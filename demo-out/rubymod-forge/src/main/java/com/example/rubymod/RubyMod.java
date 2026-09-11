package com.example.rubymod;

import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.RegistryObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Sample entry class exercising every converter path:
 * registries, event callbacks, fabric-api dependencies and a Transfer API
 * usage that must trigger a Smart Fallback warning.
 */
// TODO: [CONVERT] Fabric client entrypoint class 'com.example.rubymod.client.RubyModClient' is not auto-converted; move its logic into a client setup (@EventBusSubscriber(modid=rubymod, value=Dist.CLIENT)) class.
@Mod("rubymod")
public class RubyMod {
    public static final DeferredRegister<Block> BLOCK_REGISTRY = DeferredRegister.create(net.minecraft.core.registries.Registries.BLOCK, MOD_ID);
    public static final RegistryObject<Block> RUBY_BLOCK = BLOCK_REGISTRY.register("ruby_block", () -> new Block(AbstractBlock.Settings.create().strength(4.0f)));

    public static final DeferredRegister<Item> ITEM_REGISTRY = DeferredRegister.create(net.minecraft.core.registries.Registries.ITEM, MOD_ID);
    public static final RegistryObject<Item> RUBY = ITEM_REGISTRY.register("ruby", () -> new Item(new Item.Settings()));
    public static final RegistryObject<Item> RUBY_BLOCK_ITEM = ITEM_REGISTRY.register("ruby_block", () -> new BlockItem(RUBY_BLOCK, new Item.Settings()));

    public static final String MOD_ID = "rubymod";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    // Registry.register statements spanning multiple lines.



    public RubyMod() {
        // ModPorter: Fabric onInitialize() converted to @Mod constructor.
        LOGGER.info("RubyMod initialized");



        // ItemGroup insertion -> deep divergence, gets a TODO comment.
        // TODO: [CONVERT] ItemGroupEvents.modifyEntriesEvent(...) has no direct equivalent here. Subscribe to BuildCreativeModeTabContentsEvent and call event.getEntries().accept(...).

        // Fabric Transfer API usage -> Smart Fallback (energy system).
        // TODO: [CONVERT] Fabric energy storage utility; replace with a Capability-based energy handler.
        long stored = EnergyStorageUtil.getStored(RUBY_BLOCK);
        if (stored > 0) {
            LOGGER.info("block stores energy: {}", stored);
        }
    }
    }

    @SubscribeEvent
    public static void onEndServerTick(ServerTickEvent event) {
        // ModPorter: converted from ServerTickEvents.END_SERVER_TICK
        var server = event.getServer();

        if (server.getPlayerManager().getCurrentPlayerCount() > 0) {
            LOGGER.debug("tick with players online");
        }

    }

    @SubscribeEvent
    public static void onServerStarted(ServerStartedEvent event) {
        // ModPorter: converted from ServerLifecycleEvents.SERVER_STARTED
        var server = event.getServer();

        LOGGER.info("server started");

    }
}
