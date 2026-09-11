# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Tests for the TOML subset reader/writer."""
import unittest

from modporter.core.reader import _toml_lite
from modporter.core.tomlwriter import dumps


class TomlWriterTests(unittest.TestCase):
    def test_scalars_and_tables(self):
        text = dumps({
            "modLoader": "javafml",
            "license": "MIT",
            "mods": [{
                "modId": "rubymod",
                "displayName": 'The "Ruby" Mod',
                "version": "1.0",
            }],
            "dependencies": [
                {"modId": "forge", "versionRange": "[49,)"},
                {"modId": "minecraft", "versionRange": "[1.21,)"},
            ],
        })
        self.assertIn('modLoader = "javafml"', text)
        self.assertIn("[mods]", text)
        self.assertIn('modId = "rubymod"', text)
        self.assertIn('\\"Ruby\\"', text)
        self.assertIn("[[dependencies]]", text)
        # round trip
        data = _toml_lite(text)
        self.assertEqual(data["modLoader"], "javafml")
        self.assertEqual(data["mods"][0]["modId"], "rubymod")
        self.assertEqual(data["dependencies"][1]["versionRange"], "[1.21,)")

    def test_arrays(self):
        text = dumps({"mixins": ["a.json", "b.json"], "empty": []})
        self.assertIn('mixins = ["a.json", "b.json"]', text)
        self.assertIn("empty = []", text)


class TomlReaderTests(unittest.TestCase):
    def test_reader_basic(self):
        text = """
modLoader = "javafml"
loaderVersion = "[49,)"
license = "MIT"

[[mods]]
modId = "rubymod"
version = "1.2.3"
displayName = "Ruby Mod"

[[dependencies.rubymod]]
modId = "forge"
versionRange = "[49,)"
"""
        data = _toml_lite(text)
        self.assertEqual(data["mods"][0]["modId"], "rubymod")
        self.assertEqual(data["dependencies"]["rubymod"][0]["modId"], "forge")


if __name__ == "__main__":
    unittest.main()
