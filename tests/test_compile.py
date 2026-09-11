# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Compile-order regression: generated fields must not forward-reference.

Full ``javac`` of generated files needs the Minecraft classpath, so the lock
is structural: the injected ``DeferredRegister`` fields must come *after*
the ``MOD_ID``/``LOGGER`` constants in the class body (Java's illegal
forward reference), plus a standalone skeleton proving javac accepts the
emitted ordering pattern.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from modporter.core.generator import convert_project
from modporter.core.reader import read_project
from modporter.java.editor import JavaSourceEditor
from modporter.java.registry import (
    RegistryCollector,
    rewrite_fabric_registry_to_deferred,
)

FABRIC_MAIN = """package com.example.rubymod;

import net.fabricmc.api.ModInitializer;
import net.minecraft.block.Block;
import net.minecraft.item.Item;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RubyMod implements ModInitializer {
    public static final String MOD_ID = "rubymod";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    public static final Block RUBY_BLOCK = Registry.register(
        Registries.BLOCK, new Identifier(MOD_ID, "ruby_block"), new Block(
            AbstractBlock.Settings.create().strength(4.0f)));
    public static final Item RUBY = Registry.register(
        Registries.ITEM, new Identifier(MOD_ID, "ruby"), new Item(
            new Item.Settings()));

    @Override
    public void onInitialize() {
        LOGGER.info("RubyMod initialized");
    }
}
"""

SKELETON = """class Order {
    public static final String MOD_ID = "x";
    public static final java.util.logging.Logger LOGGER =
        java.util.logging.Logger.getLogger(MOD_ID);
    public static final java.util.List<String> REGISTRY =
        java.util.Arrays.asList(MOD_ID, LOGGER.getName());
}
"""

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "fabric-mod"


class TestFieldOrdering(unittest.TestCase):
    def _editor(self, target: str) -> JavaSourceEditor:
        editor = JavaSourceEditor(FABRIC_MAIN)
        collector = RegistryCollector(mod_id="rubymod")
        rewrite_fabric_registry_to_deferred(editor, collector, target)
        return editor

    def _class_body(self, editor: JavaSourceEditor) -> list[str]:
        lines = editor.lines
        start = next(i for i, l in enumerate(lines) if "class " in l and "{" in l)
        return lines[start + 1:]

    def _field_order(self, editor: JavaSourceEditor) -> list[str]:
        order: list[str] = []
        for line in self._class_body(editor):
            s = line.strip()
            if s.startswith("public static final String MOD_ID"):
                order.append("MOD_ID")
            elif s.startswith("public static final Logger LOGGER"):
                order.append("LOGGER")
            elif "DeferredRegister<" in s:
                order.append("DeferredRegister")
        return order

    def test_neoforge_constants_precede_deferred_register(self) -> None:
        order = self._field_order(self._editor("neoforge"))
        self.assertIn("DeferredRegister", order)
        self.assertLess(
            order.index("MOD_ID"), order.index("DeferredRegister"),
            f"MOD_ID must precede DeferredRegister, got {order}",
        )

    def test_forge_constants_precede_deferred_register(self) -> None:
        order = self._field_order(self._editor("forge"))
        self.assertLess(
            order.index("MOD_ID"), order.index("DeferredRegister"),
            f"MOD_ID must precede DeferredRegister, got {order}",
        )

    def test_generated_main_class_has_legal_field_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            convert_project(read_project(SAMPLE, engine="fabric"), "neoforge", out)
            main = out / "src/main/java/com/example/rubymod/RubyMod.java"
            text = main.read_text(encoding="utf-8")
            body = text[text.index("public class RubyMod"):]
            self.assertLess(
                body.index('String MOD_ID ='),
                body.index("DeferredRegister<"),
                "MOD_ID constant must be declared before the DeferredRegister fields",
            )


class TestSkeletonCompiles(unittest.TestCase):
    def test_skeleton_ordering_is_valid_java(self) -> None:
        javac = shutil.which("javac")
        if not javac:
            self.skipTest("javac not available")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "Order.java"
            src.write_text(SKELETON, encoding="utf-8")
            proc = subprocess.run(
                [javac, str(src)], capture_output=True, text=True, cwd=td
            )
            self.assertEqual(
                proc.returncode, 0,
                f"skeleton must compile: {proc.stderr}",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
