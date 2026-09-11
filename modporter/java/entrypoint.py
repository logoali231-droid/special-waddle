# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 3a - Entrypoint transformer.

Converts between the Fabric entrypoint pattern and the Forge/NeoForge ``@Mod``
pattern:

- Fabric -> Forge/NeoForge: ``implements ModInitializer`` +
  ``public static void onInitialize()`` becomes a class annotated with
  ``@Mod("modid")`` whose constructor (optionally taking ``IEventBus``)
  contains the old body.
- Forge/NeoForge -> Fabric: the ``@Mod`` annotated class keeps its methods,
  gains ``implements ModInitializer`` and its constructor body moves into
  ``public static void onInitialize()``; a fabric.mod.json entrypoints entry
  is added by the project generator.
"""
from __future__ import annotations

import re

from ..core.model import ModMetadata, SourceFile
from .editor import JavaSourceEditor
from .scanner import find_method_blocks, strip_comments_and_strings


def _class_decl_line(editor: JavaSourceEditor, class_name: str) -> int | None:
    for i, line in enumerate(editor.lines):
        if re.search(r"\b(?:class|interface|enum)\s+" + re.escape(class_name) + r"\b", line):
            return i
    return None


def transform_fabric_to_ibus(
    source: SourceFile,
    meta: ModMetadata,
    target_spec,
    collector=None,
) -> tuple[str, list[str]]:
    """Convert a Fabric ModInitializer class to Forge/NeoForge ``@Mod`` style.

    Returns ``(new_text, notes)`` where *notes* are human-readable messages
    for the conversion report.
    """
    editor = JavaSourceEditor(source.text, source.path)
    notes: list[str] = []
    mod_id = meta.mod_id

    # 0. Keep the client-entrypoint note with the code: add it AFTER class
    #    construction below (needs the class line index). No top-of-file comment.

    # 1. Tag the class with @Mod("modid")
    class_line = _class_decl_line(editor, source.class_name)
    if class_line is not None:
        indent = re.match(r"\s*", editor.get_line(class_line)).group(0)
        editor.insert_before(class_line, f"{indent}@Mod(\"{mod_id}\")")
        editor.add_import(target_spec.loader_class)

    # 2. Drop `implements ModInitializer` (and Client variant) from the class decl.
    for i, line in enumerate(list(editor.lines)):
        if "class " in line and "implements" in line:
            new_line = line
            new_line = re.sub(r"\s*implements\s+[^{]*\bClientModInitializer\b[^{]*", "", new_line)
            new_line = re.sub(r"\s*implements\s+[^{]*\bModInitializer\b[^{]*", "", new_line)
            if "implements" in new_line:
                # other interfaces remain: clean up dangling commas
                new_line = re.sub(r"implements\s+,\s*", "implements ", new_line)
                new_line = re.sub(r",\s*\{", " {", new_line)
            # normalize exactly one space before '{' ("RubyMod    {"/"RubyMod{" -> "RubyMod {")
            new_line = re.sub(r"\s*\{", " {", new_line, count=1)
            if new_line != line:
                editor.replace_line(i, new_line)
    editor.rewrite_imports(
        {},
        {
            "net.fabricmc.api.ModInitializer",
            "net.fabricmc.api.ClientModInitializer",
            "net.fabricmc.api.Environment",
        },
    )

    # 3. onInitialize -> constructor.
    blocks = find_method_blocks(source.text, "onInitialize")
    if blocks:
        first_start, first_end, first_text = blocks[0]
        body = editor.reindent(_method_body_lines(first_text), "        ")
        ctor = [f"    public {source.class_name}() {{"]
        ctor.append("        // ModPorter: Fabric onInitialize() converted to @Mod constructor.")
        ctor.extend(body)
        ctor.append("    }")
        editor.lines[first_start:first_end] = ctor
        notes.append(
            f"{source.class_name}.onInitialize() converted to {source.class_name}() constructor "
            "(plain constructor; the constructor with IEventBus is preferred for event registration)."
        )
        for (s, e, _t) in reversed(blocks[1:]):
            del editor.lines[s:e]
    else:
        editor.add_warning(0, "INFO", "No onInitialize() method found; add mod construction logic to the @Mod constructor.")

    # 4. ClientModInitializer-style entrypoints declared in fabric.mod.json.
    #    Notes go directly above the @Mod annotation so they stay attached.
    note_block: list[str] = []
    for ep in meta.entrypoints.get("client", []):
        if "::" in ep:
            note_block.append(
                f"// TODO: [CONVERT] Fabric client entrypoint '{ep}' was kept as a plain method; "
                f"annotate client-only logic with @OnlyIn(Dist.CLIENT) and call it from the constructor."
            )
        elif "." in ep:
            note_block.append(
                f"// TODO: [CONVERT] Fabric client entrypoint class '{ep}' is not auto-converted; "
                f"move its logic into a client setup (@EventBusSubscriber(modid={mod_id}, value=Dist.CLIENT)) class."
            )
        else:
            note_block.append(f"// NOTE: [MODPORTER] Client entrypoint '{ep}' referenced but not found in source.")
    if note_block:
        # place above @Mod if present, else above the class declaration
        anno_line = editor.line_no(lambda l: re.match(r"^\s*@Mod\s*\(", l))
        target_line = anno_line if anno_line is not None else _class_decl_line(editor, source.class_name)
        if target_line is not None:
            editor.insert_before(target_line, "\n".join(note_block))
        notes.extend(
            n.replace("// TODO: [CONVERT] ", "").replace("// NOTE: [MODPORTER] ", "").strip()
            for n in note_block
        )

    # 5. Server lifecycle methods commonly paired with Fabric entrypoints.
    for name in ("onInitializeServer", "onInitializeClient"):
        found = find_method_blocks(source.text, name)
        for (s, e, _t) in reversed(found):
            editor.add_warning(s, "CONVERT", f"{name}() has no direct Forge/NeoForge equivalent; "
                                              f"move logic into the constructor or an @EventBusSubscriber class.")
    return editor.text(), notes


def transform_ibus_to_fabric(
    source: SourceFile,
    meta: ModMetadata,
    target_spec,
    collector=None,
) -> tuple[str, list[str]]:
    """Convert a Forge/NeoForge ``@Mod`` class into a Fabric ModInitializer."""
    editor = JavaSourceEditor(source.text, source.path)
    notes: list[str] = []
    mod_id = meta.mod_id

    # 1. Remove the @Mod annotation and its import. The *source* loader class
    # depends on where the file came from (forge or neoforge), not the target.
    source_loader_classes = {
        "net.neoforged.fml.common.Mod",
        "net.minecraftforge.fml.common.Mod",
    }
    for i, line in enumerate(list(editor.lines)):
        if re.match(r"^\s*@Mod\s*\(", line):
            editor.delete_line(i)
    editor.rewrite_imports({}, source_loader_classes)
    if any("Dist.CLIENT" in l for l in editor.lines):
        editor.add_import("net.fabricmc.api.Environment")

    # 2. Add `implements ModInitializer` to the class declaration (short name).
    editor.add_import("net.fabricmc.api.ModInitializer")
    class_line = _class_decl_line(editor, source.class_name)
    if class_line is not None:
        line = editor.get_line(class_line)
        if "implements" in line:
            line = re.sub(r"\bimplements\s+", "implements ModInitializer, ", line, count=1)
        elif "{" in line:
            line = line.replace("{", "implements ModInitializer {", 1)
        editor.replace_line(class_line, line)

    # 3. Constructor -> onInitialize (static) or keep constructor + call from onInitialize.
    ctor_blocks = find_method_blocks(source.text, source.class_name)
    if ctor_blocks:
        (cs, ce, ct) = ctor_blocks[0]
        body = _method_body_lines(ct)
        init = ["    @Override", "    public void onInitialize() {"]
        init.append("        // ModPorter: @Mod constructor converted to Fabric onInitialize().")
        init.extend(f"        {b}" if b.strip() else "" for b in body)
        init.append("    }")
        editor.lines[cs:ce] = init
        notes.append("@Mod constructor converted to onInitialize().")
        # remove remaining constructors
        for (s, e, _t) in reversed(ctor_blocks[1:]):
            del editor.lines[s:e]
    else:
        init_block = [
            "    @Override",
            "    public void onInitialize() {",
            f"        // TODO: [CONVERT] Move {mod_id} initialization from the removed @Mod constructor here.",
            "    }",
        ]
        # insert after class opening brace
        class_line = _class_decl_line(editor, source.class_name)
        if class_line is not None:
            depth = 0
            for j in range(class_line, len(editor.lines)):
                depth += editor.get_line(j).count("{") - editor.get_line(j).count("}")
                if depth >= 1:
                    editor.insert_after(j, "\n".join(init_block))
                    break
        else:
            editor.lines.extend(init_block)

    # 4. Note about client-only code (DistExecutor / OnlyIn).
    for i, line in enumerate(editor.lines):
        if "DistExecutor" in line or "OnlyIn" in line or "Dist.CLIENT" in line:
            editor.add_warning(i, "CONVERT", "DistExecutor/@OnlyIn client-only code has no Fabric equivalent; "
                                             "use a ClientModInitializer declared in fabric.mod.json.")
            break

    return editor.text(), notes


def _method_body_lines(method_text: str) -> list[str]:
    """Return body lines (without signature/braces) of a method block.

    Only the method's OWN closing brace is dropped; nested block closers
    (e.g. an ``if`` at the end) must survive to keep the body balanced.
    """
    lines = method_text.splitlines()
    start = next((i for i, l in enumerate(lines) if "{" in l), 0)
    body = lines[start + 1:]
    if body and body[-1].strip() == "}":
        body.pop()
    return body
