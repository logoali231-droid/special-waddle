package com.example.rubymod;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;
import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.item.BlockItem;
import net.minecraft.item.Item;
import net.minecraft.item.ItemGroups;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Sample entry class exercising every converter path:
 * registries, event callbacks, fabric-api dependencies and a Transfer API
 * usage that must trigger a Smart Fallback warning.
 */
public class RubyMod implements ModInitializer {
    public static final String MOD_ID = "rubymod";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    // Registry.register statements spanning multiple lines.
    public static final Block RUBY_BLOCK = Registry.register(
        Registries.BLOCK,
        new Identifier(MOD_ID, "ruby_block"),
        new Block(AbstractBlock.Settings.create().strength(4.0f))
    );

    public static final Item RUBY = Registry.register(
        Registries.ITEM,
        new Identifier(MOD_ID, "ruby"),
        new Item(new Item.Settings())
    );

    public static final Item RUBY_BLOCK_ITEM = Registry.register(
        Registries.ITEM,
        new Identifier(MOD_ID, "ruby_block"),
        new BlockItem(RUBY_BLOCK, new Item.Settings())
    );

    @Override
    public void onInitialize() {
        LOGGER.info("RubyMod initialized");

        // Fabric event callback -> should become @SubscribeEvent on Forge/NeoForge.
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (server.getPlayerManager().getCurrentPlayerCount() > 0) {
                LOGGER.debug("tick with players online");
            }
        });

        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            LOGGER.info("server started");
        });

        // ItemGroup insertion -> deep divergence, gets a TODO comment.
        ItemGroupEvents.modifyEntriesEvent(ItemGroups.INGREDIENTS).register(entries -> {
            entries.add(RUBY);
        });

        // Fabric Transfer API usage -> Smart Fallback (energy system).
        long stored = EnergyStorageUtil.getStored(RUBY_BLOCK);
        if (stored > 0) {
            LOGGER.info("block stores energy: {}", stored);
        }
    }
}
