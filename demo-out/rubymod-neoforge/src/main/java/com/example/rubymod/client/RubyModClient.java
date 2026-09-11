package com.example.rubymod.client;

import net.fabricmc.api.EnvType;
import net.neoforged.api.distmarker.OnlyIn;
import net.minecraft.client.render.BlockRenderLayerMap;
import net.minecraft.client.render.BlockRenderLayer;

@Environment(EnvType.CLIENT)
public class RubyModClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        BlockRenderLayerMap.INSTANCE.putBlock(RubyMod.RUBY_BLOCK, BlockRenderLayer.CUTOUT);
    }
}
