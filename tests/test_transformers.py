# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Tests for the Java transformers (entrypoint, registry, events, fallback)."""
import re
import unittest

from modporter.core.engines import get_engine
from modporter.core.model import Dependency, ModMetadata
from modporter.java.editor import JavaSourceEditor
from modporter.java.entrypoint import transform_fabric_to_ibus, transform_ibus_to_fabric
from modporter.java.fallback import scan_fallbacks
from modporter.java.registry import (
    RegistryCollector,
    rewrite_deferred_to_fabric_registry,
    rewrite_fabric_registry_to_deferred,
)

FABRIC_ENTRY = '''package com.example.rubymod;

import net.fabricmc.api.ModInitializer;
import net.minecraft.item.Item;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;

public class RubyMod implements ModInitializer {
    public static final String MOD_ID = "rubymod";

    public static final Item RUBY = Registry.register(
        Registries.ITEM,
        new Identifier(MOD_ID, "ruby"),
        new Item(new Item.Settings())
    );

    @Override
    public void onInitialize() {
        System.out.println("hello");
    }
}
'''

NEO_ENTRY = '''package com.example.rubymod;

import net.neoforged.fml.common.Mod;
import net.neoforged.bus.api.IEventBus;

@Mod("rubymod")
public class RubyMod {
    public static final String MOD_ID = "rubymod";

    public RubyMod(IEventBus modEventBus) {
        System.out.println("hello");
    }
}
'''


def _meta() -> ModMetadata:
    meta = ModMetadata(mod_id="rubymod", name="Ruby Mod", version="1.0.0")
    meta.entrypoints = {"main": ["com.example.rubymod.RubyMod"]}
    return meta


class EntrypointTests(unittest.TestCase):
    def test_fabric_to_neoforge(self):
        src_text, notes = transform_fabric_to_ibus(
            _src(FABRIC_ENTRY), _meta(), get_engine("neoforge"), None
        )
        self.assertIn('@Mod("rubymod")', src_text)
        self.assertNotIn("implements ModInitializer", src_text)
        self.assertIn("public RubyMod()", src_text)
        self.assertIn('System.out.println("hello")', src_text)
        self.assertNotIn("import net.fabricmc.api.ModInitializer;", src_text)
        self.assertIn("import net.neoforged.fml.common.Mod;", src_text)
        self.assertTrue(notes)

    def test_neoforge_to_fabric(self):
        src_text, notes = transform_ibus_to_fabric(
            _src(NEO_ENTRY), _meta(), get_engine("fabric"), None
        )
        self.assertIn("implements ModInitializer", src_text)
        self.assertIn("public void onInitialize()", src_text)
        self.assertIn('System.out.println("hello")', src_text)
        self.assertNotIn("@Mod(", src_text)
        self.assertNotIn("import net.neoforged.fml.common.Mod;", src_text)
        self.assertIn("import net.fabricmc.api.ModInitializer;", src_text)


class RegistryTests(unittest.TestCase):
    def test_fabric_registry_to_deferred(self):
        editor = JavaSourceEditor(FABRIC_ENTRY, "RubyMod.java")
        collector = RegistryCollector(mod_id="rubymod")
        rewrite_fabric_registry_to_deferred(editor, collector, "neoforge")
        text = editor.text()
        self.assertIn("DeferredRegister", text)
        self.assertIn('ITEM_REGISTRY.register("ruby"', text)
        self.assertIn("DeferredItem<Item> RUBY", text)
        # the old static registration must be gone
        self.assertNotIn("= Registry.register(", text)
        self.assertEqual(len(collector.entries), 1)
        self.assertIn("Converted 1", " ".join(collector.notes))

    def test_deferred_to_fabric(self):
        neo_src = '''package com.example;

import net.neoforged.neoforge.registries.DeferredRegister;
import net.neoforged.neoforge.registries.DeferredItem;
import net.minecraft.world.item.Item;
import net.minecraft.core.registries.Registries;

public class ModItems {
    public static final DeferredRegister<Item> ITEMS = DeferredRegister.create(Registries.ITEM, "rubymod");
    public static final DeferredItem<Item> RUBY = ITEMS.register("ruby", () -> new Item(new Item.Properties()));
}
'''
        editor = JavaSourceEditor(neo_src, "ModItems.java")
        collector = RegistryCollector(mod_id="rubymod")
        rewrite_deferred_to_fabric_registry(editor, collector, "neoforge")
        text = editor.text()
        self.assertIn("Registry.register(", text)
        self.assertIn("Identifier(", text)
        self.assertNotIn("DeferredRegister.create", text)


class FallbackTests(unittest.TestCase):
    def test_transfer_api_warns(self):
        src = '''package com.example;

import net.fabricmc.fabric.api.transfer.v1.item.ItemStorage;

public class EnergyThing {
    long x = EnergyStorageUtil.getStored(null);
}
'''
        editor = JavaSourceEditor(src, "EnergyThing.java")
        report = scan_fallbacks(editor, "fabric")
        text = editor.text()
        # both the import line and the code line trigger the (distinct) patterns
        self.assertEqual(len(report.hits), 2)
        self.assertIn("// TODO: [CONVERT]", text)
        self.assertIn("Capabilities", text)
        # the dead import must be replaced, not kept
        self.assertNotIn("import net.fabricmc.fabric.api.transfer", text)

    def test_capability_warns_on_fabric_target(self):
        src = '''package com.example;

import net.minecraftforge.common.capabilities.CapabilityManager;

public class CapThing {
}
'''
        editor = JavaSourceEditor(src, "CapThing.java")
        report = scan_fallbacks(editor, "forge")
        self.assertEqual(len(report.hits), 1)
        self.assertIn("Transfer API", editor.text())


def _src(text: str):
    from modporter.core.model import SourceFile
    return SourceFile(path="RubyMod.java", package="com.example.rubymod", class_name="RubyMod", text=text)


if __name__ == "__main__":
    unittest.main()
