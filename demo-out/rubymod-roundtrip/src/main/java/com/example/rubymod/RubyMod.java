package com.example.rubymod;

import net.fabricmc.api.Environment;
import net.fabricmc.api.ModInitializer;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.block.Block;
import net.minecraft.world.item.BlockItem;
import net.minecraft.item.Item;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.core.registries.Registries;
import net.minecraft.util.Identifier;
import net.neoforged.neoforge.event.TickEvent$ServerTickEvent;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Sample entry class exercising every converter path:
 * registries, event callbacks, fabric-api dependencies and a Transfer API
 * usage that must trigger a Smart Fallback warning.
 */
// TODO: [CONVERT] DistExecutor/@OnlyIn client-only code has no Fabric equivalent; use a ClientModInitializer declared in fabric.mod.json.
// TODO: [CONVERT] Fabric client entrypoint class 'com.example.rubymod.client.RubyModClient' is not auto-converted; move its logic into a client setup (@EventBusSubscriber(modid=rubymod, value=Dist.CLIENT)) class.
public class RubyMod implements ModInitializer {
    // TODO: [CONVERT] DeferredRegister registration converted to static Registry.register; verify that modEventBus.register(...) calls were removed and that BlockEntityType builders supply the correct supplier argument.
    public static final Block RUBY_BLOCK = Registry.register(net.minecraft.core.registries.Registries.BLOCK, new Identifier(MOD_ID, "ruby_block"),
    public static final Item RUBY = Registry.register(net.minecraft.core.registries.Registries.ITEM, new Identifier(MOD_ID, "ruby"),
    public static final Item RUBY_BLOCK_ITEM = Registry.register(net.minecraft.core.registries.Registries.ITEM, new Identifier(MOD_ID, "ruby_block"),
    );


    public static final String MOD_ID = "rubymod";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    // Registry.register statements spanning multiple lines.



    @Override
    public void onInitialize() {
        // ModPorter: converted @SubscribeEvent onEndServerTick()
        ServerTickEvents.END_SERVER_TICK.register(system -> {
                    // TODO: [CONVERT] Fabric energy storage utility; replace with a Capability-based energy handler.
                    long stored = EnergyStorageUtil.getStored(RUBY_BLOCK);
                    if (stored > 0) {
                        LOGGER.info("block stores energy: {}", stored);
        });
        // ModPorter: converted @SubscribeEvent onServerStarted()
        ServerLifecycleEvents.SERVER_STARTED.register(event -> {
        public static void onServerStarted(ServerStartedEvent event) {
            // ModPorter: converted from ServerLifecycleEvents.SERVER_STARTED
            var server = event.getServer();

            LOGGER.info("server started");

        });
        // ModPorter: @Mod constructor converted to Fabric onInitialize().
                // ModPorter: Fabric onInitialize() converted to @Mod constructor.
                LOGGER.info("RubyMod initialized");



                // ItemGroup insertion -> deep divergence, gets a TODO comment.
                // TODO: [CONVERT] ItemGroupEvents.modifyEntriesEvent(...) has no direct equivalent here. Subscribe to BuildCreativeModeTabContentsEvent and call event.getEntries().accept(...).

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

}
