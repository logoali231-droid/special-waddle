# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 2 - Metadata conversion.

Converts ``fabric.mod.json`` <-> ``mods.toml`` <-> ``neoforge.mods.toml``
while preserving id, name, version, description, authors, license and
dependency lists.
"""
from __future__ import annotations

import json

from .engines import ENGINE_FABRIC, ENGINE_FORGE, ENGINE_NEOFORGE
from .model import ModMetadata, ProjectModel
from .tomlwriter import dumps as toml_dumps

LOADER_MIN_FABRIC = ">=0.16.0"
LOADER_MIN_FORGE = "[49,)"
LOADER_MIN_NEOFORGE = "[21,)"


def convert_metadata(model: ProjectModel, target_engine: str) -> dict[str, str]:
    """Return {resource_path: content} for the target engine's metadata file."""
    meta = model.metadata
    if target_engine == ENGINE_FABRIC:
        return {"src/main/resources/fabric.mod.json": _to_fabric_json(meta, model)}
    name = "neoforge.mods.toml" if target_engine == ENGINE_NEOFORGE else "mods.toml"
    return {f"src/main/resources/META-INF/{name}": _to_toml(meta, target_engine, model)}


def _to_fabric_json(meta: ModMetadata, model: ProjectModel) -> str:
    data = {
        "schemaVersion": 1,
        "id": meta.mod_id,
        "version": meta.version,
        "name": meta.name,
        "description": meta.description,
        "authors": meta.authors or ["Unknown"],
        "contact": {
            k: v for k, v in {
                "homepage": meta.homepage,
                "sources": meta.sources,
                "issues": meta.issues,
            }.items() if v
        },
        "license": meta.license,
        "icon": meta.icon,
        "environment": meta.extra.get("environment", "*"),
        "entrypoints": {
            "main": meta.entrypoints.get("main", [f"com.example.{meta.mod_id.capitalize()}"]),
        },
        "depends": {
            "fabricloader": LOADER_MIN_FABRIC,
            "fabric-api": "*",
            "minecraft": model.minecraft_version or "~1.21",
        },
        "suggests": {d.mod_id: d.version_range for d in meta.suggests},
    }
    if meta.extra.get("mixins"):
        data["mixins"] = meta.extra["mixins"]
    return json.dumps(data, indent=2) + "\n"


def _to_toml(meta: ModMetadata, target_engine: str, model: ProjectModel) -> str:
    is_neo = target_engine == ENGINE_NEOFORGE
    file_key = "neoforge.mods.toml" if is_neo else "mods.toml"
    loader_key = "loaderVersion" if is_neo else "loaderVersion"
    mods_tbl = {
        "modId": meta.mod_id,
        "version": meta.version,
        "displayName": meta.name,
        "authors": ", ".join(meta.authors) if meta.authors else "Unknown",
        "description": meta.description or "Converted by ModPorter",
        "license": meta.license,
    }
    if meta.icon:
        mods_tbl["logoFile"] = meta.icon
    if meta.extra.get("displayTest"):
        mods_tbl["displayTest"] = meta.extra["displayTest"]

    deps: list[dict] = [
        {
            "modId": "neoforge" if is_neo else "forge",
            "type": "required",
            "versionRange": LOADER_MIN_NEOFORGE if is_neo else LOADER_MIN_FORGE,
            "ordering": "NONE",
            "side": "BOTH",
        },
        {
            "modId": "minecraft",
            "type": "required",
            "versionRange": model.minecraft_version or "[1.21,)",
            "ordering": "NONE",
            "side": "BOTH",
        },
    ]
    # fabric-api dependencies do not exist on Forge/NeoForge; javelin them into notes.
    for d in meta.depends:
        if d.mod_id in ("fabric", "fabric-api", "fabricloader", "minecraft", "java"):
            continue
        deps.append({
            "modId": d.mod_id,
            "type": "required",
            "versionRange": d.version_range,
            "ordering": "AFTER",
            "side": "BOTH",
        })

    header_comment = (
        "# Conversion by ModPorter - metadata migrated from "
        f"{model.engine} ({model.spec.metadata_file}).\n"
    )
    body = {
        "modLoader": "javafml",
        "loaderVersion": LOADER_MIN_NEOFORGE if is_neo else LOADER_MIN_FORGE,
        "license": meta.license,
        "issueTrackerURL": meta.issues or "",
        "mods": [mods_tbl],
        "dependencies": deps,
    }
    if is_neo:
        body["properties"] = {}
    return header_comment + toml_dumps(body)


# --- reverse direction: read target-style metadata (used by round trips) ----

def metadata_from_toml_data(data: dict, engine: str) -> ModMetadata:
    from .reader import _metadata_from_toml
    return _metadata_from_toml(data, engine)
