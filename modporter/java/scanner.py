# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Lightweight Java source scanning and surgical source editing.

ModPorter deliberately avoids heavyweight Java parsers (no javalang dependency).
Instead it combines:

- :class:`JavaClassIndex` -- symbol table of every scanned class
  (imports, fields, method names, annotation lines),
- :class:`JavaSourceEditor` -- line-based editing that tracks deleted
  imports and performs brace-balanced block deletion.

This "smart text" approach keeps the tool stdlib-only while still being
robust for the well-formed generated mod code it targets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- utilities

PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?([\w.*]+)\s*;", re.M)
WORD_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


def strip_comments_and_strings(text: str) -> str:
    """Return *text* with comments and string/char literals blanked out.

    Newlines are preserved so line/column structure stays intact. Used by
    heuristics that must not match inside literals.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            if j == -1:
                break
            out.append(" " * (j - i))
            i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            seg = text[i:j]
            out.append("".join(ch if ch == "\n" else " " for ch in seg))
            i = j
        elif c == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            j = min(j + 1, n)
            out.append('"' + " " * (j - i - 2) + '"')
            i = j
        elif c == "'":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            j = min(j + 1, n)
            out.append("'" + " " * (j - i - 2) + "'")
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def method_name_of(decl: str) -> str | None:
    """Extract the method name from a declaration line."""
    name = re.search(r"([A-Za-z_$][\w$]*)\s*\(", decl)
    return name.group(1) if name else None


def find_method_blocks(src: str, name: str) -> list[tuple[int, int, str]]:
    """Find complete method/constructor blocks called *name*.

    Returns list of (start_line_0, end_line_exclusive, block_text). A block
    starts at the line whose stripped text starts with ``name(`` or matches
    ``... name( ... )`` and ends at the matching closing brace.
    """
    lines = src.splitlines()
    blocks: list[tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        m = re.match(rf"^(?:@\w+(?:\([^)]*\))?\s+)*?(?:public|private|protected|static|final)?\s*[\w<>\[\],\s]*\b{name}\s*\(", stripped)
        if not m and not stripped.startswith(f"{name}("):
            i += 1
            continue
        # find opening brace within next few lines
        j = i
        brace_line = None
        while j < min(i + 6, len(lines)):
            if "{" in lines[j]:
                brace_line = j
                break
            if ";" in lines[j] and j != i:
                break
            j += 1
        if brace_line is None:
            i += 1
            continue
        # brace balance from brace_line
        depth = 0
        k = brace_line
        end = None
        while k < len(lines):
            seg = strip_comments_and_strings(lines[k])
            depth += seg.count("{") - seg.count("}")
            if depth == 0 and "{" in "".join(lines[brace_line:k + 1]):
                end = k
                break
            k += 1
        if end is None:
            i += 1
            continue
        blocks.append((i, end + 1, "\n".join(lines[i:end + 1])))
        i = end + 1
    return blocks


def remove_method_blocks(src: str, name: str) -> tuple[str, list[str]]:
    """Remove every method block named *name*; return (new_src, removed_texts)."""
    blocks = find_method_blocks(src, name)
    if not blocks:
        return src, []
    lines = src.splitlines()
    removed: list[str] = []
    for start, end, text in sorted(blocks, reverse=True):
        removed.append(text)
        # also swallow directly preceding annotations lines
        s = start
        while s > 0 and lines[s - 1].strip().startswith("@"):
            s -= 1
        del lines[s:end]
    return "\n".join(lines) + ("\n" if src.endswith("\n") else ""), removed


def qualified_split(fqn: str) -> tuple[str, str]:
    """Split a fully qualified name into (package, simple)."""
    if "." in fqn:
        pkg, _, cls = fqn.rpartition(".")
        return pkg, cls
    return "", fqn


# ---------------------------------------------------------------- index


@dataclass
class ClassInfo:
    """Scanned facts about one Java source file."""

    path: str
    package: str
    name: str
    fqn: str
    text: str
    imports: list[str] = field(default_factory=list)
    extends: str | None = None
    implements: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)


@dataclass
class JavaClassIndex:
    """Symbol table for all scanned classes."""

    classes: list[ClassInfo] = field(default_factory=list)

    def by_fqn(self) -> dict[str, ClassInfo]:
        return {c.fqn: c for c in self.classes}

    def simple_names(self) -> set[str]:
        return {c.name for c in self.classes}

    def find_simple(self, name: str) -> ClassInfo | None:
        for c in self.classes:
            if c.name == name:
                return c
        return None


def scan_class(text: str, path: str, package: str, class_name: str) -> ClassInfo:
    """Scan a single Java file into a :class:`ClassInfo`."""
    code = strip_comments_and_strings(text)
    info = ClassInfo(path=path, package=package, name=class_name, fqn=f"{package}.{class_name}" if package else class_name, text=text)
    info.imports = [m.group(2) for m in IMPORT_RE.finditer(text)]
    annos = []
    for line in code.splitlines():
        s = line.strip()
        if s.startswith("@"):
            m = re.match(r"@([\w.]+)", s)
            if m:
                annos.append(m.group(1))
    info.annotations = annos
    em = re.search(r"(?:class|interface|enum)\s+" + re.escape(class_name) + r"(?:<[^>]*>)?\s+extends\s+([\w.]+)", code)
    info.extends = em.group(1) if em else None
    im = re.search(r"(?:class|interface|enum)\s+" + re.escape(class_name) + r"(?:<[^>]*>)?[^{;]*\bimplements\s+([^{;]+)", code)
    if im:
        info.implements = [x.strip().split("<")[0] for x in im.group(1).split(",") if x.strip()]
    fm = re.search(r"(?:class|enum)\s+" + re.escape(class_name) + r"(?:<[^>]*>)?[^{;]*\{", code)
    body_start = fm.end() if fm else 0
    # fields: lines like `public static final Block FOO;` or `= ...;`
    for m in re.finditer(
        r"^\s*(?:@[\w.]+(?:\([^;{]*\))?\s+)*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?([\w.<>\[\],\s]+?)\s+(\w+)\s*(?:=[^;]*)?;",
        code[body_start:],
        re.M,
    ):
        ftype, fname = m.group(1).strip(), m.group(2)
        if ftype in ("return", "new", "else", "throw"):
            continue
        if "(" in ftype or ")" in ftype:
            continue
        info.fields.append(fname)
    for m in re.finditer(r"^\s*(?:public|protected|private|static|final|synchronized|native|abstract|\s)*[\w<>\[\],\s]+\s(\w+)\s*\([^;{)]*\)\s*(?:throws [\w,\s]+)?\{", code, re.M):
        name = m.group(1)
        if name not in ("if", "for", "while", "switch", "catch", "synchronized", "new", "return", "do"):
            info.methods.append(name)
    return info


def scan_sources(model) -> JavaClassIndex:
    """Scan every source in *model* and return the class index."""
    idx = JavaClassIndex()
    for src in model.sources:
        idx.classes.append(scan_class(src.text, src.path, src.package, src.class_name))
    return idx
