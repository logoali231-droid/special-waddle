# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""End-to-end conversion tests running the full pipeline on the sample project."""
import tempfile
import unittest
from pathlib import Path

from modporter.core.generator import convert_project
from modporter.core.reader import read_project

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


class EndToEndTests(unittest.TestCase):
    def test_fabric_to_neoforge(self):
        model = read_project(SAMPLES / "fabric-mod")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            convert_project(model, "neoforge", out)
            self.assertTrue((out / "build.gradle").exists())
            self.assertTrue((out / "gradle.properties").exists())
            self.assertTrue((out / "settings.gradle").exists())
            self.assertTrue((out / "src/main/resources/META-INF/neoforge.mods.toml").exists())
            entry = (out / "src/main/java/com/example/rubymod/RubyMod.java").read_text(encoding="utf-8")
            self.assertIn('@Mod("rubymod")', entry)
            self.assertIn("DeferredRegister", entry)
            self.assertIn("@SubscribeEvent", entry)
            self.assertIn("// TODO: [CONVERT]", entry)  # Transfer API fallback
            report = (out / "CONVERSION_REPORT.md").read_text(encoding="utf-8")
            self.assertIn("Smart Fallback", report)
            # fabric.mod.json must not be copied to the neoforge output
            self.assertFalse((out / "src/main/resources/fabric.mod.json").exists())

    def test_fabric_to_forge(self):
        model = read_project(SAMPLES / "fabric-mod")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            convert_project(model, "forge", out)
            self.assertTrue((out / "src/main/resources/META-INF/mods.toml").exists())
            build = (out / "build.gradle").read_text(encoding="utf-8")
            self.assertIn("minecraftforge", build)
            entry = (out / "src/main/java/com/example/rubymod/RubyMod.java").read_text(encoding="utf-8")
            self.assertIn("RegistryObject", entry)

    def test_neoforge_to_fabric_roundtrip(self):
        # convert fabric -> neoforge first, then neoforge -> fabric
        model = read_project(SAMPLES / "fabric-mod")
        with tempfile.TemporaryDirectory() as tmp:
            mid = Path(tmp) / "mid"
            convert_project(model, "neoforge", mid)
            back = read_project(mid)
            self.assertEqual(back.engine, "neoforge")
            out2 = Path(tmp) / "back"
            convert_project(back, "fabric", out2)
            entry = (out2 / "src/main/java/com/example/rubymod/RubyMod.java").read_text(encoding="utf-8")
            self.assertIn("implements ModInitializer", entry)
            self.assertIn("onInitialize", entry)
            self.assertTrue((out2 / "src/main/resources/fabric.mod.json").exists())

    def test_same_engine_rejected(self):
        model = read_project(SAMPLES / "fabric-mod")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                convert_project(model, "fabric", Path(tmp) / "x")


if __name__ == "__main__":
    unittest.main()
