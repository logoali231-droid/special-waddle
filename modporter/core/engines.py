# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Engine specifications and source engine detection.

Each supported engine (fabric, forge, neoforge) is described by an
:class:`EngineSpec` capturing every detail ModPorter needs:

- metadata file name (``fabric.mod.json`` vs ``mods.toml`` / ``neoforge.mods.toml``),
- Gradle plugin ids and repositories,
- default dependency artifacts (fabric-api vs neoforge/forge userdev),
- source package roots for code generation,
- Java token vocabulary used by the transpiler.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ENGINE_FABRIC = "fabric"
ENGINE_FORGE = "forge"
ENGINE_NEOFORGE = "neoforge"
SUPPORTED = (ENGINE_FABRIC, ENGINE_FORGE, ENGINE_NEOFORGE)

# Minecraft version used when generating fresh build files.
DEFAULT_MC_VERSION = "1.21.1"
DEFAULT_JAVA_VERSION = 21

# Yarn intermediary names that appear in transpiled code comments.
KNOWN_YARN_NAMES = ("ItemGroupEvents", "Registry", "Identifier")


class EngineError(ValueError):
    """Raised for unknown engine identifiers."""


@dataclass(frozen=True)
class EngineSpec:
    """Static description of a supported mod loader ecosystem."""

    name: str
    display_name: str
    metadata_file: str
    metadata_kind: str  # "json" | "toml"
    loader_class: str  # entry interface (fabric) or base annotation FQN (forge/neoforge)
    entry_marker: str  # annotation used to tag the entry class
    gradle: dict[str, str]
    gradle_block: str
    mappings: str
    mapping_type: str  # "yarn" | "mojmap"
    source_root: str  # generated java package root
    dependencies: dict[str, str]
    uses_ibus: bool  # event bus style: True -> EventBus (forge/neo), False -> fabric callbacks

    @property
    def is_fabric(self) -> bool:
        return self.name == ENGINE_FABRIC

    @property
    def is_mojmap(self) -> bool:
        return self.mapping_type == "mojmap"


ENGINES: dict[str, EngineSpec] = {
    ENGINE_FABRIC: EngineSpec(
        name=ENGINE_FABRIC,
        display_name="Fabric",
        metadata_file="fabric.mod.json",
        metadata_kind="json",
        loader_class="net.fabricmc.api.ModInitializer",
        entry_marker="@ModPorterEntrypoint",
        gradle={
            "loom_version": "1.7-SNAPSHOT",
            "fabric_api": "0.102.0+1.21.1",
            "minecraft": DEFAULT_MC_VERSION,
        },
        gradle_block=(
            'plugins {\n'
            '    id \'fabric-loom\' version \'1.7-SNAPSHOT\'\n'
            '    id \'maven-publish\'\n'
            '}\n'
        ),
        mappings="net.fabricmc:yarn:1.21.1+build.3:v2",
        mapping_type="yarn",
        source_root="com.example",
        dependencies={
            "minecraft": "com.mojang:minecraft",
            "yarn": "net.fabricmc:yarn",
            "fabricloader": "net.fabricmc:fabric-loader",
            "fabric-api": "net.fabricmc.fabric-api:fabric-api",
        },
        uses_ibus=False,
    ),
    ENGINE_FORGE: EngineSpec(
        name=ENGINE_FORGE,
        display_name="Forge",
        metadata_file="mods.toml",
        metadata_kind="toml",
        loader_class="net.minecraftforge.fml.common.Mod",
        entry_marker="@Mod",
        gradle={
            "forge_version": "52.0.24",
            "minecraft": DEFAULT_MC_VERSION,
        },
        gradle_block=(
            'plugins {\n'
            '    id \'net.minecraftforge.gradle\' version \'[6.0.18,6.2)\'\n'
            '}\n'
        ),
        mappings="official",
        mapping_type="mojmap",
        source_root="com.example",
        dependencies={
            "minecraft": "net.minecraftforge:forge",
            "junit": "org.junit.jupiter:junit",
        },
        uses_ibus=True,
    ),
    ENGINE_NEOFORGE: EngineSpec(
        name=ENGINE_NEOFORGE,
        display_name="NeoForge",
        metadata_file="neoforge.mods.toml",
        metadata_kind="toml",
        loader_class="net.neoforged.fml.common.Mod",
        entry_marker="@Mod",
        gradle={
            "neo_version": "21.1.77",
            "minecraft": DEFAULT_MC_VERSION,
        },
        gradle_block=(
            'plugins {\n'
            '    id \'net.neoforged.gradle.userdev\' version \'7.0.145\'\n'
            '}\n'
        ),
        mappings="official",
        mapping_type="mojmap",
        source_root="com.example",
        dependencies={
            "minecraft": "net.neoforged:neoforge",
            "junit": "org.junit.jupiter:junit",
        },
        uses_ibus=True,
    ),
}


def get_engine(name: str) -> EngineSpec:
    """Return the engine spec for *name* (case-insensitive)."""
    key = (name or "").strip().lower()
    if key not in ENGINES:
        raise EngineError(
            f"Unknown engine {name!r}. Supported: {', '.join(sorted(ENGINES))}"
        )
    return ENGINES[key]


def is_supported(name: str) -> bool:
    try:
        get_engine(name)
        return True
    except EngineError:
        return False


def detect_source_engine(root: Path) -> tuple[str, str] | tuple[None, None]:
    """Detect the source engine from project files.

    Returns ``(engine_name, evidence_path)`` or ``(None, None)``.
    """
    root = Path(root)
    # Probe both the source-tree layout (src/main/resources/...) and the
    # built-jar layout (META-INF/... / fabric.mod.json at the root).
    candidates: list[tuple[str, str]] = [
        (ENGINE_FABRIC, "src/main/resources/fabric.mod.json"),
        (ENGINE_NEOFORGE, "src/main/resources/META-INF/neoforge.mods.toml"),
        (ENGINE_FORGE, "src/main/resources/META-INF/mods.toml"),
        (ENGINE_FABRIC, "fabric.mod.json"),
        (ENGINE_NEOFORGE, "META-INF/neoforge.mods.toml"),
        (ENGINE_FORGE, "META-INF/mods.toml"),
    ]
    for engine, rel in candidates:
        if (root / rel).is_file():
            return engine, rel

    # Fallback: scan build.gradle for loader keywords.
    gradle = root / "build.gradle"
    if gradle.is_file():
        text = gradle.read_text(encoding="utf-8", errors="replace")
        if "fabric-loom" in text or "net.fabricmc" in text:
            return ENGINE_FABRIC, "build.gradle"
        if "net.neoforged" in text or "neoforge" in text.lower():
            return ENGINE_NEOFORGE, "build.gradle"
        if "net.minecraftforge" in text or "minecraftforge" in text.lower():
            return ENGINE_FORGE, "build.gradle"
    return None, None
