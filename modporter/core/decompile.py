# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Compiled-jar support: turn a mod ``*.jar`` into a processable source project.

Mod jars ship ``.class`` bytecode, not sources. This module

1. recognizes a mod jar (loader metadata or ``.class`` payload),
2. extracts its metadata + assets,
3. reconstructs ``.java`` sources with `Vineflower <https://vineflower.org/>`_
   (downloaded once from Maven Central and cached; runs on any JDK 17+),
4. assembles a source-tree project ModPorter can convert normally.

Decompiled code loses comments and pre-1.17 Forge jars expose SRG member
names (``func_...``); semantic results are therefore a best-effort starting
point, and the conversion report says so.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

VINEFLOWER_URL = (
    "https://repo1.maven.org/maven2/org/vineflower/vineflower/"
    "1.11.1/vineflower-1.11.1.jar"
)
VINEFLOWER_MIN_BYTES = 1_000_000  # an HTML error page is not a 1 MB+ jar

MANIFEST_PATHS = {
    "META-INF/mods.toml": "forge",
    "META-INF/neoforge.mods.toml": "neoforge",
    "fabric.mod.json": "fabric",
    "src/main/resources/META-INF/mods.toml": "forge",
    "src/main/resources/META-INF/neoforge.mods.toml": "neoforge",
    "src/main/resources/fabric.mod.json": "fabric",
}


class DecompileError(RuntimeError):
    """Raised when a jar cannot be prepared for conversion."""


# --------------------------------------------------------------------------
# jar detection
# --------------------------------------------------------------------------

def is_mod_jar(path: Path) -> bool:
    """True when *path* is a readable jar/zip carrying loader metadata."""
    path = Path(path)
    if not path.is_file() or path.suffix.lower() not in (".jar", ".zip"):
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return any(
        name in names or name.rstrip("/") in names
        for name in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml", "fabric.mod.json")
    )


def jar_engine(path: Path) -> str | None:
    """Engine implied by the loader metadata inside *path*, if any."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "META-INF/neoforge.mods.toml" in names:
                return "neoforge"
            if "META-INF/mods.toml" in names:
                return "forge"
            if "fabric.mod.json" in names:
                return "fabric"
    except (OSError, zipfile.BadZipFile):
        return None
    return None


# --------------------------------------------------------------------------
# Vineflower acquisition (cached, stdlib-only)
# --------------------------------------------------------------------------

def _cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "modporter"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "modporter"


def vineflower_cache_path() -> Path:
    return _cache_dir() / "vineflower.jar"


def _find_java() -> str:
    java = shutil.which("java")
    if not java:
        raise DecompileError(
            "Java was not found on PATH. Install a JDK 17+ (https://adoptium.net) "
            "to enable decompiling of compiled mod jars."
        )
    return java


def ensure_vineflower(force_download: bool = False) -> Path:
    """Return a usable vineflower.jar, downloading it on first use."""
    cache = vineflower_cache_path()
    if cache.is_file() and not force_download and cache.stat().st_size >= VINEFLOWER_MIN_BYTES:
        return cache
    _find_java()  # fail early with the actionable message
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".part")
    print(f"[decompile] downloading Vineflower -> {cache}")
    try:
        with urllib.request.urlopen(VINEFLOWER_URL, timeout=120) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out)
        tmp.replace(cache)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise DecompileError(
            f"Could not download Vineflower from {VINEFLOWER_URL}: {exc}. "
            "Download it manually and place it at " + str(cache)
        ) from exc
    return cache


# --------------------------------------------------------------------------
# extraction + decompilation
# --------------------------------------------------------------------------

def _safe_unzip(jar: Path, dest: Path) -> None:
    with zipfile.ZipFile(jar) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest.resolve()) + "\\") and \
               not str(target).startswith(str(dest.resolve()) + "/"):
                if target != dest.resolve():
                    continue  # zip-slip entry: skip
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _has_class_files(root: Path) -> bool:
    return any(root.rglob("*.class"))


def decompile_directory(extracted: Path, sources_out: Path, log=print) -> None:
    """Run Vineflower over *extracted*, writing ``.java`` under *sources_out*."""
    vf = ensure_vineflower()
    sources_out.mkdir(parents=True, exist_ok=True)
    cmd = [
        _find_java(), "-jar", str(vf),
        "--folder-compression-level=9",
        str(extracted), str(sources_out),
    ]
    log(f"[decompile] vineflower: {extracted.name} -> {sources_out.name}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        raise DecompileError(
            "Vineflower failed (exit "
            f"{proc.returncode}):\n" + "\n".join(tail)
        )


def _looks_like_source_tree(extracted: Path) -> bool:
    return (extracted / "src" / "main").is_dir()


def prepare_jar_project(
    jar: Path,
    workdir: Path,
    keep_intermediates: bool = False,
    log=print,
) -> Path:
    """Turn a compiled mod jar into a ModPorter source project.

    Returns the project root. ``.java`` sources are reconstructed with
    Vineflower when the jar contains ``.class`` files.
    """
    jar = Path(jar)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    if not is_mod_jar(jar):
        raise DecompileError(f"Not a readable mod jar: {jar}")

    extracted = workdir / f"{jar.stem}-extracted"
    sources_out = workdir / f"{jar.stem}-decompiled"
    project = workdir / f"{jar.stem}-project"
    if project.is_dir() and (project / "src").is_dir():
        return project  # idempotent: reuse a previous preparation

    if not extracted.is_dir():
        log(f"[decompile] extracting {jar.name}")
        extracted.mkdir(parents=True, exist_ok=True)
        _safe_unzip(jar, extracted)

    source_tree = _looks_like_source_tree(extracted)
    needs_decompile = not source_tree and _has_class_files(extracted)
    if needs_decompile and not sources_out.is_dir():
        decompile_directory(extracted, sources_out, log=log)

    # Assemble the source-tree layout ModPorter understands.
    res = project / "src" / "main" / "resources"
    jav = project / "src" / "main" / "java"
    res.mkdir(parents=True, exist_ok=True)

    if source_tree:
        if (extracted / "src" / "main" / "java").is_dir():
            shutil.copytree(extracted / "src" / "main" / "java", jav, dirs_exist_ok=True)
        shutil.copytree(extracted / "src" / "main" / "resources", res, dirs_exist_ok=True)
    else:
        # resources: everything except classfiles and jar plumbing
        for path in sorted(extracted.rglob("*")):
            if not path.is_file() or path.suffix == ".class":
                continue
            rel = path.relative_to(extracted)
            if rel.parts[0] == "META-INF":
                # keep the loader manifest (relocated to the source-tree
                # position ModPorter reads) and the access transformer;
                # drop MANIFEST.MF and friends.
                if rel.name in ("mods.toml", "neoforge.mods.toml", "accesstransformer.cfg"):
                    rel = Path("src/main/resources") / "META-INF" / rel.name
                    target = project / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                continue
            target = res / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if sources_out.is_dir():
            for path in sorted(sources_out.rglob("*.java")):
                rel = path.relative_to(sources_out)
                (jav / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, jav / rel)

    if not keep_intermediates:
        shutil.rmtree(extracted, ignore_errors=True)
        shutil.rmtree(sources_out, ignore_errors=True)
    log(f"[decompile] prepared source project at {project}")
    return project
