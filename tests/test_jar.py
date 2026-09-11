# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Compiled-jar support: detection, extraction, preparation, layout discovery."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from modporter.core import decompile
from modporter.core.engines import detect_source_engine
from modporter.core.reader import _toml_lite, read_project

TOML_FIXTURE = """modLoader="javafml"
loaderVersion="[36,37)"
license="All rights reserved"

[[mods]]
modId="tombstone"
version="6.7.3"
displayName="Corail Tombstone"
authors="Corail31"
description='''
Corail Tombstone keeps you from losing your belongings on death.
'''
displayTest="MATCH_VERSION"

[[dependencies.tombstone]]
    modId="forge"
    mandatory=true
    versionRange="[36.2.0,37)"
    ordering="NONE"
    side="BOTH"

[[dependencies.tombstone]]
    modId="minecraft"
    mandatory=true
    versionRange="[1.16.5,1.17)"
    ordering="NONE"
    side="BOTH"
"""


def _make_mod_jar(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/mods.toml", TOML_FIXTURE)
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        zf.writestr("pack.mcmeta", '{"pack":{"description":"t","pack_format":6}}')
        zf.writestr("assets/tombstone/lang/en_us.json", '{"block.x": "X"}')
        zf.writestr("ovh/corail/Foo.class", b"\xca\xfe\xba\xbe-fake")


class TestJarDetection(unittest.TestCase):
    def test_is_mod_jar(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            jar = Path(td) / "m.jar"
            _make_mod_jar(jar)
            self.assertTrue(decompile.is_mod_jar(jar))
            plain = Path(td) / "plain.zip"
            with zipfile.ZipFile(plain, "w") as zf:
                zf.writestr("readme.txt", "hi")
            self.assertFalse(decompile.is_mod_jar(plain))
            self.assertFalse(decompile.is_mod_jar(Path(td) / "missing.jar"))

    def test_jar_engine(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            jar = Path(td) / "m.jar"
            _make_mod_jar(jar)
            self.assertEqual(decompile.jar_engine(jar), "forge")


class TestLayoutDiscovery(unittest.TestCase):
    """Extracted-jar layout must read like an IDE project (audit fix)."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        root = Path(self._td.name)
        _make_mod_jar(root / "unused.jar")
        # simulate an extraction: manifest at the root, assets alongside
        (root / "META-INF").mkdir()
        (root / "META-INF" / "mods.toml").write_text(TOML_FIXTURE, encoding="utf-8")
        (root / "pack.mcmeta").write_text(
            '{"pack":{"description":"t","pack_format":6}}', encoding="utf-8"
        )
        lang = root / "assets" / "tombstone" / "lang"
        lang.mkdir(parents=True)
        (lang / "en_us.json").write_text('{"block.x": "X"}', encoding="utf-8")
        self.root = root

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_detect_root_layout(self) -> None:
        engine, evidence = detect_source_engine(self.root)
        self.assertEqual(engine, "forge")
        self.assertEqual(evidence, "META-INF/mods.toml")

    def test_multiline_toml_description(self) -> None:
        data = _toml_lite(TOML_FIXTURE)
        first = data["mods"][0]
        self.assertEqual(first["modId"], "tombstone")
        self.assertIn("losing your belongings", first["description"])

    def test_read_project_keeps_identity_and_assets(self) -> None:
        model = read_project(self.root, engine="forge")
        self.assertEqual(model.metadata.mod_id, "tombstone")
        self.assertEqual(model.metadata.version, "6.7.3")
        self.assertEqual(model.metadata.authors, ["Corail31"])
        self.assertIn("losing your belongings", model.metadata.description)
        dep_ids = {d.mod_id for d in model.metadata.depends}
        self.assertEqual(dep_ids, {"forge", "minecraft"})
        # pack.mcmeta + lang json carried as assets, manifest dir excluded
        asset_paths = {a.path for a in model.assets}
        self.assertIn("pack.mcmeta", asset_paths)
        self.assertIn("assets/tombstone/lang/en_us.json", asset_paths)


class TestPrepareJarProject(unittest.TestCase):
    def test_prepare_assembles_source_project(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            jar = Path(td) / "m.jar"
            _make_mod_jar(jar)

            def fake_decompile(extracted: Path, sources_out: Path, log=print) -> None:
                src = sources_out / "ovh" / "corail" / "Foo.java"
                src.parent.mkdir(parents=True, exist_ok=True)
                src.write_text("package ovh.corail;\npublic class Foo {}\n", encoding="utf-8")

            with mock.patch.object(decompile, "decompile_directory", side_effect=fake_decompile):
                project = decompile.prepare_jar_project(jar, Path(td) / "work")
            self.assertTrue((project / "src/main/resources/META-INF/mods.toml").is_file())
            self.assertTrue((project / "src/main/resources/pack.mcmeta").is_file())
            self.assertTrue((project / "src/main/resources/assets/tombstone/lang/en_us.json").is_file())
            self.assertTrue((project / "src/main/java/ovh/corail/Foo.java").is_file())
            self.assertFalse((project / "src/main/resources/META-INF/MANIFEST.MF").exists())
            # idempotent: a second call reuses the prepared project
            again = decompile.prepare_jar_project(jar, Path(td) / "work")
            self.assertEqual(project, again)

    def test_missing_java_gives_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            jar = Path(td) / "m.jar"
            _make_mod_jar(jar)
            with mock.patch.object(decompile.shutil, "which", return_value=None):
                with self.assertRaises(decompile.DecompileError) as ctx:
                    decompile.prepare_jar_project(jar, Path(td) / "work")
            self.assertIn("Java was not found", str(ctx.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
