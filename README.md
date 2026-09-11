# ModPorter — Fabric ⇄ Forge ⇄ NeoForge Mod Project Converter

ModPorter is a CLI tool that converts Minecraft mod projects between the
three major loader ecosystems: **Fabric**, **MinecraftForge** and
**NeoForge**. It rewrites metadata, build files and Java sources, and —
where the two loaders diverge architecturally — it never breaks: it inserts
structured `// TODO: [CONVERT] ...` warnings into the generated code and
collects them in a `CONVERSION_REPORT.md`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             modporter CLI                                │
│  convert <root> <target> | detect <root> | engines                       │
└──────────────┬───────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────┐   ┌──────────────────────────────────────┐
│ 1. Metadata Reader          │   │ 2. Metadata / Build Converters       │
│    modporter.core.reader    │──▶│    modporter.core.metadata (toml)    │
│    fabric.mod.json          │   │    modporter.core.buildgen (gradle)  │
│    mods.toml                │   └──────────────────────────────────────┘
│    neoforge.mods.toml       │
│    gradle files, sources,   │   ┌──────────────────────────────────────┐
│    assets        ▲          │   │ 3. Code Transpilation (Java)         │
└──────────────────┼──────────┘   │    modporter.java.pipeline           │
                   │              │  ├─ entrypoint.py  ModInitializer    │
┌──────────────────┴──────────┐   │  │                ⇄ @Mod + ctor      │
│ Java scanner / editor       │   │  ├─ registry.py    Registry.register │
│ modporter.java.scanner      │──▶│  │                ⇄ DeferredRegister │
│ modporter.java.editor       │   │  ├─ events.py      .register(cb) ⇄  │
│ (comment/string-aware,      │   │  │                @SubscribeEvent    │
│  brace/paren balanced)      │   │  ├─ mappings.py    Yarn ⇄ Mojmap     │
└─────────────────────────────┘   │  ├─ fallback.py    Smart Fallback    │
                                  │  └─ mixins.py      mixin json fixup  │
┌─────────────────────────────┐   └──────────────────────────────────────┘
│ 4. Project Generator        │   writes the output tree +
│ modporter.core.generator    │   CONVERSION_REPORT.md
└─────────────────────────────┘
```

## Requirements

- Python 3.10+ (no third-party dependencies — standard library only)
- Java/Gradle are only needed to *build* the converted project, not to convert it

## Installation

```bash
# from the repo root (optional - you can also run it in place)
pip install -e .
```

## Step-by-step: converting the bundled test project

The repository ships with `samples/fabric-mod/` — a small Fabric mod that
exercises every converter path (multi-line `Registry.register` calls,
Fabric event callbacks, a Fabric client entrypoint, a Fabric Transfer API
"energy" call that must produce a fallback warning).

**1. (Optional) See which engines are supported**

```bash
python -m modporter engines
```

```
fabric     metadata=fabric.mod.json        mappings=yarn
forge      metadata=mods.toml              mappings=mojmap
neoforge   metadata=neoforge.mods.toml     mappings=mojmap
```

**2. Detect the engine of a project**

```bash
python -m modporter detect samples/fabric-mod
# detected: fabric (evidence: src/main/resources/fabric.mod.json)
```

**3. Convert to NeoForge**

```bash
python -m modporter convert samples/fabric-mod neoforge -o out/rubymod-neoforge
```

```
conversion complete -> out/rubymod-neoforge
report: out/rubymod-neoforge/CONVERSION_REPORT.md
```

**4. Inspect the result**

- `out/rubymod-neoforge/src/main/resources/META-INF/neoforge.mods.toml` —
  converted metadata (id `rubymod`, version `1.2.3`, authors, license,
  dependencies; loader-only deps dropped, `cloth-config` carried over).
- `out/rubymod-neoforge/build.gradle`, `settings.gradle`, `gradle.properties` —
  generated NeoForge userdev build.
- `src/main/java/com/example/rubymod/RubyMod.java` — transpiled entry class:
  - `@Mod("rubymod")` replaces `implements ModInitializer`
  - `onInitialize()` body becomes the constructor
  - `Registry.register(...)` fields become `DeferredRegister` +
    `DeferredItem`/`DeferredBlock` fields
  - `ServerTickEvents.END_SERVER_TICK.register(server -> {...})` becomes a
    `@SubscribeEvent static void onEndServerTick(ServerTickEvent event)` method
  - the Fabric Transfer API call is preserved with a
    `// TODO: [CONVERT] Fabric energy storage utility; ...` warning above it
- `CONVERSION_REPORT.md` — every change, note and fallback warning.

**5. Build the converted project** (regular modding toolchain)

```bash
cd out/rubymod-neoforge
gradle build   # first run downloads the NeoForge userdev toolchain
```

**6. Other directions**

```bash
python -m modporter convert samples/fabric-mod forge -o out/rubymod-forge
python -m modporter convert out/rubymod-neoforge fabric -o out/rubymod-roundtrip
```

## CLI reference

```
python -m modporter convert <project-root-or-jar> <fabric|forge|neoforge>
                           [-o OUTPUT_DIR] [--source-engine ENGINE]
                           [--no-clean] [-v] [--keep-decompiled]

python -m modporter detect  <project-root>      # auto-detect the engine
python -m modporter engines                     # list supported engines
python -m modporter studio                      # launch the web UI
```

`SOURCE_ENGINE` may be omitted: ModPorter detects it from
`fabric.mod.json` / `META-INF/mods.toml` / `META-INF/neoforge.mods.toml`
(then falls back to scanning `build.gradle`). The output directory defaults
to `<project>-<source>-to-<target>` next to the project.

## Converting compiled mod jars

You do not need the mod's source code. Pass a **`.jar` file** (CLI or Studio
path field) and ModPorter will:

1. extract the jar's metadata and assets,
2. reconstruct `.java` sources with [Vineflower](https://vineflower.org/)
   (downloaded once from Maven Central, cached in your local app-data/cache
   directory; requires a JDK 17+ on PATH),
3. assemble a source-tree project and run the normal conversion.

```bash
python -m modporter convert Downloads/somemod-1.16.5.jar neoforge -o out/somemod-neo
```

Expectations, stated plainly: decompiled code loses comments and javadoc;
pre-1.17 Forge jars keep SRG member names (`func_...`/`m_...`); Minecraft
APIs are **not** migrated between versions (a 1.16.5 mod converted this way
still needs a real 1.21 port). Every jar conversion says this in the report
and in the Studio UI banner - the conversion is a starting point, not magic.

If Java is missing, the CLI prints the actionable error above instead of
depending on it silently.

## What gets converted

| Area | Fabric | Forge / NeoForge |
|---|---|---|
| Metadata | `fabric.mod.json` | `META-INF/mods.toml` / `neoforge.mods.toml` |
| Entrypoint | `implements ModInitializer` + `onInitialize()` | `@Mod("id")` + constructor |
| Client entry | `ClientModInitializer` in entrypoints | TODO → `@EventBusSubscriber(value=Dist.CLIENT)` |
| Registration | `Registry.register(Registries.X, id, obj)` | `DeferredRegister.create(...)` + `DeferredItem`/`DeferredBlock`/`RegistryObject` |
| Events | `SomeEvents.FIELD.register(x -> {...})` | `@SubscribeEvent` methods |
| Mappings | Yarn (`Identifier`, `net.minecraft.item.*`) | Mojmap (`ResourceLocation`, `net.minecraft.world.item.*`) |
| Build | `fabric-loom` | ForgeGradle / NeoGradle userdev |
| Mixins | refmap-based | refmap removed, `required=true` set (re-validate targets!) |

## Smart Fallback — what is deliberately *not* auto-converted

Some Fabric APIs have no syntactic equivalent on Forge/NeoForge; they need a
design change, not a rename. ModPorter keeps the code in place and inserts a
structured warning:

```java
// TODO: [CONVERT] Fabric energy storage utility; replace with a Capability-based energy handler.
long stored = EnergyStorageUtil.getStored(RUBY_BLOCK);
```

Detected patterns include: the Fabric **Transfer API** (energy/fluids) vs
Forge **Capabilities**, screen-handler vs `MenuType`, player-interact
callbacks vs `PlayerInteractEvent`, `ItemGroupEvents` vs
`BuildCreativeModeTabContentsEvent`, `LazyOptional`/capability classes when
targeting Fabric, and mixin configs. Every hit is also listed in
`CONVERSION_REPORT.md` under *Smart Fallback warnings* so nothing is missed.

## Project layout

```
modporter/
├── core/                     # metadata + build + orchestration
│   ├── engines.py            # engine specs & auto-detection
│   ├── reader.py             # (1) Metadata Reader -> ProjectModel
│   ├── metadata.py           # (2) fabric.mod.json <-> mods.toml converter
│   ├── buildgen.py           # (2) build.gradle / settings.gradle generator
│   ├── generator.py          # (4) Project Generator + report
│   ├── model.py              # ProjectModel / ModMetadata dataclasses
│   ├── tomlwriter.py         # minimal TOML emitter (stdlib-only)
│   └── cli.py + __main__.py  # argparse CLI (python -m modporter)
├── java/                     # (3) code transpilation
│   ├── scanner.py            # comment/string-aware scanner, method blocks
│   ├── editor.py             # JavaSourceEditor (line-based surgical edits)
│   ├── entrypoint.py         # ModInitializer ⇄ @Mod transformer
│   ├── registry.py           # Registry.register ⇄ DeferredRegister
│   ├── events.py             # fabric callbacks ⇄ @SubscribeEvent
│   ├── mappings.py           # Yarn ⇄ Mojmap + incompatibility patterns
│   ├── fallback.py           # Smart Fallback TODO insertion
│   ├── mixins.py             # mixin json rewriter
│   └── pipeline.py           # per-file transformer orchestration
├── samples/fabric-mod/       # test project used by the test suite
└── tests/                    # 20 stdlib unittest cases incl. e2e round-trips
```

## Notes & limitations

- The transpiler targets the **well-formed, idiomatic patterns** produced by
  mod templates (static registration fields, lambda callbacks, annotated
  entry classes). Heavily unusual code (registration inside loops, reflection)
  is left in place with a warning rather than mis-converted.
- Mixin **classes** are copied; their **configs** are adjusted (refmap removed
  for mojmap targets). Mixin *targets* must still be re-verified by a human
  — this is flagged in the report.
- Generated build files pin a current toolchain (Loom 1.7 / ForgeGradle 6 /
  NeoGradle 7 for MC 1.21.1). Version numbers are reused from the source
  project's `gradle.properties` where possible.
- Always review `CONVERSION_REPORT.md` and the `// TODO: [CONVERT]` comments
  before shipping; ModPorter is a massive head start, not a human replacement.

## Running the test suite

```bash
python -m unittest discover -s tests -v
```

The e2e tests convert the sample project in both directions (including a
fabric → neoforge → fabric round trip) and assert on the generated code.
