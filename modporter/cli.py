# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Command line interface for ModPorter."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import engines as _engines_mod
from . import __version__
from .core.generator import convert_project
from .core.reader import ReaderError, read_project


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="modporter",
        description="Convert Minecraft mod projects between Fabric, Forge and NeoForge.",
    )
    p.add_argument("--version", action="version", version=f"ModPorter {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    conv = sub.add_parser("convert", help="Convert a mod project to another engine.")
    conv.add_argument("project", help="Root directory of the source mod project.")
    conv.add_argument("target", help="Target engine: fabric, forge or neoforge.")
    conv.add_argument("-o", "--output", default=None, help="Output directory (default: <project>-<target>).")
    conv.add_argument("--source-engine", default=None, choices=["fabric", "forge", "neoforge"],
                      help="Override source engine detection.")
    conv.add_argument("--no-clean", action="store_true", help="Do not delete the output directory before converting.")
    conv.add_argument("-v", "--verbose", action="store_true", help="List every copied asset in the report.")

    det = sub.add_parser("detect", help="Detect the engine of a mod project.")
    det.add_argument("project", help="Root directory of the mod project.")

    sub.add_parser("engines", help="List supported engines.")

    ui = sub.add_parser("studio", help="Launch the ModPorter Studio web UI (no commands needed).")
    ui.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765).")
    ui.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "engines":
        for name in (_engines_mod.ENGINE_FABRIC, _engines_mod.ENGINE_FORGE, _engines_mod.ENGINE_NEOFORGE):
            spec = _engines_mod.get_engine(name)
            print(f"{name:10s} metadata={spec.metadata_file:22s} mappings={spec.mapping_type}")
        return 0

    if args.command == "studio":
        from .studio import serve
        serve(port=args.port, open_browser=not args.no_browser)
        return 0

    root = Path(args.project).resolve()
    if not root.is_dir():
        print(f"error: project directory not found: {root}", file=sys.stderr)
        return 2

    if args.command == "detect":
        engine, evidence = _engines_mod.detect_source_engine(root)
        if engine:
            print(f"detected: {engine} (evidence: {evidence})")
            return 0
        print("could not detect engine", file=sys.stderr)
        return 1

    # convert
    try:
        model = read_project(root, engine=args.source_engine)
    except ReaderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.target.lower() == model.engine:
        print(f"error: source and target engine are both '{model.engine}'.", file=sys.stderr)
        return 2

    out = Path(args.output) if args.output else root.parent / f"{root.name}-{model.engine}-to-{args.target}"
    try:
        convert_project(model, args.target.lower(), out, clean=not args.no_clean, verbose=args.verbose)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"error: conversion failed: {exc}", file=sys.stderr)
        if args.verbose:
            raise
        return 1

    report = out / "CONVERSION_REPORT.md"
    print(f"conversion complete -> {out}")
    print(f"report: {report}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
