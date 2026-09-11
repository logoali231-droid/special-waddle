# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""ModPorter Studio - a local web UI for converting mod projects.

Zero dependencies: a threaded ``http.server`` serves the single-page frontend
(``web/index.html``) and a small JSON API that wraps the ModPorter core.

Endpoints:
    GET  /                      -> frontend (index.html)
    GET  /api/engines           -> supported engines + display info
    POST /api/browse            -> list a directory (folder picker)
    POST /api/detect            -> auto-detect the engine of a project
    POST /api/convert           -> run a conversion, return structured results
    GET  /api/file?path=...     -> read a file from the output tree
    GET  /api/open?path=...     -> open a folder/file in the OS file manager

Security: the API binds to 127.0.0.1 only. ``/api/file`` and ``/api/open``
restrict paths to the last output root (the conversion target). This is a
local developer convenience, not a hardened multi-user service.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import engines as engines_mod
from .core import decompile as decompile_mod
from .core.generator import ConversionError, convert_project
from .core.reader import ReaderError, read_project

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
MAX_FILE_BYTES = 400_000  # cap for the file viewer


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _fs_error_payload(exc: Exception) -> dict:
    """Map common OS errors to short, user-friendly messages."""
    msg = str(exc)
    if isinstance(exc, PermissionError):
        return {"error": "Permission denied. Close programs using this folder or pick another one."}
    if "being used by another process" in msg:
        return {"error": "That folder is locked by another program (e.g. an open Explorer window). Close it and retry."}
    return {"error": msg}


class _PathGuard:
    """Restricts file access to a single root directory (the output project)."""

    def __init__(self) -> None:
        self._root: Path | None = None

    def set(self, out_dir: Path) -> None:
        self._root = Path(out_dir).resolve()

    def resolve(self, rel_or_abs: str) -> Path | None:
        if self._root is None:
            return None
        p = Path(rel_or_abs)
        if not p.is_absolute():
            p = self._root / p
        p = p.resolve()
        try:
            p.relative_to(self._root)
        except ValueError:
            return None
        return p


def _list_dir(path: Path) -> dict:
    """List *path* as {cwd, sep, dirs, files} sorted dirs-first."""
    entries = list(os.scandir(path))
    dirs = sorted(
        (e.name for e in entries if e.is_dir() and not e.name.startswith(".")),
        key=str.lower,
    )
    files = sorted(
        (e.name for e in entries if e.is_file() and not e.name.startswith(".")),
        key=str.lower,
    )
    return {
        "cwd": str(path.resolve()),
        "sep": os.sep,
        "dirs": dirs,
        "files": files,
        "parent": str(path.resolve().parent) if path.resolve().parent != path.resolve() else None,
    }


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------

class StudioRequestHandler(BaseHTTPRequestHandler):
    server_version = "ModPorterStudio/1.0"
    guard = _PathGuard()  # class-level: shared across requests

    # -- responses ---------------------------------------------------------

    def _send(self, code: int, payload: dict | list, content_type: str = "application/json") -> None:
        body = json.dumps(payload).encode("utf-8") if content_type == "application/json" else payload
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    # -- routing -----------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/index.html"):
            return self._serve_index()
        if self.path.startswith("/api/file"):
            return self._api_file()
        if self.path.startswith("/api/open"):
            return self._api_open()
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/engines":
            return self._api_engines()
        if self.path == "/api/browse":
            return self._api_browse()
        if self.path == "/api/detect":
            return self._api_detect()
        if self.path == "/api/convert":
            return self._api_convert()
        self._send(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        pass

    # -- endpoints ---------------------------------------------------------

    def _serve_index(self) -> None:
        index = WEB_DIR / "index.html"
        if not index.is_file():
            return self._send(500, {"error": "frontend missing: modporter/web/index.html"})
        self._send(200, index.read_bytes(), "text/html")

    def _api_engines(self) -> None:
        out = []
        for name in engines_mod.SUPPORTED:
            spec = engines_mod.get_engine(name)
            out.append({
                "id": spec.name,
                "label": spec.display_name,
                "metadata": spec.metadata_file,
                "mappings": spec.mapping_type,
            })
        self._send(200, {"engines": out})

    def _api_browse(self) -> None:
        data = self._payload()
        raw = data.get("path") or os.path.expanduser("~")
        path = Path(raw).expanduser()
        if not path.exists():
            return self._send(404, {"error": "Folder not found."})
        if not path.is_dir():
            return self._send(400, {"error": "That path is a file, not a folder."})
        try:
            self._send(200, _list_dir(path))
        except PermissionError:
            self._send(403, {"error": "Permission denied for this folder."})

    def _api_detect(self) -> None:
        data = self._payload()
        raw = (data.get("path") or "").strip()
        if not raw:
            return self._send(400, {"error": "path is required"})
        path = Path(raw).expanduser()
        if path.is_file() and decompile_mod.is_mod_jar(path):
            engine = decompile_mod.jar_engine(path)
            if engine:
                return self._send(200, {"detected": engine,
                                        "evidence": "loader metadata inside the jar",
                                        "jar": True})
            return self._send(200, {"detected": None, "jar": True})
        if not path.is_dir():
            return self._send(400, {"error": "Project folder not found."})
        engine, evidence = engines_mod.detect_source_engine(path)
        if not engine:
            return self._send(200, {"detected": None})
        return self._send(200, {"detected": engine, "evidence": evidence})

    def _api_convert(self) -> None:
        data = self._payload()
        project = (data.get("project") or "").strip()
        target = (data.get("target") or "").strip().lower()
        out = (data.get("output") or "").strip()
        if not project or not target:
            return self._send(400, {"error": "project and target are required"})

        project_path = Path(project).expanduser()
        out_path = Path(out).expanduser() if out else project_path.parent / f"{project_path.name}-{target}"
        jar_banner: str | None = None

        try:
            if project_path.is_file() and decompile_mod.is_mod_jar(project_path):
                try:
                    workdir = project_path.parent / f"{project_path.stem}-modporter-work"
                    project_path = decompile_mod.prepare_jar_project(project_path, workdir)
                    jar_banner = (
                        "Compiled jar detected: sources were reconstructed by decompilation "
                        "(Vineflower). Comments are lost and pre-1.17 Forge jars keep SRG "
                        "names - expect manual porting work."
                    )
                except decompile_mod.DecompileError as exc:
                    return self._send(400, {"error": str(exc)})
            out_path = Path(out).expanduser() if out else project_path.parent / f"{project_path.name}-{target}"
            model = read_project(project_path, engine=data.get("source_engine") or None)
            try:
                # Guard BEFORE any filesystem writes: refuse to convert a
                # project into itself or into one of its own subfolders.
                resolved_out = out_path.resolve()
                resolved_proj = project_path.resolve()
                if resolved_out == resolved_proj or resolved_proj in resolved_out.parents:
                    return self._send(400, {"error": "Output folder must be outside the project folder."})
                report = convert_project(
                    model, target, out_path, clean=True, verbose=True,
                    jar_note=(
                        "sources were reconstructed by decompilation (Vineflower); "
                        "comments are lost and pre-1.17 Forge jars keep SRG names "
                        "(func_...) - expect manual porting work"
                    ) if jar_banner else None,
                )
            except ConversionError as exc:
                return self._send(400, {"error": str(exc)})
            except engines_mod.EngineError as exc:
                return self._send(400, {"error": str(exc)})
        except ReaderError as exc:
            return self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            return self._send(500, _fs_error_payload(exc))

        out_resolved = Path(report).resolve()
        self.guard.set(out_resolved)

        # build a compact, UI-friendly summary of what changed
        report_text = (out_resolved / "CONVERSION_REPORT.md").read_text(encoding="utf-8")
        files = []
        for p in sorted(out_resolved.rglob("*")):
            if p.is_file() and p.name != "CONVERSION_REPORT.md":
                files.append({
                    "path": p.relative_to(out_resolved).as_posix(),
                    "size": p.stat().st_size,
                })
        todo_count = 0
        for p in out_resolved.rglob("*.java"):
            todo_count += p.read_text(encoding="utf-8", errors="replace").count("TODO: [CONVERT]")
        payload = {
            "output": str(out_resolved),
            "report": report_text,
            "files": files,
            "warnings": todo_count,
            "jar_banner": jar_banner,
        }
        self._send(200, payload)

    def _api_file(self) -> None:
        from urllib.parse import urlparse, parse_qs, unquote
        qs = parse_qs(urlparse(self.path).query)
        rel = unquote(qs.get("path", [""])[0])
        p = self.guard.resolve(rel)
        if p is None or not p.is_file():
            return self._send(404, {"error": "File not found (run a conversion first)."})
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                return self._send(200, {"path": rel, "truncated": True, "text": ""})
            text = p.read_text(encoding="utf-8", errors="replace")
            return self._send(200, {"path": rel, "truncated": False, "text": text})
        except OSError as exc:
            return self._send(500, _fs_error_payload(exc))

    def _api_open(self) -> None:
        from urllib.parse import urlparse, parse_qs, unquote
        qs = parse_qs(urlparse(self.path).query)
        rel = unquote(qs.get("path", [""])[0])
        p = self.guard.resolve(rel)
        if p is None:
            return self._send(404, {"error": "Path not found (run a conversion first)."})
        try:
            if sys.platform == "win32":
                os.startfile(p)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except OSError as exc:
            return self._send(500, _fs_error_payload(exc))
        self._send(200, {"opened": str(p)})


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Start the Studio server and (optionally) open the browser."""
    server = ThreadingHTTPServer((host, port), StudioRequestHandler)
    url = f"http://{host}:{port}/"
    print(f"ModPorter Studio running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":  # pragma: no cover
    serve()
