# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 3d - Smart Fallback.

For code with deep architectural divergence (Capabilities vs Transfer API,
custom mixins, client-only hacks, etc.) the transpiler must not break.
Instead, structured warning comments are inserted into the generated code:

    // TODO: [CONVERT] <explanation>

and every occurrence is recorded for the conversion report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .editor import JavaSourceEditor
from .mappings import INCOMPATIBLE_PATTERNS
from .scanner import strip_comments_and_strings


@dataclass
class FallbackHit:
    """One detected incompatibility."""

    path: str
    line: int  # 1-based line in the source file
    pattern: str
    message: str


@dataclass
class FallbackReport:
    hits: list[FallbackHit] = field(default_factory=list)

    def add(self, hit: FallbackHit) -> None:
        self.hits.append(hit)

    def merged_messages(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for h in self.hits:
            if h.message not in seen:
                seen.add(h.message)
                out.append(h.message)
        return out


def scan_fallbacks(editor: JavaSourceEditor, source_engine: str) -> FallbackReport:
    """Scan for incompatible patterns and insert TODO comments above each hit.

    Import lines referencing an incompatible API are *replaced* by a TODO
    comment rather than duplicated; code lines get a warning above them.
    """
    report = FallbackReport()
    patterns = INCOMPATIBLE_PATTERNS.get(source_engine, [])
    for i, raw_line in enumerate(list(editor.lines)):
        stripped = raw_line.strip()
        code = strip_comments_and_strings(raw_line)
        for pattern_re, message in patterns:
            if re.search(pattern_re, code):
                prev = editor.lines[i - 1] if i > 0 else ""
                if "TODO: [CONVERT]" in prev and message in prev:
                    continue
                if stripped.startswith("import "):
                    # replace the import with the TODO instead of keeping dead code
                    editor.lines[i] = f"// TODO: [CONVERT] {message}"
                else:
                    editor.add_warning(i, "CONVERT", message)
                report.add(
                    FallbackHit(
                        path=editor.path,
                        line=i + 1,
                        pattern=pattern_re,
                        message=message,
                    )
                )
    return report


def scan_mixin_refs(editor: JavaSourceEditor, mixin_configs: list[str]) -> list[str]:
    """Mixin configs cannot be ported automatically; record them."""
    messages: list[str] = []
    for cfg in mixin_configs:
        messages.append(
            f"Mixin config '{cfg}' found. Mixins must be re-validated or rewritten for the target engine "
            "(refmap format and target class names differ)."
        )
    for i, line in enumerate(editor.lines):
        if re.search(r"@(?:Inject|Accessor|Invoker|Shadow|Redirect)\b", line):
            editor.add_warning(i, "CONVERT", "Mixin annotation found here; mixin classes are engine-agnostic but "
                                              "their config files and refmaps are not. Update the mixin json.")
            break
    return messages
