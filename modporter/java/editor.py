# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 2a - Java source editing primitives.

:class:`JavaSourceEditor` performs safe, line-oriented transformations:

- rewriting the ``package`` statement and the ``import`` block,
- renaming identifiers and qualified names,
- brace-balanced removal of whole methods (incl. attached annotations),
- in-place insertion of structured warning comments (Smart Fallback).

All operations mutate ``self.lines`` immediately, so line indices gathered
from the *current* state are always valid (the first version deferred edits
and corrupted unrelated lines).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .scanner import strip_comments_and_strings

IMPORT_LINE_RE = re.compile(r"^(\s*)import\s+(static\s+)?([\w.*]+)\s*;(.*)$")


@dataclass
class SourceIssue:
    """A warning/TODO emitted during transformation."""

    kind: str  # "CONVERT" | "INFO"
    path: str
    line: int  # 1-based line in the output file
    message: str


class JavaSourceEditor:
    """Line-oriented editor over a single Java file."""

    def __init__(self, text: str, path: str = "<memory>") -> None:
        self.path = path
        self.lines: list[str] = text.splitlines()
        self._deleted_imports: list[str] = []
        self.issues: list[SourceIssue] = []

    # -- basic ops ---------------------------------------------------------

    def text(self) -> str:
        self._dedupe_imports()
        return "\n".join(self.lines) + ("\n" if self.lines else "")

    def _dedupe_imports(self) -> None:
        """Drop duplicate (and blanked) import lines, keeping first occurrences."""
        seen: set[str] = set()
        drop: list[int] = []
        for i, line in enumerate(self.lines):
            m = IMPORT_LINE_RE.match(line)
            if m:
                key = (m.group(3), bool(m.group(2)))
                if key in seen:
                    drop.append(i)
                else:
                    seen.add(key)
        for i in reversed(drop):
            del self.lines[i]

    def line_no(self, pred) -> int | None:
        """0-based index of the first line matching *pred*, else None."""
        for i, line in enumerate(self.lines):
            if pred(line):
                return i
        return None

    def get_line(self, index: int) -> str:
        return self.lines[index]

    def replace_line(self, index: int, new: str) -> None:
        self.lines[index] = new

    def insert_after(self, index: int, text: str) -> None:
        self.lines[index + 1:index + 1] = text.splitlines()

    def insert_before(self, index: int, text: str) -> None:
        self.lines[index:index] = text.splitlines()

    def delete_line(self, index: int) -> None:
        del self.lines[index]

    # -- package / imports -------------------------------------------------

    def set_package(self, new_package: str) -> None:
        for i, line in enumerate(self.lines):
            if re.match(r"^\s*package\s+[\w.]+\s*;", line):
                self.lines[i] = f"package {new_package};"
                return
        self.insert_before(0, f"package {new_package};")
        self.insert_before(1, "")

    def rewrite_imports(self, mapping: dict[str, str], removed: set[str] | None = None) -> None:
        """Rewrite import lines: exact FQN replacements and deletions.

        Safe against concurrent index shifts because each line is rewritten
        in place (never deleted here); deleted imports are blanked and
        compacted in a single final pass.
        """
        removed = removed or set()
        blank_idx: list[int] = []
        for i, line in enumerate(self.lines):
            m = IMPORT_LINE_RE.match(line)
            if not m:
                continue
            indent, static_kw, fqn, comment = m.groups()
            if fqn in removed:
                self._deleted_imports.append(fqn)
                blank_idx.append(i)
                continue
            new_fqn = mapping.get(fqn, fqn)
            if new_fqn != fqn:
                self.lines[i] = f"{indent}import {static_kw or ''}{new_fqn};{comment if comment.strip() else ''}"
        for i in reversed(blank_idx):
            del self.lines[i]

    def deleted_imports(self) -> list[str]:
        return list(self._deleted_imports)

    def dedupe_imports(self) -> int:
        """Remove duplicate import lines; return how many were dropped."""
        seen: set[str] = set()
        drop: list[int] = []
        for i, line in enumerate(self.lines):
            m = IMPORT_LINE_RE.match(line)
            if not m:
                continue
            key = (m.group(2) or "") + m.group(3)
            if key in seen:
                drop.append(i)
            else:
                seen.add(key)
        for i in reversed(drop):
            del self.lines[i]
        return len(drop)

    @staticmethod
    def reindent(body_lines: list[str], base: str = "        ") -> list[str]:
        """Normalize indentation of *body_lines* to *base* + relative indent."""
        indents = [len(l) - len(l.lstrip()) for l in body_lines if l.strip()]
        if not indents:
            return [l for l in body_lines]
        common = min(indents)
        return [base + l[common:] if l.strip() else "" for l in body_lines]

    def add_import(self, fqn: str) -> None:
        """Insert ``import fqn;`` in alphabetical order inside the import block."""
        pattern = re.compile(rf"^\s*import\s+(?:static\s+)?{re.escape(fqn)}\s*;")
        if any(pattern.match(l) for l in self.lines):
            return
        block_start = None
        block_end = None
        for i, line in enumerate(self.lines):
            if IMPORT_LINE_RE.match(line):
                if block_start is None:
                    block_start = i
                block_end = i
        if block_start is None:
            pkg = self.line_no(lambda l: l.strip().startswith("package "))
            at = (pkg + 1) if pkg is not None else 0
            self.insert_before(at, f"import {fqn};")
            self.insert_before(at + 1, "")
            return
        spot = block_end + 1
        for j in range(block_start, block_end + 1):
            m = IMPORT_LINE_RE.match(self.lines[j])
            if m and m.group(3) > fqn:
                spot = j
                break
        self.insert_before(spot, f"import {fqn};")

    # -- identifier / qualified renames -------------------------------------

    def rename_qualified(self, mapping: dict[str, str]) -> None:
        """Replace fully qualified names anywhere in the source."""
        if not mapping:
            return
        for i, line in enumerate(self.lines):
            new = line
            for old, repl in mapping.items():
                new = new.replace(old, repl)
            if new != line:
                self.lines[i] = new

    def rename_words(self, mapping: dict[str, str]) -> None:
        """Rename standalone identifiers (word-boundary aware)."""
        if not mapping:
            return
        pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in mapping) + r")\b")
        for i, line in enumerate(self.lines):
            new = pattern.sub(lambda m: mapping[m.group(1)], line)
            if new != line:
                self.lines[i] = new

    # -- block surgery -------------------------------------------------------

    def find_block(self, start_pred) -> tuple[int, int] | None:
        """First brace-balanced block whose first line matches *start_pred*.

        Returns ``(start, end)`` inclusive 0-based line indices.
        """
        start = self.line_no(start_pred)
        if start is None:
            return None
        depth = 0
        seen_open = False
        for j in range(start, len(self.lines)):
            seg = strip_comments_and_strings(self.lines[j])
            depth += seg.count("{") - seg.count("}")
            if "{" in seg:
                seen_open = True
            if seen_open and depth <= 0:
                return (start, j)
        return None

    def remove_block(self, start_pred, swallow_annotations: bool = True) -> tuple[int, int] | None:
        """Delete a brace-balanced block (and directly attached annotations)."""
        found = self.find_block(start_pred)
        if not found:
            return None
        start, end = found
        if swallow_annotations:
            while start > 0 and self.lines[start - 1].strip().startswith("@"):
                start -= 1
        del self.lines[start:end + 1]
        return (start, end)

    def remove_method(self, name: str) -> tuple[int, int] | None:
        """Remove a method/constructor by name."""
        escaped = re.escape(name)
        return self.remove_block(
            lambda l: re.match(
                rf"^\s*(?:@\w+(?:\([^)]*\))?\s*)?(?:public|private|protected)?\s*[\w<>\[\]]*\s*{escaped}\s*\(",
                l,
            )
        )

    # -- warnings ------------------------------------------------------------

    def add_warning(self, line_index: int, kind: str, message: str) -> None:
        """Insert a structured warning comment above *line_index*.

        The comment inherits the indentation of the line it annotates.
        """
        idx = max(0, min(line_index, len(self.lines) - 1))
        indent = re.match(r"[ \t]*", self.lines[idx]).group(0) if self.lines else ""
        tag = "TODO: [CONVERT]" if kind == "CONVERT" else "NOTE: [MODPORTER]"
        self.insert_before(idx, f"{indent}// {tag} {message}")

    def warn_top(self, message: str) -> None:
        self.insert_before(0, f"// TODO: [CONVERT] {message}")

    def dump_issues(self) -> list[SourceIssue]:
        return list(self.issues)
