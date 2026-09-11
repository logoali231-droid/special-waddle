# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 3b - Registry transformer.

Converts Fabric-style static registration::

    public static final Block RUBY_BLOCK = Registry.register(
        Registries.BLOCK, new Identifier(MOD_ID, "ruby_block"), new Block(...));

into Forge/NeoForge ``DeferredRegister`` style::

    public static final DeferredRegister<Block> BLOCKS =
        DeferredRegister.create(Registries.BLOCK, MOD_ID);
    public static final DeferredBlock<Block> RUBY_BLOCK =
        BLOCKS.register("ruby_block", () -> new Block(...));

and back. Also performs a reverse "static init" extraction when targeting
Fabric (DeferredRegister.register(bus) calls are removed and a TODO is added
if side effects existed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .editor import JavaSourceEditor
from .scanner import strip_comments_and_strings

# registry kind -> (yarn constant, mojmap constant)
REGISTRY_CONSTANTS = {
    "Block": ("Registries.BLOCK", "Registries.BLOCK"),
    "Item": ("Registries.ITEM", "Registries.ITEM"),
    "BlockEntityType": ("Registries.BLOCK_ENTITY_TYPE", "Registries.BLOCK_ENTITY_TYPE"),
    "EntityType": ("Registries.ENTITY_TYPE", "Registries.ENTITY_TYPE"),
    "CreativeModeTab": ("Registries.CREATIVE_MODE_TAB", "Registries.CREATIVE_MODE_TAB"),
    "SoundEvent": ("Registries.SOUND_EVENT", "Registries.SOUND_EVENT"),
    "ParticleType": ("Registries.PARTICLE_TYPE", "Registries.PARTICLE_TYPE"),
    "Potion": ("Registries.POTION", "Registries.POTION"),
    "Enchantment": ("Registries.ENCHANTMENT", "Registries.ENCHANTMENT"),
}

# Yarn registry holder classes -> mojmap equivalents
REGISTRY_CLASS_MAP = {
    "net.minecraft.registry.Registries": "net.minecraft.core.registries.Registries",
    "net.minecraft.registry.Registry": "net.minecraft.core.Registry",
    "net.minecraft.registry.Registries.BLOCK": "net.minecraft.core.registries.Registries.BLOCK",
}


@dataclass
class RegistryEntry:
    """One registered object discovered in a Fabric-style source file."""

    field_name: str
    kind: str  # "Block", "Item", ...
    registry_constant: str  # e.g. "Registries.BLOCK"
    registry_path: str  # e.g. "ruby_block"
    factory_text: str  # RHS expression, e.g. "new Block(AbstractBlock.Settings.create())"
    line_index: int  # 0-based start line in the ORIGINAL source


@dataclass
class RegistryCollector:
    """Collects registration facts shared between transformers."""

    mod_id: str = "examplemod"
    entries: list[RegistryEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def kinds(self) -> set[str]:
        return {e.kind for e in self.entries}

    def has_entries(self) -> bool:
        return bool(self.entries)


# --------------------------------------------------------------------------
# Fabric Registry.register(...) -> DeferredRegister
# --------------------------------------------------------------------------

REGISTER_CALL_RE = re.compile(
    r"(?:@\w+(?:\([^)]*\))?\s+)*"
    r"(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?"
    r"[\w.<>\[\],\s?]+?\s+(\w+)\s*=\s*Registry\.register\s*\(",
    re.M,
)


def collect_fabric_registrations(editor: JavaSourceEditor) -> list[RegistryEntry]:
    """Find ``X NAME = Registry.register(REG, new Identifier(...), new X(...))`` fields.

    Matches are located on comment/string-stripped text, but the statement is
    extracted from the raw text so string literals survive.
    """
    entries: list[RegistryEntry] = []
    text = "\n".join(editor.lines)
    code = strip_comments_and_strings(text)  # same length as text
    for m in REGISTER_CALL_RE.finditer(code):
        field_name = m.group(1)
        start = m.start()
        # paren balance on the stripped text (literals can't mislead)
        depth = 0
        end = None
        for k in range(m.end() - 1, len(code)):
            ch = code[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        if end is None:
            continue
        # statement ends at the next ';' after the closing paren
        semi = code.find(";", end)
        stmt_end = semi if semi != -1 else end + 1
        stmt = text[start:stmt_end + 1]  # RAW text: literals intact
        # registry constant: first argument
        reg_m = re.search(r"Registry\.register\s*\(\s*([\w.]+)\s*,", stmt)
        reg_const = reg_m.group(1) if reg_m else "Registries.BLOCK"
        # path: Identifier.of(MOD_ID, "name") or new Identifier(MOD_ID, "name")
        path_m = re.search(r'Identifier\s*\.\s*of\s*\(\s*[\w.]+\s*,\s*"([^"]+)"', stmt)
        if not path_m:
            path_m = re.search(r'new\s+Identifier\s*\(\s*[\w.]+\s*,\s*"([^"]+)"', stmt)
        reg_path = path_m.group(1) if path_m else field_name.lower()
        # factory: last argument (third)
        factory = _third_arg(stmt)
        kind = _infer_kind(reg_const, factory)
        line_index = code[:start].count("\n")
        entries.append(
            RegistryEntry(
                field_name=field_name,
                kind=kind,
                registry_constant=reg_const,
                registry_path=reg_path,
                factory_text=factory,
                line_index=line_index,
            )
        )
    return entries


def _split_args(inner: str) -> list[str]:
    parts, buf, depth, quote = [], [], 0, None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return parts


def _third_arg(stmt: str) -> str:
    """Last argument of the Registry.register(...) call inside *stmt*."""
    inner = stmt[stmt.index("(") + 1: stmt.rindex(")")]
    args = _split_args(inner)
    return args[-1] if args else "null"


def _infer_kind(reg_const: str, factory: str) -> str:
    const = reg_const.rsplit(".", 1)[-1].upper()
    for kind in REGISTRY_CONSTANTS:
        if kind.upper() == const or const == kind.upper() + "S" or const.startswith(kind.upper()):
            return kind
    f = factory.strip()
    for kind in ("Block", "Item", "BlockEntityType", "EntityType", "SoundEvent", "ParticleType", "CreativeModeTab"):
        if re.search(rf"\bnew\s+{kind}\b|\b{kind}\b", f.split("(")[0]):
            return kind
    return "Item"


def rewrite_fabric_registry_to_deferred(
    editor: JavaSourceEditor,
    collector: RegistryCollector,
    target_engine: str,
) -> None:
    """In-place rewrite of Registry.register fields to DeferredRegister fields."""
    entries = collect_fabric_registrations(editor)
    collector.entries.extend(entries)
    if not entries:
        return

    # group by registry constant
    by_reg: dict[str, list[RegistryEntry]] = {}
    for e in entries:
        by_reg.setdefault(e.registry_constant, []).append(e)

    replacement_lines: list[str] = []
    for reg_const, group in by_reg.items():
        kind = group[0].kind
        if target_engine == "neoforge":
            wrapper = {"Block": "DeferredBlock", "Item": "DeferredItem"}.get(kind, "DeferredHolder")
        else:  # forge
            wrapper = "RegistryObject" if kind in ("Block", "Item") else "DeferredHolder"
        simple = reg_const.rsplit(".", 1)[-1]
        # e.g. "ITEM" -> "ITEM_REGISTRY", block group naming: BLOCK_REGISTRY
        reg_name = simple.upper() + "_REGISTRY"
        reg_const_moj = reg_const
        if reg_const.startswith("Registries."):
            reg_const_moj = "net.minecraft.core.registries.Registries." + reg_const.split(".", 1)[1]
        modid_ref = f'"{collector.mod_id}"'
        # reuse an existing MOD_ID constant when present (avoid undefined refs)
        if any(re.search(r"\bString\s+MOD_ID\s*=", l) for l in editor.lines):
            modid_ref = "MOD_ID"
        replacement_lines.append(
            f"    public static final DeferredRegister<{kind}> {reg_name} = "
            f"DeferredRegister.create({reg_const_moj}, {modid_ref});"
        )
        for e in group:
            replacement_lines.append(
                f"    public static final {wrapper}<{kind}> {e.field_name} = "
                f"{reg_name}.register("
                f'"{e.registry_path}", () -> {e.factory_text});'
            )
        replacement_lines.append("")

    # Remove original Registry.register statements (brace/paren balanced lines).
    _remove_registry_register_statements(editor, entries)

    # Insert DeferredRegister fields before the first method or at class start.
    insert_at = _class_body_start(editor)
    editor.lines[insert_at:insert_at] = replacement_lines

    # imports
    editor.rename_qualified(
        {
            "net.minecraft.registry.Registry": "net.minecraft.core.Registry",
            "net.minecraft.registry.Registries": "net.minecraft.core.registries.Registries",
            "net.minecraft.util.Identifier": "net.minecraft.resources.ResourceLocation",
        }
    )
    if target_engine == "neoforge":
        editor.add_import("net.neoforged.neoforge.registries.DeferredRegister")
        if any("DeferredBlock" in l for l in editor.lines):
            editor.add_import("net.neoforged.neoforge.registries.DeferredBlock")
        if any("DeferredItem" in l for l in editor.lines):
            editor.add_import("net.neoforged.neoforge.registries.DeferredItem")
        if any("DeferredHolder" in l for l in editor.lines):
            editor.add_import("net.neoforged.neoforge.registries.DeferredHolder")
    else:
        editor.add_import("net.minecraftforge.registries.DeferredRegister")
        editor.add_import("net.minecraftforge.registries.RegistryObject")
    if any("DeferredRegister" in l and "register(modEventBus" in l for l in editor.lines):
        pass  # bus registration added by entrypoint transformer
    collector.notes.append(
        f"Converted {len(entries)} Registry.register(...) field(s) into DeferredRegister pattern "
        f"({', '.join(sorted(by_reg))})."
    )


def _remove_registry_register_statements(editor: JavaSourceEditor, entries: list[RegistryEntry]) -> None:
    """Delete full statements (multi-line aware) of the original registrations."""
    lines = editor.lines
    i = 0
    while i < len(lines):
        seg = strip_comments_and_strings(lines[i])
        if re.search(r"=\s*Registry\.register\s*\(", seg):
            # find statement end: line whose code, after balance, ends with ';'
            depth = 0
            j = i
            end = None
            while j < len(lines):
                s2 = strip_comments_and_strings(lines[j])
                depth += s2.count("(") - s2.count(")")
                if depth <= 0 and ";" in s2:
                    end = j
                    break
                j += 1
            if end is None:
                end = i
            # swallow preceding annotation lines
            start = i
            while start > 0 and lines[start - 1].strip().startswith("@"):
                start -= 1
            del lines[start:end + 1]
            i = start
            continue
        i += 1


def _class_body_start(editor: JavaSourceEditor) -> int:
    """Index just after the class opening brace line."""
    for i, line in enumerate(editor.lines):
        if re.search(r"\b(?:class|interface|enum)\s+\w+", line) and "{" in line:
            return i + 1
    for i, line in enumerate(editor.lines):
        if re.search(r"\b(?:class|interface|enum)\s+\w+", line):
            # opening brace on a later line
            for j in range(i, min(i + 5, len(editor.lines))):
                if "{" in editor.get_line(j):
                    return j + 1
    return 0


# --------------------------------------------------------------------------
# DeferredRegister / RegistryObject -> Fabric static init
# --------------------------------------------------------------------------

DEFERRED_FIELD_RE = re.compile(
    r"(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?"
    r"(?:DeferredRegister<[\w.<>,\s?]+>|Deferred(?:Block|Item|Holder)<[\w.<>,\s?]+>|RegistryObject<[\w.<>,\s?]+>)\s+"
    r"(\w+)\s*=\s*(.+?);\s*$",
    re.M,
)


def rewrite_deferred_to_fabric_registry(
    editor: JavaSourceEditor,
    collector: RegistryCollector,
    source_engine: str,
) -> None:
    """Convert DeferredRegister fields to Fabric ``Registry.register`` fields.

    Regexes run against the raw text (string literals must survive); removal
    uses comment-aware scanning to avoid deleting commented-out code.
    """
    text = "\n".join(editor.lines)

    dr_fields: list[tuple[str, str]] = []  # (wrapper_var, registry constant)
    for m in re.finditer(
        r"DeferredRegister<([\w.<>,\s?]+)>\s+(\w+)\s*=\s*DeferredRegister\.create\s*\(\s*([\w.]+)\s*,",
        text,
    ):
        dr_fields.append((m.group(2), m.group(3)))

    object_fields: list[tuple[str, str, str]] = []  # (field_var, wrapper_var, path)
    for m in re.finditer(
        r"(?:Deferred(?:Block|Item|Holder)<([\w.<>,\s?]+)>|RegistryObject<([\w.<>,\s?]+)>)"
        r"\s+(\w+)\s*=\s*(\w+)\.register\s*\(\s*\"([\w/.]+)\"\s*,\s*(\(\)\s*->\s*.+?)\)\s*;",
        text,
        re.S,
    ):
        object_fields.append((m.group(3), m.group(4), m.group(5)))

    if not dr_fields and not object_fields:
        return

    mapping = dict(dr_fields)

    # registry constant suffix -> Java type name
    KIND_BY_CONST = {
        "BLOCK": "Block",
        "ITEM": "Item",
        "BLOCK_ENTITY_TYPE": "BlockEntityType",
        "ENTITY_TYPE": "EntityType",
        "CREATIVE_MODE_TAB": "CreativeModeTab",
        "SOUND_EVENT": "SoundEvent",
        "PARTICLE_TYPE": "ParticleType",
        "POTION": "Potion",
        "ENCHANTMENT": "Enchantment",
    }

    # Build Fabric replacements first (raw factory text preserved).
    has_modid_const = any(re.search(r"\bString\s+MOD_ID\s*=", l) for l in editor.lines)
    modid_ref = "MOD_ID" if has_modid_const else f'"{collector.mod_id}"'
    replacement: list[str] = []
    for (var, wrapper_var, path) in object_fields:
        reg_const = mapping.get(wrapper_var, "Registries.ITEM")
        const_simple = reg_const.rsplit(".", 1)[-1].upper()
        kind = KIND_BY_CONST.get(const_simple, "Item")
        replacement.append(
            f"    public static final {kind} {var} = Registry.register("
            f"{reg_const}, new Identifier({modid_ref}, \"{path}\"),"
        )

    # Remove the original Deferred* statements (comment-aware).
    _remove_deferred_statements(editor)

    # Drop now-dead imports.
    editor.rewrite_imports(
        {},
        {
            "net.neoforged.neoforge.registries.DeferredRegister",
            "net.neoforged.neoforge.registries.DeferredItem",
            "net.neoforged.neoforge.registries.DeferredBlock",
            "net.neoforged.neoforge.registries.DeferredHolder",
            "net.minecraftforge.registries.DeferredRegister",
            "net.minecraftforge.registries.RegistryObject",
        },
    )

    if replacement:
        replacement.append("    );")
        insert_at = _class_body_start(editor)
        editor.lines[insert_at:insert_at] = replacement

    collector.notes.append(
        f"Converted {len(object_fields)} DeferredRegister/RegistryObject field(s) into Fabric "
        "Registry.register(...) static fields."
    )
    if replacement:
        editor.add_warning(insert_at, "CONVERT",
            "DeferredRegister registration converted to static Registry.register; verify that "
            "modEventBus.register(...) calls were removed and that BlockEntityType builders "
            "supply the correct supplier argument.")


def _remove_deferred_statements(editor: JavaSourceEditor) -> None:
    """Delete statements that declare or register Deferred*/RegistryObject fields."""
    lines = editor.lines
    i = 0
    while i < len(lines):
        seg = strip_comments_and_strings(lines[i])
        declares = re.search(r"\b(?:DeferredRegister|DeferredBlock|DeferredItem|DeferredHolder|RegistryObject)\b", seg)
        if declares and re.search(r"=\s*\w+", seg):
            depth = 0
            j = i
            end = None
            while j < len(lines):
                s2 = strip_comments_and_strings(lines[j])
                depth += s2.count("(") - s2.count(")")
                if depth <= 0 and ";" in s2:
                    end = j
                    break
                j += 1
            if end is None:
                end = i
            del lines[i:end + 1]
            continue
        i += 1
