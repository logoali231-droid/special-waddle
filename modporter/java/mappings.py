# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Symbol mapping tables: Yarn <-> Mojang mappings, package swaps, API classes.

Used by Module 3 (Code Transpilation). All mappings are direction-agnostic:
they are looked up with the *source* engine's mapping type.
"""
from __future__ import annotations

# --- top-level package swaps (prefix based) ---------------------------------

PACKAGE_SWAPS: dict[str, str] = {
    "net.fabricmc.api": "net.neoforged.fml.common",
    "net.fabricmc.fabric.api": "net.neoforged.neoforge.common",
    "net.minecraft.util": "net.minecraft.resources",
}

# --- per-engine import rewrite tables ---------------------------------------

IMPORT_MAPS: dict[str, dict[str, str]] = {
    # source engine -> {source FQN -> target FQN}
    "fabric": {
        # entrypoints
        "net.fabricmc.api.ModInitializer": "net.neoforged.fml.common.Mod",
        "net.fabricmc.api.ClientModInitializer": "net.neoforged.api.distmarker.OnlyIn",
        # registry
        "net.minecraft.core.Registry": "net.minecraft.core.registries.Registries",
        "net.minecraft.core.registries.BuiltInRegistries": "net.minecraft.core.registries.BuiltInRegistries",
        "net.minecraft.util.Identifier": "net.minecraft.resources.ResourceLocation",
        # items/blocks/entities
        "net.minecraft.item.Item": "net.minecraft.world.item.Item",
        "net.minecraft.item.ItemGroup": "net.minecraft.world.item.CreativeModeTab",
        "net.minecraft.item.ItemStack": "net.minecraft.world.item.ItemStack",
        "net.minecraft.item.ItemGroups": "net.minecraft.world.item.CreativeModeTabs",
        "net.minecraft.item.BlockItem": "net.minecraft.world.item.BlockItem",
        "net.minecraft.block.AbstractBlock": "net.minecraft.world.level.block.state.BlockBehaviour",
        "net.minecraft.block.Block": "net.minecraft.world.level.block.Block",
        "net.minecraft.block.Blocks": "net.minecraft.world.level.block.Blocks",
        "net.minecraft.block.entity.BlockEntityType": "net.minecraft.world.level.block.entity.BlockEntityType",
        "net.minecraft.entity.EntityType": "net.minecraft.world.entity.EntityType",
        "net.minecraft.entity.Entity": "net.minecraft.world.entity.Entity",
        # fabric api events
        "net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents": "net.neoforged.neoforge.common.NeoForgeMod",
        "net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents": "net.neoforged.neoforge.event.TickEvent$ServerTickEvent",
        "net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents": "net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent",
    },
    "forge": {
        "net.minecraftforge.fml.common.Mod": "net.neoforged.fml.common.Mod",
        "net.minecraftforge.eventbus.api.SubscribeEvent": "net.neoforged.bus.api.SubscribeEvent",
        "net.minecraftforge.eventbus.api.IEventBus": "net.neoforged.bus.api.IEventBus",
        "net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent": "net.neoforged.fml.event.lifecycle.FMLClientSetupEvent",
        "net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent": "net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent",
        "net.minecraftforge.event.entity.EntityAttributeCreationEvent": "net.neoforged.neoforge.event.entity.EntityAttributeCreationEvent",
        "net.minecraftforge.event.BuildCreativeModeTabContentsEvent": "net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent",
        "net.minecraft.util.Identifier": "net.minecraft.resources.ResourceLocation",
        "net.minecraft.item.Item": "net.minecraft.world.item.Item",
        "net.minecraft.block.Block": "net.minecraft.world.level.block.Block",
    },
    "neoforge": {
        "net.neoforged.fml.common.Mod": "net.minecraftforge.fml.common.Mod",
        "net.neoforged.bus.api.SubscribeEvent": "net.minecraftforge.eventbus.api.SubscribeEvent",
        "net.neoforged.bus.api.IEventBus": "net.minecraftforge.eventbus.api.IEventBus",
        "net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent": "net.minecraftforge.event.BuildCreativeModeTabContentsEvent",
        "net.neoforged.neoforge.event.TickEvent$ServerTickEvent": "net.minecraftforge.event.TickEvent$ServerTickEvent",
        "net.neoforged.neoforge.common.NeoForgeMod": "net.minecraftforge.common.ForgeMod",
        "net.minecraft.resources.ResourceLocation": "net.minecraft.util.Identifier",
        "net.minecraft.world.item.Item": "net.minecraft.item.Item",
        "net.minecraft.world.level.block.Block": "net.minecraft.block.Block",
    },
}

# --- identifiers inside method bodies (Yarn -> Mojmap wording) ---------------

YARN_TO_MOJMAP_WORDS: dict[str, str] = {
    "Identifier": "ResourceLocation",
    "newIdentifier": "newResourceLocation",
    "ItemStack": "ItemStack",
    "Registry": "Registry",
    "register": "register",
}

MOJMAP_TO_YARN_WORDS: dict[str, str] = {
    "ResourceLocation": "Identifier",
}

# --- registry kind constants for DeferredRegister generation ----------------

REGISTRY_KINDS = {
    "Block": "Registries.BLOCK",
    "Item": "Registries.ITEM",
    "BlockEntityType": "Registries.BLOCK_ENTITY_TYPE",
    "EntityType": "Registries.ENTITY_TYPE",
    "CreativeModeTab": "Registries.CREATIVE_MODE_TAB",
    "SoundEvent": "Registries.SOUND_EVENT",
    "ParticleType": "Registries.PARTICLE_TYPE",
}

# forge/neoforge registry object wrappers per registry kind
REGISTRY_WRAPPERS = {
    "Block": "DeferredBlock",
    "Item": "DeferredItem",
    "BlockEntityType": "DeferredHolder",
    "EntityType": "DeferredHolder",
    "CreativeModeTab": "DeferredHolder",
    "SoundEvent": "DeferredHolder",
    "ParticleType": "DeferredHolder",
}

# Smart-fallback: APIs with deep architectural divergence -> TODO comments.
INCOMPATIBLE_PATTERNS: dict[str, str] = {
    "fabric": [
        (r"\bfabric\.api\.transfer\b", "Fabric Transfer API used (energy/fluid); Forge/NeoForge use Capabilities instead."),
        (r"\bEnergyStorageUtil\b", "Fabric energy storage utility; replace with a Capability-based energy handler."),
        (r"\bItemApi\b", "Fabric ItemApi lookup; replace with Capabilities (e.g. net.neoforged.neoforge.capabilities)."),
        (r"\bfabric-screen-handler-api-v1\b", "Fabric screen handler API; Forge/NeoForge use MenuType + IMenuTypeExtension."),
        (r"\bPlayerBlockBreakEvents\b", "Fabric block break events; use Forge/NeoForge BlockEvent.BreakEvent."),
        (r"\bUseBlockCallback\b", "Fabric use-block callback; use Forge/NeoForge PlayerInteractEvent.RightClickBlock."),
        (r"\bAttackBlockCallback\b", "Fabric attack-block callback; use Forge/NeoForge PlayerInteractEvent.LeftClickBlock."),
        (r"\bItemGroupEvents\b", "Fabric item-group insertion; rebuild with CreativeModeTab.buildContents / BuildCreativeModeTabContentsEvent on Forge/NeoForge."),
    ],
    "forge": [
        (r"\bCapabilityManager\b", "Forge Capabilities used; Fabric uses the Transfer API instead."),
        (r"\b@CapabilityInject\b", "Forge capability injection; replace with Fabric Transfer API or manual lookup."),
        (r"\bLazyOptional\b", "Forge LazyOptional capability wrapper; replace with Fabric Transfer API."),
        (r"\bForgeHooks\b", "Forge-specific hook class; check for a Fabric API equivalent."),
    ],
    "neoforge": [
        (r"\bCapabilityRegistry\b", "NeoForge capability registry usage; Fabric uses the Transfer API."),
        (r"\bLazyOptional\b", "Legacy capability wrapper; NeoForge 21+ replaced LazyOptional with getCapability()."),
        (r"\bIBlockExtension\b", "NeoForge block extension; Fabric equivalents live in FabricBlockEvents."),
    ],
}
