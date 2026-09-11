# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 1 - Metadata Reader.

Reads the source project (``fabric.mod.json``, ``mods.toml``,
``neoforge.mods.toml``, Gradle files, Java sources and assets) and produces a
normalized :class:`~modporter.core.model.ProjectModel`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .engines import ENGINE_FABRIC, ENGINE_FORGE, ENGINE_NEOFORGE, detect_source_engine, get_engine
from .model import AssetFile, Dependency, ModMetadata, ProjectModel, SourceFile

JAVA_FILE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.java$")
ASSET_SUFFIXES = {".json", ".mcmeta", ".toml", ".txt", ".cfg"}
SKIP_DIRS = {"build", ".gradle", "run", ".git", "out", "target", ".idea", "runs", ".loom"}


class ReaderError(RuntimeError):
    """Raised when the source project cannot be read."""


def _toml_lite(text: str) -> dict:
    """Parse the subset of TOML used by mods.toml without external deps.

    Supports: strings (single/double quoted), booleans, numbers, arrays of
    scalars, ``[table]`` and ``[[array-of-tables]]`` headers.
    """
    root: dict = {}
    current: list[str] = []
    in_multiline = False
    quote3 = ""
    buf: list[str] = []

    def container(path: list[str]) -> dict:
        node = root
        for part in path:
            nxt = node.get(part)
            if isinstance(nxt, list):
                if not nxt:
                    nxt.append({})
                nxt = nxt[-1]
            elif not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        return node

    def parse_value(raw: str):
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            parts = [p.strip() for p in _split_toml_list(inner)]
            return [parse_value(p) for p in parts if p]
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            return raw[1:-1]
        if raw in ("true", "false"):
            return raw == "true"
        try:
            return int(raw)
        except ValueError:
            try:
                return float(raw)
            except ValueError:
                return raw

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if in_multiline:
            if raw_line.strip().endswith(quote3):
                buf.append(raw_line[: raw_line.rindex(quote3)])
                container(current)[key] = "\n".join(buf).lstrip("\n")
                in_multiline = False
            else:
                buf.append(raw_line)
            continue
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if line.startswith("[["):
                name = line[2:-2].strip()
                parts = [p.strip().strip("\"'") for p in name.split(".")]
                node = container(parts[:-1])
                arr = node.setdefault(parts[-1], [])
                if not isinstance(arr, list):
                    raise ValueError(f"{parts[-1]} is not an array")
                arr.append({})
                current = parts
            elif line.startswith("["):
                name = line[1:-1].strip()
                parts = [p.strip().strip("\"'") for p in name.split(".")]
                node = container(parts[:-1])
                if parts[-1] in node and isinstance(node[parts[-1]], dict):
                    raise ValueError(f"duplicate table {name}")
                node.setdefault(parts[-1], {})
                current = parts
            elif "=" in line:
                key, _, raw = line.partition("=")
                key = key.strip().strip("\"'")
                m3 = re.match(r"^(['\"]){3}(.*)$", raw)
                if m3:
                    quote3 = m3.group(1) * 3
                    rest = m3.group(2)
                    if rest.endswith(quote3) and len(rest) >= 3:
                        container(current)[key] = rest[: -3]
                    else:
                        buf = [rest]
                        in_multiline = True
                    continue
                if "#" in raw and not raw.lstrip().startswith(("\"", "'")):
                    raw = raw.split("#", 1)[0]
                container(current)[key] = parse_value(raw)
        except Exception as exc:  # pragma: no cover - defensive
            raise ReaderError(f"TOML parse error at line {lineno}: {raw_line!r} ({exc})") from exc
    return root


def _split_toml_list(inner: str) -> list[str]:
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _dep_list(raw) -> list[Dependency]:
    out: list[Dependency] = []
    if isinstance(raw, dict):
        for mod_id, val in raw.items():
            version = val.get("version", "*") if isinstance(val, dict) else str(val)
            out.append(Dependency(mod_id=mod_id, version_range=version))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.append(Dependency(mod_id=item.get("modId", "?"), version_range=item.get("versionRange", item.get("version", "*"))))
    return out


def _metadata_from_fabric(data: dict) -> ModMetadata:
    meta = ModMetadata()
    meta.mod_id = data.get("id", "examplemod")
    meta.name = data.get("name", meta.mod_id)
    meta.version = data.get("version", "1.0.0")
    meta.description = data.get("description", "")
    meta.authors = list(data.get("authors", []) or [])
    if meta.authors and not isinstance(meta.authors[0], str):
        meta.authors = [a.get("name", "?") if isinstance(a, dict) else str(a) for a in meta.authors]
    meta.license = data.get("license", "MIT")
    if isinstance(meta.license, list):
        meta.license = ", ".join(meta.license)
    meta.entrypoints = {k: list(v) for k, v in (data.get("entrypoints") or {}).items()}
    contact = data.get("contact") or {}
    meta.homepage = contact.get("homepage")
    meta.sources = contact.get("sources")
    meta.issues = contact.get("issues")
    meta.icon = data.get("icon")
    meta.depends = _dep_list(data.get("depends"))
    meta.suggests = _dep_list(data.get("suggests"))
    meta.extra = {
        k: v for k, v in data.items()
        if k not in {"id", "name", "version", "description", "authors", "license",
                     "entrypoints", "contact", "icon", "depends", "suggests", "environment", "mixins"}
    }
    meta.extra["environment"] = data.get("environment", "*")
    meta.extra["mixins"] = list(data.get("mixins", []) or [])
    return meta


def _metadata_from_toml(data: dict, engine: str) -> ModMetadata:
    meta = ModMetadata()
    mods = data.get("mods") or [{}]
    first = mods[0] if mods else {}
    meta.mod_id = first.get("modId", "examplemod")
    meta.name = first.get("displayName", meta.mod_id)
    meta.version = str(first.get("version", "1.0.0"))
    meta.description = first.get("description", "")
    authors = first.get("authors", "")
    meta.authors = [a.strip() for a in authors.split(",")] if isinstance(authors, str) else list(authors or [])
    meta.license = str(first.get("license", "MIT"))
    meta.icon = first.get("logoFile")
    deps: list[Dependency] = []
    raw_deps = data.get("dependencies") or {}
    # Two valid shapes:
    #   dotted:      [[dependencies.rubymod]]  -> dict of modid -> [tables]
    #   flat (Neo):  [[dependencies]]          -> list of tables with modId
    if isinstance(raw_deps, dict):
        dep_tables = raw_deps.get(meta.mod_id, []) or []
        if isinstance(dep_tables, dict):
            dep_tables = [dep_tables]
    else:
        dep_tables = [d for d in raw_deps if isinstance(d, dict)]
    for dep in dep_tables:
        deps.append(Dependency(mod_id=dep.get("modId", "?"), version_range=dep.get("versionRange", dep.get("version", "*"))))
    meta.depends = deps
    meta.extra = {
        "loaderVersion": data.get("loaderVersion", ""),
        "issueTrackerURL": data.get("issueTrackerURL"),
        "displayTest": first.get("displayTest"),
    }
    return meta


def _read_entry_class_refs(root: Path, meta: ModMetadata) -> None:
    """Resolve fabric entrypoints pointing at classes vs. methods."""
    # Kept as declared; the entrypoint transformer resolves them later.
    return None


# Candidate locations of loader manifests, most specific first. Covers both
# the source-tree layout (src/main/resources/...) and the built-jar layout
# (... at the jar root), so extracted mod jars read exactly like IDE projects.
_METADATA_CANDIDATES: dict[str, tuple[str, ...]] = {
    "fabric.mod.json": (
        "src/main/resources/fabric.mod.json",
        "fabric.mod.json",
    ),
    "mods.toml": (
        "src/main/resources/META-INF/mods.toml",
        "META-INF/mods.toml",
    ),
    "neoforge.mods.toml": (
        "src/main/resources/META-INF/neoforge.mods.toml",
        "META-INF/neoforge.mods.toml",
    ),
}


def _find_metadata(root: Path, filename: str) -> Path | None:
    for rel in _METADATA_CANDIDATES.get(filename, (filename,)):
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


def _resource_root_for(root: Path, manifest: Path | None) -> Path:
    """The resources root implied by where the manifest was found."""
    if manifest is None:
        return root / "src/main/resources"
    rel = manifest.relative_to(root)
    if "META-INF" in rel.parts:
        return root / Path(*rel.parts[: rel.parts.index("META-INF")])
    if rel.parent != Path("."):
        return root / rel.parent
    return root


def read_project(root: Path, engine: str | None = None) -> ProjectModel:
    """Read the project at *root* into a :class:`ProjectModel`."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ReaderError(f"Project root does not exist: {root}")

    detected, evidence = detect_source_engine(root)
    if engine is None:
        engine = detected
    if engine is None:
        raise ReaderError(
            "Could not detect the source engine automatically. "
            "Pass --source-engine explicitly."
        )
    if detected and detected != engine:
        print(f"[reader] warning: metadata says {detected} (via {evidence}), using requested {engine}")
    spec = get_engine(engine)

    meta = ModMetadata()
    manifest_path: Path | None = None
    if engine == ENGINE_FABRIC:
        fmp = _find_metadata(root, "fabric.mod.json")
        manifest_path = fmp
        if fmp is not None:
            try:
                data = json.loads(fmp.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ReaderError(f"Invalid fabric.mod.json: {exc}") from exc
            meta = _metadata_from_fabric(data)
    else:
        toml_name = "neoforge.mods.toml" if engine == ENGINE_NEOFORGE else "mods.toml"
        toml_path = _find_metadata(root, toml_name)
        manifest_path = toml_path
        if toml_path is not None:
            data = _toml_lite(toml_path.read_text(encoding="utf-8"))
            meta = _metadata_from_toml(data, engine)

    if manifest_path is None or not meta.mod_id:
        raise ReaderError(
            f"No readable {engine} manifest ({spec.metadata_file}) found at {root}. "
            "The mod identity would be lost; refusing to convert. "
            "If this is a compiled jar, pass the .jar file directly."
        )

    model = ProjectModel(root=str(root), engine=engine, spec=spec, metadata=meta)

    # Gradle files (kept for reference / version reuse).
    for gradle_name in ("build.gradle", "settings.gradle", "gradle.properties"):
        gp = root / gradle_name
        if gp.is_file():
            model.gradle_files[gradle_name] = gp.read_text(encoding="utf-8", errors="replace")
    props = _parse_gradle_properties(model.gradle_files.get("gradle.properties", ""))
    model.minecraft_version = props.get("minecraft_version")
    model.loader_version = props.get("loader_version", props.get("neo_version", props.get("forge_version", "*")))

    src_main = root / "src" / "main"
    res_root = _resource_root_for(root, manifest_path)
    java_root = src_main / "java"
    if java_root.is_dir():
        for path in sorted(java_root.rglob("*.java")):
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            package, class_name = _java_coord(path, java_root)
            model.sources.append(SourceFile(path=rel, package=package, class_name=class_name, text=text))

    mixin_configs: list[str] = []
    if res_root.is_dir():
        for path in sorted(res_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(res_root).as_posix()
            if path.suffix.lower() in ASSET_SUFFIXES and "META-INF" not in path.parts:
                model.assets.append(AssetFile(path=rel, text=path.read_text(encoding="utf-8", errors="replace")))
            if path.suffix == ".json" and "mixins" in path.stem.lower():
                mixin_configs.append(rel)
    model.mixin_configs = mixin_configs
    return model


def _java_coord(path: Path, java_root: Path) -> tuple[str, str]:
    package = path.parent.relative_to(java_root).as_posix().replace("/", ".")
    if package == ".":
        package = ""
    return package, path.stem


def _parse_gradle_properties(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        props[key.strip()] = val.strip()
    return props
