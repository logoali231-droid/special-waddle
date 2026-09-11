# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Asset transformers for mixin configs and language files."""
from __future__ import annotations

import json
import re

from ..core.model import ProjectModel


class AssetTransformer:
    def transform(self, asset, model, ctx) -> str:
        return asset.text


class MixinConfigTransformer(AssetTransformer):
    """Rewrites a mixin json for the target engine."""

    def transform(self, asset, model, ctx) -> str:
        try:
            data = json.loads(asset.text)
        except json.JSONDecodeError:
            return asset.text
        if not isinstance(data, dict):
            return asset.text

        notes = []
        target = ctx.target_engine
        if target == "fabric":
            # fabric uses "refmap" with yarn names; compatibility entries unchanged
            if "refmap" not in data:
                data["refmap"] = ctx.metadata.mod_id + ".refmap.json"
        elif target in ("forge", "neoforge"):
            data.pop("refmap", None)
            data["minVersion"] = "0.8"
            if target == "forge" and "required" not in data:
                data["required"] = True
            if target == "neoforge" and "required" not in data:
                data["required"] = True
            notes.append("Removed refmap (mojmap targets use named targets directly).")
            notes.append("Set required=true and minVersion=0.8 for Forge-style mixin configs.")
        data.setdefault("compatibilityLevel", "JAVA_21")
        if notes:
            ctx.notes.append(f"Mixin config {asset.path}: " + " ".join(notes))
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


class LangFileTransformer(AssetTransformer):
    """Language files are engine-agnostic; pass through unchanged."""

    def transform(self, asset, model, ctx) -> str:
        return asset.text


def is_mixin_config(path: str) -> bool:
    return path.endswith(".json") and "mixins" in path.rsplit("/", 1)[-1].lower()
