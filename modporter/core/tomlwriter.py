# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Tiny TOML serializer (stdlib-only project; no external deps).

Emits the subset of TOML needed for ``mods.toml`` / ``neoforge.mods.toml``:
top-level key/value pairs, string arrays, and [[table]] arrays-of-tables.
"""
from __future__ import annotations

from typing import Any


def _escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_escape(value)}"'
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        return "[" + ", ".join(_format_scalar(v) for v in value) + "]"
    raise TypeError(f"Cannot serialize {type(value).__name__} to TOML")


def dumps(data: dict[str, Any]) -> str:
    """Serialize *data* to TOML text.

    Rules:
    - plain scalar/array keys first (insertion order),
    - then ``dict`` values as ``[table]``,
    - then ``list`` of dicts as repeated ``[[table]]`` sections.
    """
    out: list[str] = []

    def emit_table(prefix: str, table: dict[str, Any], header: str = "[") -> None:
        scalars: list[tuple[str, Any]] = []
        tables: list[tuple[str, dict]] = []
        table_arrays: list[tuple[str, list]] = []
        for k, v in table.items():
            if isinstance(v, dict):
                tables.append((k, v))
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                table_arrays.append((k, v))
            else:
                scalars.append((k, v))
        if prefix and scalars:
            out.append(f"{header}{prefix}{']' if header == '[' else ']]'}")
        for k, v in scalars:
            out.append(f"{k} = {_format_scalar(v)}")
        if prefix and scalars:
            out.append("")
        for k, v in tables:
            emit_table(f"{prefix}.{k}" if prefix else k, v)
        for k, arr in table_arrays:
            key = f"{prefix}.{k}" if prefix else k
            for entry in arr:
                # array-of-tables entries emit [[key]] headers
                emit_table(key, entry, header="[[")

    emit_table("", data)
    # Collapse duplicate blank lines at the end.
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"
