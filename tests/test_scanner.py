# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Tests for the Java scanner utilities."""
import unittest

from modporter.java.scanner import (
    find_method_blocks,
    remove_method_blocks,
    scan_class,
    strip_comments_and_strings,
)


SRC = '''
package com.example;

import net.fabricmc.api.ModInitializer;

public class Demo implements ModInitializer {
    // Registry.register inside a string must not match: "Registry.register"
    public static final Block A = Registry.register(Registries.BLOCK,
        new Identifier("demo", "a"), new Block(Settings.create()));

    @Override
    public void onInitialize() {
        System.out.println("onInitialize");
        if (x > 0) {
            System.out.println("nested { braces }");
        }
    }

    private int helper(int v) { return v * 2; }
}
'''


class ScannerTests(unittest.TestCase):
    def test_strip_comments_and_strings(self):
        code = strip_comments_and_strings(SRC)
        # the string literal mentioning Registry.register must be blanked
        self.assertNotIn('"Registry.register', code)
        # the real registration line stays (outside the string)
        self.assertIn("public static final Block A = Registry.register", code)
        self.assertIn("public class Demo", code)

    def test_find_method_blocks(self):
        blocks = find_method_blocks(SRC, "onInitialize")
        self.assertEqual(len(blocks), 1)
        start, end, text = blocks[0]
        self.assertIn("onInitialize", text)
        self.assertIn("nested", text)
        self.assertTrue(text.strip().endswith("}"))

    def test_remove_method_blocks(self):
        new_src, removed = remove_method_blocks(SRC, "helper")
        self.assertEqual(len(removed), 1)
        self.assertNotIn("helper(int", new_src)
        self.assertIn("onInitialize", new_src)

    def test_scan_class(self):
        info = scan_class(SRC, "Demo.java", "com.example", "Demo")
        self.assertEqual(info.fqn, "com.example.Demo")
        self.assertIn("net.fabricmc.api.ModInitializer", info.imports)
        self.assertIn("ModInitializer", info.implements)
        self.assertIn("A", info.fields)
        self.assertIn("onInitialize", info.methods)
        self.assertIn("Override", info.annotations)


if __name__ == "__main__":
    unittest.main()
