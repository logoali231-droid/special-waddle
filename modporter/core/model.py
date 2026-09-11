# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""In-memory project model shared by all ModPorter modules.

A :class:`ProjectModel` is produced by the :mod:`modporter.core.reader`
metadata module and consumed by the code transformers and the
:mod:`modporter.core.generator` project generator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .engines import EngineSpec


@dataclass
class Dependency:
    """A dependency declared in the source metadata."""

    mod_id: str
    version_range: str = "*"


@dataclass
class ModMetadata:
    """Normalized mod metadata (id, name, version, dependencies...)."""

    mod_id: str = "examplemod"
    name: str = "Example Mod"
    version: str = "1.0.0"
    description: str = ""
    authors: list[str] = field(default_factory=list)
    license: str = "MIT"
    homepage: str | None = None
    sources: str | None = None
    issues: str | None = None
    icon: str | None = None
    entrypoints: dict[str, list[str]] = field(default_factory=dict)
    depends: list[Dependency] = field(default_factory=list)
    suggests: list[Dependency] = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # engine-specific leftovers


@dataclass
class SourceFile:
    """A Java source file discovered by the scanner."""

    path: str  # path relative to project root
    package: str  # java package ("") for default package
    class_name: str
    text: str
    is_entry: bool = False


@dataclass
class AssetFile:
    """A non-Java file (JSON lang files, textures, mixins, pack.mcmeta...)."""

    path: str  # relative to project root
    text: str


@dataclass
class ProjectModel:
    """Everything ModPorter knows about the source project."""

    root: str
    engine: str  # source engine name
    spec: EngineSpec
    metadata: ModMetadata
    sources: list[SourceFile] = field(default_factory=list)
    assets: list[AssetFile] = field(default_factory=list)
    gradle_files: dict[str, str] = field(default_factory=dict)
    mixin_configs: list[str] = field(default_factory=list)
    loader_version: str = "*"
    minecraft_version: str | None = None

    def entry_file(self) -> SourceFile | None:
        for s in self.sources:
            if s.is_entry:
                return s
        return None
