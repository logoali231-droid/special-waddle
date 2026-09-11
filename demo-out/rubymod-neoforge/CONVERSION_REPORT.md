# ModPorter conversion report

- Source engine: **fabric** (`fabric.mod.json`)
- Target engine: **neoforge** (`neoforge.mods.toml`)
- Mod: **Ruby Mod** (`rubymod` v1.2.3)

## Metadata
- Generated `src/main/resources/META-INF/neoforge.mods.toml`
- Dropped loader-only dependencies: fabric-api, fabricloader, java (replaced by the target loader's own dependency)

## Build configuration
- Generated `build.gradle`
- Generated `settings.gradle`
- Generated `gradle.properties`

## Code transpilation
- Transpiled 2 Java file(s)
- Entry class: `src/main/java/com/example/rubymod/RubyMod.java`
- RubyMod.onInitialize() converted to RubyMod() constructor (plain constructor; the constructor with IEventBus is preferred for event registration).
- Fabric client entrypoint class 'com.example.rubymod.client.RubyModClient' is not auto-converted; move its logic into a client setup (@EventBusSubscriber(modid=rubymod, value=Dist.CLIENT)) class.
- Converted 2 Fabric event callback(s) to @SubscribeEvent methods.

## Assets
- Skipped source metadata `src/main/resources/fabric.mod.json` (replaced by target metadata)

## Smart Fallback warnings (TODO: [CONVERT])
- TODO: [CONVERT] Fabric energy storage utility; replace with a Capability-based energy handler.
- TODO: [CONVERT] ItemGroupEvents.modifyEntriesEvent(...) has no direct equivalent here. Subscribe to BuildCreativeModeTabContentsEvent and call event.getEntries().accept(...).

