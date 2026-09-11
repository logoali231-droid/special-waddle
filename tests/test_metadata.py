# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Tests for metadata conversion (fabric.mod.json <-> mods.toml)."""
import json
import unittest
from pathlib import Path

from modporter.core.engines import ENGINE_FABRIC, ENGINE_NEOFORGE
from modporter.core.metadata import convert_metadata
from modporter.core.model import ModMetadata, ProjectModel


def _model(engine: str) -> ProjectModel:
    from modporter.core.engines import get_engine
    meta = ModMetadata(
        mod_id="rubymod",
        name="Ruby Mod",
        version="1.2.3",
        description="desc",
        authors=["Alice"],
        license="MIT",
        entrypoints={"main": ["com.example.rubymod.RubyMod"], "client": ["com.example.rubymod.client.RubyModClient"]},
    )
    from modporter.core.reader import Dependency
    meta.depends = [Dependency("cloth-config", ">=11.0.0"), Dependency("fabric-api", "*")]
    meta.suggests = [Dependency("modmenu", "*")]
    return ProjectModel(root=".", engine=engine, spec=get_engine(engine), metadata=meta,
                        minecraft_version="1.21.1")


class MetadataTests(unittest.TestCase):
    def test_fabric_to_neoforge(self):
        model = _model(ENGINE_FABRIC)
        files = convert_metadata(model, ENGINE_NEOFORGE)
        self.assertIn("src/main/resources/META-INF/neoforge.mods.toml", files)
        text = files["src/main/resources/META-INF/neoforge.mods.toml"]
        self.assertIn('modId = "rubymod"', text)
        self.assertIn('version = "1.2.3"', text)
        self.assertIn('displayName = "Ruby Mod"', text)
        self.assertIn('modId = "neoforge"', text)
        self.assertIn('modId = "cloth-config"', text)
        self.assertNotIn("fabric-api", text)

    def test_fabric_to_fabric_roundtrip(self):
        model = _model(ENGINE_FABRIC)
        files = convert_metadata(model, ENGINE_FABRIC)
        text = files["src/main/resources/fabric.mod.json"]
        data = json.loads(text)
        self.assertEqual(data["id"], "rubymod")
        self.assertEqual(data["version"], "1.2.3")
        self.assertEqual(data["entrypoints"]["main"], ["com.example.rubymod.RubyMod"])
        self.assertIn("fabric-api", data["depends"])

    def test_neo_to_fabric(self):
        model = _model(ENGINE_NEOFORGE)
        files = convert_metadata(model, ENGINE_FABRIC)
        text = files["src/main/resources/fabric.mod.json"]
        data = json.loads(text)
        self.assertEqual(data["id"], "rubymod")
        self.assertIn("fabricloader", data["depends"])


if __name__ == "__main__":
    unittest.main()
