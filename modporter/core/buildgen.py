# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 4 - Project Generator: build configuration.

Generates ``build.gradle``, ``settings.gradle`` and ``gradle.properties``
for the target engine, reusing versions found in the source project when
available.
"""
from __future__ import annotations

import re

from .engines import ENGINE_FABRIC, ENGINE_FORGE, ENGINE_NEOFORGE, DEFAULT_JAVA_VERSION
from .model import ProjectModel


def _props(model: ProjectModel, target_engine: str) -> dict[str, str]:
    """Version properties for the TARGET engine, reusing source versions."""
    mc = model.minecraft_version or "1.21.1"
    props: dict[str, str] = {"minecraft_version": mc}
    src_text = model.gradle_files.get("gradle.properties", "")
    if target_engine == ENGINE_FABRIC:
        # reuse loader/fabric-api versions from source gradle.properties if present
        m = re.search(r"loader_version=([\w.+\-]+)", src_text)
        props["loader_version"] = m.group(1) if m else "0.16.5"
        m = re.search(r"fabric_version=([\w.+\-]+)", src_text)
        props["fabric_version"] = m.group(1) if m else "0.102.0+1.21.1"
    elif target_engine == ENGINE_FORGE:
        m = re.search(r"forge_version=([\w.+\-]+)", src_text)
        props["forge_version"] = m.group(1) if m else "52.0.24"
    else:
        m = re.search(r"neo_version=([\w.+\-]+)", src_text)
        props["neo_version"] = m.group(1) if m else "21.1.77"
    return props


def generate_build_files(model: ProjectModel, target_engine: str) -> dict[str, str]:
    """Return {filename: content} for the target engine."""
    meta = model.metadata
    props = _props(model, target_engine)
    mc = props["minecraft_version"]
    group = "com.example"
    authors = ", ".join(meta.authors) if meta.authors else "YourName"
    mod_id = meta.mod_id

    if target_engine == ENGINE_FABRIC:
        build = f"""plugins {{
    id 'fabric-loom' version '1.7-SNAPSHOT'
    id 'maven-publish'
}}

version = project.mod_version
group = project.maven_group

base {{
    archivesName = project.archives_base_name
}}

repositories {{
    mavenCentral()
    maven {{ url = 'https://maven.fabricmc.net/' }}
}}

dependencies {{
    minecraft "com.mojang:minecraft:${{project.minecraft_version}}"
    mappings "net.fabricmc:yarn:${{project.minecraft_version}}+build.1:v2"
    modImplementation "net.fabricmc:fabric-loader:${{project.loader_version}}"
    modImplementation "net.fabricmc.fabric-api:fabric-api:${{project.fabric_version}}"
}}

processResources {{
    inputs.property "version", project.version
    filesMatching("fabric.mod.json") {{
        expand "version": project.version
    }}
}}

tasks.withType(JavaCompile).configureEach {{
    it.options.release = {DEFAULT_JAVA_VERSION}
}}

java {{
    withSourcesJar()
    sourceCompatibility = JavaVersion.VERSION_{DEFAULT_JAVA_VERSION}
    targetCompatibility = JavaVersion.VERSION_{DEFAULT_JAVA_VERSION}
}}

jar {{
    from("LICENSE") {{
        rename {{ "${{it}}" }}
    }}
}}
"""
        settings = f"""pluginManagement {{
    repositories {{
        maven {{
            name = 'Fabric'
            url = 'https://maven.fabricmc.net/'
        }}
        mavenCentral()
        gradlePluginPortal()
    }}
}}

rootProject.name = '{mod_id}-fabric'
"""
        gprops = (
            "org.gradle.jvmargs=-Xmx2G\n"
            "org.gradle.parallel=true\n\n"
            f"# Fabric Properties\nminecraft_version={mc}\n"
            f"yarn_mappings={mc}+build.3\n"
            f"loader_version={props['loader_version']}\n\n"
            f"# Mod Properties\nmod_version={meta.version}\n"
            f"maven_group={group}\n"
            f"archives_base_name={mod_id}\n\n"
            f"# Dependencies\nfabric_version={props['fabric_version']}\n"
        )
        return {"build.gradle": build, "settings.gradle": settings, "gradle.properties": gprops}

    if target_engine == ENGINE_NEOFORGE:
        build = f"""plugins {{
    id 'java-library'
    id 'net.neoforged.gradle.userdev' version '7.0.145'
}}

version = project.mod_version
group = project.maven_group

base {{
    archivesName = project.archives_base_name
}}

java.toolchain.languageVersion = JavaLanguageVersion.of({DEFAULT_JAVA_VERSION})

repositories {{
    mavenCentral()
    maven {{ url = 'https://maven.neoforged.net/releases' }}
}}

dependencies {{
    implementation "net.neoforged:neoforge:${{project.neo_version}}"
}}

tasks.named('processResources', ProcessResources).configure {{
    var replaceProperties = [
        minecraft_version: project.minecraft_version,
        neo_version: project.neo_version,
        mod_version: project.mod_version
    ]
    inputs.properties replaceProperties
    filesMatching(['META-INF/neoforge.mods.toml']) {{
        expand replaceProperties
    }}
}}
"""
        settings = f"""pluginManagement {{
    repositories {{
        gradlePluginPortal()
        maven {{ url = 'https://maven.neoforged.net/releases' }}
    }}
}}

rootProject.name = '{mod_id}-neoforge'
"""
        gprops = (
            "org.gradle.jvmargs=-Xmx2G\n"
            "org.gradle.parallel=true\n\n"
            f"minecraft_version={mc}\n"
            f"neo_version={props['neo_version']}\n\n"
            f"mod_version={meta.version}\n"
            f"maven_group={group}\n"
            f"archives_base_name={mod_id}\n"
        )
        return {"build.gradle": build, "settings.gradle": settings, "gradle.properties": gprops}

    # Forge
    build = f"""buildscript {{
    repositories {{
        maven {{ url = 'https://maven.minecraftforge.net' }}
        mavenCentral()
    }}
    dependencies {{
        classpath 'net.minecraftforge.gradle:ForgeGradle:[6.0,6.2)'
    }}
}}
plugins {{
    id 'net.minecraftforge.gradle' version '[6.0.18,6.2)'
}}

version = project.mod_version
group = project.maven_group

base {{
    archivesName = project.archives_base_name
}}

java.toolchain.languageVersion = JavaLanguageVersion.of({DEFAULT_JAVA_VERSION})

repositories {{
    mavenCentral()
    maven {{
        name = 'MinecraftForge'
        url = 'https://maven.minecraftforge.net'
    }}
}}

dependencies {{
    minecraft "net.minecraftforge:forge:{mc}-${{project.forge_version}}"
}}

tasks.named('processResources', ProcessResources).configure {{
    var replaceProperties = [
        minecraft_version: project.minecraft_version,
        forge_version: project.forge_version,
        mod_version: project.mod_version
    ]
    inputs.properties replaceProperties
    filesMatching(['META-INF/mods.toml']) {{
        expand replaceProperties
    }}
}}
"""
    settings = f"""pluginManagement {{
    repositories {{
        gradlePluginPortal()
        maven {{ url = 'https://maven.minecraftforge.net' }}
    }}
}}

rootProject.name = '{mod_id}-forge'
"""
    gprops = (
        "org.gradle.jvmargs=-Xmx2G\n"
        "org.gradle.parallel=true\n\n"
        f"minecraft_version={mc}\n"
        f"forge_version={props['forge_version']}\n\n"
        f"mod_version={meta.version}\n"
        f"maven_group={group}\n"
        f"archives_base_name={mod_id}\n"
    )
    return {"build.gradle": build, "settings.gradle": settings, "gradle.properties": gprops}
