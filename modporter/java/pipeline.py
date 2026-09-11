# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 3 - Code Transpilation pipeline.

Orchestrates all Java transformers in a deterministic order for each source
file and collects notes, fallback hits and per-file outputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.engines import EngineSpec, get_engine
from ..core.model import ProjectModel, SourceFile
from . import events, fallback, mixins, registry
from .editor import JavaSourceEditor
from .entrypoint import transform_fabric_to_ibus, transform_ibus_to_fabric
from .mappings import IMPORT_MAPS, MOJMAP_TO_YARN_WORDS, YARN_TO_MOJMAP_WORDS
from .scanner import JavaClassIndex, scan_sources


@dataclass
class TransformContext:
    """Shared context handed to every transformer."""

    source_engine: str
    target_engine: str
    source_spec: EngineSpec
    target_spec: EngineSpec
    metadata: object  # ModMetadata
    class_index: JavaClassIndex
    collector: registry.RegistryCollector
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TranspileResult:
    """Per-file transformation output."""

    files: dict[str, str] = field(default_factory=dict)  # rel path -> new text
    entry_file: str | None = None
    notes: list[str] = field(default_factory=list)
    fallback_messages: list[str] = field(default_factory=list)


def transpile(model: ProjectModel, target_engine: str) -> TranspileResult:
    """Transform every Java source for the target engine."""
    target_spec = get_engine(target_engine)
    source_spec = model.spec
    idx = scan_sources(model)
    collector = registry.RegistryCollector(mod_id=model.metadata.mod_id)
    ctx = TransformContext(
        source_engine=model.engine,
        target_engine=target_engine,
        source_spec=source_spec,
        target_spec=target_spec,
        metadata=model.metadata,
        class_index=idx,
        collector=collector,
    )
    result = TranspileResult()

    fabric_to_ibus = model.engine == "fabric" and target_engine in ("forge", "neoforge")
    ibus_to_fabric = model.engine in ("forge", "neoforge") and target_engine == "fabric"

    # Mapping direction: Yarn -> Mojmap or Mojmap -> Yarn.
    if source_spec.mapping_type != target_spec.mapping_type:
        word_map = YARN_TO_MOJMAP_WORDS if source_spec.mapping_type == "yarn" else MOJMAP_TO_YARN_WORDS
    else:
        word_map = {}

    entry_fqn = model.metadata.entrypoints.get("main", [])
    entry_simple = None
    for ep in entry_fqn:
        if "." in ep:
            entry_simple = ep.rsplit(".", 1)[-1]
            break

    for src in model.sources:
        editor = JavaSourceEditor(src.text, src.path)

        # --- 1. Entry class detection & lifecycle conversion ----------------
        is_entry = src.class_name == entry_simple or (
            src.package == "" and src.class_name.endswith("Init")  # heuristic fallback
        )
        if ibus_to_fabric and any(re.search(rf"^\s*@Mod\s*\(", l) for l in editor.lines):
            is_entry = True
        if fabric_to_ibus and is_entry:
            new_text, notes = transform_fabric_to_ibus(src, model.metadata, target_spec, collector)
            editor = JavaSourceEditor(new_text, src.path)
            result.notes.extend(notes)
            result.entry_file = src.path
        elif ibus_to_fabric and is_entry:
            new_text, notes = transform_ibus_to_fabric(src, model.metadata, target_spec, collector)
            editor = JavaSourceEditor(new_text, src.path)
            result.notes.extend(notes)
            result.entry_file = src.path

        # --- 2. Registry conversion ------------------------------------------
        if fabric_to_ibus:
            registry.rewrite_fabric_registry_to_deferred(editor, collector, target_engine)
        elif ibus_to_fabric:
            registry.rewrite_deferred_to_fabric_registry(editor, collector, model.engine)

        # --- 3. Event callbacks ----------------------------------------------
        if fabric_to_ibus:
            events.convert_fabric_callbacks_to_subscribe(editor, result.notes, target_engine)
        elif ibus_to_fabric:
            events.convert_subscribe_to_fabric_callbacks(editor, result.notes)

        # --- 4. Import remap --------------------------------------------------
        import_map = dict(IMPORT_MAPS.get(model.engine, {}))
        removed = set()
        if fabric_to_ibus:
            removed.add("net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents")
        if fabric_to_ibus:
            for fqn in ("net.fabricmc.api.ModInitializer", "net.fabricmc.api.ClientModInitializer",
                        "net.fabricmc.api.Environment", "net.minecraft.registry.Registry",
                        "net.minecraft.registry.Registries", "net.minecraft.util.Identifier"):
                import_map.setdefault(fqn, _default_target(fqn, target_engine))
            removed.add("net.fabricmc.api.ModInitializer")
            removed.add("net.fabricmc.api.ClientModInitializer")
            for fqn in ("net.minecraft.registry.Registry", "net.minecraft.registry.Registries"):
                import_map[fqn] = "net.minecraft.core.registries.Registries" if target_engine == "neoforge" else "net.minecraft.core.Registry"
        elif ibus_to_fabric:
            for fqn in ("net.neoforged.fml.common.Mod", "net.minecraftforge.fml.common.Mod",
                        "net.neoforged.bus.api.SubscribeEvent", "net.minecraftforge.eventbus.api.SubscribeEvent"):
                import_map.setdefault(fqn, "net.fabricmc.api.ModInitializer")
            removed.add("net.neoforged.fml.common.Mod")
            removed.add("net.minecraftforge.fml.common.Mod")

        editor.rewrite_imports(import_map, removed)

        # --- 5. In-body word remap (yarn<->mojmap simple names) --------------
        if word_map:
            editor.rename_words(word_map)

        # --- 6. Smart fallback scan (Capabilities vs Transfer API, mixins) ---
        stub_msgs = _stub_unconvertible_fabric_calls(editor, fabric_to_ibus)
        result.fallback_messages.extend(stub_msgs)
        report = fallback.scan_fallbacks(editor, model.engine)
        result.fallback_messages.extend(report.merged_messages())
        mixin_msgs = fallback.scan_mixin_refs(editor, model.mixin_configs if src is model.sources[0] else [])
        result.fallback_messages.extend(mixin_msgs)

        editor.dedupe_imports()
        result.files[src.path] = editor.text()

    # entry fallback: if no entrypoint declared in metadata, tag first @Mod class
    if target_engine in ("forge", "neoforge") and result.entry_file is None:
        for path, text in result.files.items():
            if re.search(r"^\s*@Mod\s*\(", text, re.M):
                result.entry_file = path
                break

    return result


def _stub_unconvertible_fabric_calls(editor: JavaSourceEditor, fabric_to_ibus: bool) -> list[str]:
    """Replace Fabric-specific call patterns that have no 1:1 mapping with
    TODO stubs instead of leaving broken code (Smart Fallback).

    Returns the messages emitted so the conversion report can list them.
    """
    if not fabric_to_ibus:
        return []
    text = "\n".join(editor.lines)
    if "ItemGroupEvents" not in text:
        return []
    # match  modifyEntriesEvent(REGISTRY).register(entries -> { ... })
    pattern = re.compile(
        r"(?P<indent>[ \t]*)ItemGroupEvents\.modifyEntriesEvent\s*\([^)]*\)\.register\s*\(\s*(?:\w+)\s*->\s*\{.*?\}\s*\)\s*;",
        re.S,
    )
    message = (
        "ItemGroupEvents.modifyEntriesEvent(...) has no direct equivalent here. "
        "Subscribe to BuildCreativeModeTabContentsEvent and call event.getEntries().accept(...)."
    )
    count = 0

    def _repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{m.group('indent')}// TODO: [CONVERT] {message}"

    new_text = pattern.sub(_repl, text)
    if count:
        editor.lines[:] = new_text.splitlines()
        return [message]
    return []


def _default_target(fqn: str, target_engine: str) -> str:
    table = {
        "net.fabricmc.api.ModInitializer": get_engine(target_engine).loader_class,
        "net.fabricmc.api.ClientModInitializer": "net.neoforged.api.distmarker.OnlyIn",
        "net.fabricmc.api.Environment": "net.neoforged.api.distmarker.OnlyIn",
        "net.minecraft.registry.Registry": "net.minecraft.core.Registry",
        "net.minecraft.registry.Registries": "net.minecraft.core.registries.Registries",
        "net.minecraft.util.Identifier": "net.minecraft.resources.ResourceLocation",
    }
    return table.get(fqn, fqn)
