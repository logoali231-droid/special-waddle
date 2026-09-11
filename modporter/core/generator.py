# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 4 - Project Generator.

Assembles the output project: converted metadata, generated Gradle files,
transpiled Java sources, ported assets and a conversion report.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..java import mixins as mixin_transformers
from ..java.pipeline import TransformContext, transpile
from .buildgen import generate_build_files
from .engines import ENGINE_FABRIC, get_engine
from .metadata import convert_metadata
from .model import ProjectModel


class ConversionError(RuntimeError):
    """Raised when a conversion request is invalid."""


class ConversionReport:
    """Human-readable summary of a conversion run."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, line: str) -> None:
        self.lines.append(line)

    def extend(self, lines: list[str]) -> None:
        self.lines.extend(lines)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"

    def save(self, out_dir: Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "CONVERSION_REPORT.md"
        target.write_text(self.text(), encoding="utf-8")
        return target


def convert_project(
    model: ProjectModel,
    target_engine: str,
    out_dir: Path,
    *,
    clean: bool = True,
    verbose: bool = False,
    jar_note: str | None = None,
) -> Path:
    """Run the full conversion and write the result into *out_dir*.

    ``jar_note`` documents that the input sources were reconstructed by
    decompilation; it is surfaced in the report's Smart Fallback section.
    """
    target_engine = (target_engine or "").strip().lower()
    if target_engine == model.engine:
        raise ConversionError(
            f"Source and target engine are both '{model.engine}'; nothing to convert."
        )
    target_spec = get_engine(target_engine)  # raises EngineError for unknown names
    out_dir = Path(out_dir).resolve()
    project_dir = Path(model.root).resolve()
    if out_dir == project_dir or project_dir in out_dir.parents:
        raise ConversionError(
            "Output folder must be outside the project folder "
            "(the conversion clears the output directory first)."
        )

    report = ConversionReport()
    report.add(f"# ModPorter conversion report")
    report.add("")
    report.add(f"- Source engine: **{model.engine}** (`{model.spec.metadata_file}`)")
    report.add(f"- Target engine: **{target_engine}** (`{target_spec.metadata_file}`)")
    report.add(f"- Mod: **{model.metadata.name}** (`{model.metadata.mod_id}` v{model.metadata.version})")
    report.add("")

    if out_dir.exists() and clean:
        shutil.rmtree(out_dir)
    (out_dir / "src" / "main" / "java").mkdir(parents=True, exist_ok=True)
    (out_dir / "src" / "main" / "resources").mkdir(parents=True, exist_ok=True)

    # --- 1. metadata ---------------------------------------------------------
    meta_files = convert_metadata(model, target_engine)
    for rel, content in meta_files.items():
        _write(out_dir, rel, content)
    report.add("## Metadata")
    for rel in meta_files:
        report.add(f"- Generated `{rel}`")
    dropped = []
    for d in model.metadata.depends:
        if d.mod_id in ("fabric", "fabric-api", "fabricloader", "java"):
            dropped.append(d.mod_id)
    if dropped:
        report.add(f"- Dropped loader-only dependencies: {', '.join(sorted(set(dropped)))} "
                   f"(replaced by the target loader's own dependency)")
    report.add("")

    # --- 2. build files --------------------------------------------------------
    build_files = generate_build_files(model, target_engine)
    for rel, content in build_files.items():
        _write(out_dir, rel, content)
    report.add("## Build configuration")
    for rel in build_files:
        report.add(f"- Generated `{rel}`")
    report.add("")

    # --- 3. Java sources --------------------------------------------------------
    result = transpile(model, target_engine)
    package_root = target_spec.source_root
    for rel, text in result.files.items():
        # keep the original relative path (package statements were rewritten)
        _write(out_dir, rel, text)
    report.add("## Code transpilation")
    report.add(f"- Transpiled {len(result.files)} Java file(s)")
    if result.entry_file:
        report.add(f"- Entry class: `{result.entry_file}`")
    for note in result.notes:
        report.add(f"- {note}")
    report.add("")

    # --- 4. assets ------------------------------------------------------------
    report.add("## Assets")
    asset_mixin = mixin_transformers.MixinConfigTransformer()
    source_metadata_files = {
        f"src/main/resources/{model.spec.metadata_file}",
        "src/main/resources/META-INF/mods.toml",
        "src/main/resources/META-INF/neoforge.mods.toml",
    }
    for asset in model.assets:
        if asset.path in source_metadata_files:
            report.add(f"- Skipped source metadata `{asset.path}` (replaced by target metadata)")
            continue
        if mixin_transformers.is_mixin_config(asset.path):
            content = asset_mixin.transform(asset, model, _SimpleCtx(target_engine, model.metadata, report.lines))
        else:
            content = asset.text
        _write(out_dir, asset.path, content)
        if verbose:
            report.add(f"- Copied `{asset.path}`")
    if not model.assets:
        report.add("- (no assets found)")
    report.add("")

    # --- 5. pack.mcmeta & mixins bookkeeping -----------------------------------
    if not (out_dir / "src/main/resources/pack.mcmeta").exists():
        _write(
            out_dir,
            "src/main/resources/pack.mcmeta",
            '{\n  "pack": {\n    "description": "Converted by ModPorter",\n    "pack_format": 34\n  }\n}\n',
        )
        report.add("- Generated default `pack.mcmeta` (pack_format 34, MC 1.21.x)")
    if model.mixin_configs:
        report.add("## Mixins")
        for cfg in model.mixin_configs:
            report.add(f"- ⚠ Mixin config `{cfg}` was copied but must be re-validated for {target_engine}.")
        report.add("")

    # --- 6. smart fallback warnings ---------------------------------------------
    report.add("## Smart Fallback warnings (TODO: [CONVERT])")
    if jar_note:
        report.add("")
        report.add("> **Compiled-jar input:** " + jar_note)
    if result.fallback_messages:
        for msg in sorted(set(result.fallback_messages)):
            report.add(f"- TODO: [CONVERT] {msg}")
    else:
        report.add("- None detected.")
    report.add("")

    report.save(out_dir)
    return out_dir


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _SimpleCtx:
    """Minimal context object for asset transformers."""

    def __init__(self, target_engine: str, metadata, notes: list[str]) -> None:
        self.target_engine = target_engine
        self.metadata = metadata
        self.notes = notes
