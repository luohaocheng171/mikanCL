# MikanCL v5.4.6 Release Notes

[中文](RELEASE.md) · **English** · [Русский](RELEASE.ru.md) · [Français](RELEASE.fr.md) · [日本語](RELEASE.ja.md)

Release date: 2026-11-15

## Addendum: NBT extreme-value engine (beyond in-game numeric limits)

- **Principle & boundaries**: numeric caps mostly come from NBT tag bit widths (`TAG_Byte` 8-bit / `TAG_Short` 32767 / `TAG_Int` 2³¹ / `TAG_Long` 2⁶³). The new `nbt_extreme.py` writes values beyond a tag's native cap via **type promotion** (short→int→long) and **unsigned bit patterns**; out-of-range values are rejected by default (wrap-around optional), and a `.mikancl-bak` backup is created automatically before every write.
- **Dual-track enchantment breakthrough**: automatically detects pre/post-`1.20.5` layouts — legacy `tag.Enchantments`/`ench` (short) and modern `components."minecraft:enchantments".levels` (int; enchanted books use `stored_enchantments`). The enchantment dictionary is expanded to 44 entries (including `1.21` `breach`/`density`/`wind_burst` and `26.1` `lunge`), with one-click maxing and the "⚡ Grand Universal Enchantment" (inject every enchantment — including conflicting ones and curses — then max them all: the principle behind 32k enchants).
- **General overflow power**: auto-promote any node's type to write huge values, scan the whole tree for overflow, and 14 one-click presets (XP / stack size / health / potion effect / seed / time, etc.); integer parsing switched to direct string conversion, fixing the `int(float())` precision loss above 2⁵³.
- **All three UIs**: the NBT studio adds an "⚡ Extreme Values" page (8 `nbe_*` endpoints for Web / Electron + an identically named Qt tab), all on background threads with lazy imports.
- **Warning**: extreme values can crash the game, corrupt saves, or get you banned on servers. Whether they take effect depends on whether the game reads a field "by value" or "by tag type". This feature only guarantees the written NBT is valid and readable by tools — it does not promise the game will honor it. Data cross-checked against minecraft.wiki on 2026-11-15.
- **The truth about the 255 enchantment cap (important)**: bit width can be promoted, but **enchantment levels have an additional hard cap in the game**. Since **Java 1.17.1 (2021-07-06), all enchantments are capped at level 255 in both display and power** (release-note quote: *All enchantments are now capped at level 255 in both display and power*; that version also fixed MC-131290). So on 1.17.1+ writing 32767 only shows/works as 255 — a diamond sword with Sharpness 255 = `7 + 0.5×(255+1) = 135` damage, exactly matching the in-game tooltip; by 32767 it would be 16391. This is a code-level limit that **type promotion cannot bypass**. Before 1.17.1 (1.16.5 / 1.12.2 / 1.7.10 etc.) there is no such clamp and a short can really hold 32767. `enchant_effective_cap(version)` reports the real cap per version and the UI warns when a value will be clamped.
- **Bypassing 255: direct attribute editing**: new `attribute_apply()` attaches an attack-damage attribute modifier instead of raising the enchantment level (legacy `tag.AttributeModifiers` / 1.20.5+ `components.attribute_modifiers`), `amount` being a double. The attribute caps at **0–2048** in game, far above Sharpness 255's 135. New "Direct attribute" sub-tab in Web/Electron and matching Qt controls.
- **Validation**: `test_nbt_extreme.py` expanded to **70/70 green** (including the 1.17.1 cap boundary, 1.16.5 uncapped, legacy/modern attribute writes, 2048 clamping, 1.21.2 prefix removal); `test_nbt_studio.py` 38/38, `test_api_gateway.py` 30/30, `test_datapack_v2.py` 38/38, `test_item_icons.py` 20/20 all green (196 total); `node --check app.js`, 127-file AST compile and the Qt page (offscreen) pass; the 10 `nbe_*` endpoints match frontend to backend.

## New: building generation at a coordinate + 41 deep numeric controls

- **Why not write region directly**: world blocks live in `region/*.mca` chunks, not in `level.dat`; rewriting a chunk plus its heightmap easily corrupts a save. This uses the official route: **structure file + a placement tool**.
- **Structure file generation**: emits `size`/`palette`/`blocks`/`entities`/`DataVersion` (gzip) in the official format. Four built-in templates — hut, tower, floating platform, pillar — plus custom block tables and block states. The target folder follows the version automatically: **`structure/` (singular) from 1.21, `structures/` before**.
- **Three placement paths, gated by version**: ① `/give` a structure-block item (1.10+, easiest) — carries `BlockEntityTag` (LOAD mode, structure name, position, size, rotation, mirror, integrity); power it and it loads. BE id is `structure_block` from 1.11 and `Structure` in 1.10, switched automatically. ② `/place template` (1.19+); `strict` only in 1.21.5+. ③ Command-block item preloaded with the command. On 1.12.2 only the structure-block path is offered — no pretending `/place` exists.
- **41 deep numeric controls**: spawn point and angle (`SpawnAngle` 1.16.2+), world time, four weather fields, difficulty / hardcore / allow-commands, **world border** (center / size / damage / warning), **player abilities** (fly / instabuild / invulnerable / speeds), XP / food / health / absorption, **entity physics** (no-gravity / invulnerable / persistence / silent / glowing / no-AI).
- **Real-time version detection**: `capabilities(version)` and `control_catalog(version)` are the single entry points, reporting what the current version supports and which file each field belongs to. **26.1 restructured `level.dat`** (weather→`weather.dat`, difficulty→`difficulty_settings`, world border→`world_border.dat`); writes are redirected to the right file, a missing file is reported honestly instead of invented, and fields below their minimum version are disabled with the reason shown.
- **All three UIs**: Web / Electron gain a "🏗 Building" page and 7 `nbb_*` endpoints; the Qt build adds the same tab (7 tabs) and refreshes both the capability badges and the control table when the version changes.
- **Validation**: new `test_nbt_build.py` — **79/79 green**; **275 tests** green across all six suites; 129 files compile with zero AST errors, `node --check` passes, the Qt page runs offscreen with 7 tabs.

## Fixes: drag false alarm, dynamic item discovery, per-version world filtering

- **Fixed the spurious "no dropped file path" error**: the window-level `drop` listener never checked whether `dataTransfer.types` contained `Files`, so dragging an item icon (`text/plain`) in the recipe workshop and releasing over empty space wrongly triggered the file-import warning. All three drag listeners now confirm it is really a file drop before acting.
- **Items are now fetched from installed versions each time**: the recipe workshop item palette no longer relies only on the built-in 270 item IDs — every load reads real textures from local version jars / resource packs / mod jars and augments the static dictionary with vanilla items it does not contain (including newly added ones), exposing `dynamic_added` / `from_version_jar`. Switching version refetches.
- **Importing a crafting pack shows only current-version worlds by default**: the target-world dropdown now defaults to worlds whose `level.dat` version matches the selected game version, so same-named worlds ("New World") from different versions are no longer ambiguous; a "current version only" toggle switches back to all worlds. Same checkbox in the Qt build.

## v5.4.6: full NBT editor, drag-and-drop recipe workshop, tuning, unified API gateway

- **Official game data dictionary**: new `game_data.py`, cross-checked against the raw minecraft.wiki pages. Covers 18 data pack formats / 26 resource pack formats (`1.6.1`–`26.3`), 59 game rules, 32 entity attributes, 31 default mob loot tables, 97 common NBT fields in 7 groups, all 13 NBT tag types and 270 vanilla item IDs. Version boundaries are explicit: `1.20.5` recipe `item`→`id`, `1.21` singular `loot_table` folder, `1.21.2` simplified ingredients and attribute prefix removal, `1.21.5` snake_case entity NBT, `1.21.9` `min_format`/`max_format` in `pack.mcmeta`, `1.21.11` snake_case game rules with some inverted values, `26.1` GameRules moved to `game_rules.dat`. `1.12.2` and older have no data pack system — the UI says so and points to mods instead.
- **NBT studio**: new `nbt_studio.py` builds on typed NBT I/O with a tree view, batch edits, add/delete nodes, automatic `.mikancl-bak` backups and path-traversal guards. Edit entity attributes (version-correct IDs), mob drops (generates a loot table overriding the `minecraft` namespace), GameRules (key renames and inverted values handled automatically) and `server.properties` (key-by-key, comments preserved).
- **Recipe workshop with item icons**: new `item_icons.py` extracts real textures from version jars, resource packs and mod jars, and generates stable pixel-art placeholders when a texture is missing. WebView2 and Electron get a 3×3 crafting bench plus furnace UI — drag icons into slots and drop the output in the result slot; the Qt build uses native `ItemPalette` → `ItemSlot` drag and drop. One action exports **both a data pack zip and a resource pack zip** for manual installation into `datapacks/` and `resourcepacks/`. Mod namespaces can be selected to **override existing recipes**, and existing recipes from worlds / mod jars / version jars can be loaded and edited.
- **Numeric tuning**: 18 controls for spawn caps, entity cramming, movement speed and more, grouped by source (gamerule / `server.properties` / Bukkit / entity attributes). Game rules are written to `level.dat`, server properties are rewritten key by key; Bukkit-only and attribute entries show recommended values and point to the right editor rather than pretending to be writable.
- **Unified API gateway**: new `api_gateway.py` reflects **all 339 public `WebApi` methods** into a searchable catalogue with signatures, Chinese descriptions and groups. Query, describe, invoke, export OpenAPI 3, or start a localhost-only HTTP JSON-RPC server (`127.0.0.1`, random token). Dangerous and private methods are blacklisted; all 9 Terracotta interfaces remain untouched.
- **All three UIs**: Qt gains four pages (NBT studio / recipe workshop / tuning / API browser); pywebview and Electron share the same four navigation pages in `app.js`. Everything still uses first-show loading, background threads and function-level lazy imports; the source remains Python 3.10+ compatible.
- **Bug fixes**: `save_repair.list_world_candidates()` raised `UnboundLocalError` when the saves folder was missing, breaking first load on a fresh machine — fixed with a regression test. Also fixed `nbs_open` missing its `path` field, JSON-array pointer handling, a form index mismatch in numeric tuning, a duplicated `craft-pick` action, and the empty-path fallback in `tune_server_write`.

### Build and verification

- **Executable**: `dist/MikanCL.exe` rebuilt with Python 3.15.2 + PyInstaller 6.22.3 — **369.8 MB** (includes the 149.4 MB Electron bundle, 7 min 29 s); `FileVersion` / `ProductVersion` are **5.4.6**. The previous 5.4.5 binary is kept as `dist/MikanCL-5.4.5.exe`.
- **Compilation**: 112 `mc_launcher/*.py` + 13 `tests/*.py` compile cleanly on 3.15.2; `node --check app.js` passes; every new CSS class is defined.
- **API parity**: all 314 frontend `call()` names resolve to the 339 backend methods (40 new-prefix calls included), 405 `ACT` definitions with no duplicates; Terracotta untouched.
- **Regression tests**: 38 + 20 + 38 + 30 = **126 tests, all passing**.
- **Qt offscreen smoke test**: all four new Qt pages were constructed, shown, first-loaded and shut down under `QT_QPA_PLATFORM=offscreen` without exceptions; drag MIME, placeholder icons and 3×3 recipe modelling verified too.
- **Caveats**: real item textures require local version jars / resource packs / mod jars; placeholders appear otherwise. To keep the binary small, `PySide6.QtSvg` is excluded from the bundle, so SVG placeholders fall back to lettered colour swatches in the Qt exe only; the WebView2 / Electron builds render SVG directly. Real PNG textures work everywhere. Biome and structure previews remain high-fidelity approximations. RCON and multi-instance direct connect are verified at the protocol / UI / wiring level only.

## v5.4.5: backup centre, custom height, LAN hub, datapack editor

- **Backup centre (all three UIs)**: one index for auto-launch, Creator and save-repair backups (world detected from the zip's root folder). Per-world retention limit (1–200) deletes the oldest backup of that world automatically; delete single archives or all backups of a world, open the backup folder, clean up on demand.
- **Custom height in the world map preview**: `TerrainGen.java` source v7 adds a relief scale (0.1–5), sea level Y and min/max world Y, plus a height histogram and observed surface range. Old 5- and 10-argument calls stay compatible.
- **Native LAN hub (Terracotta kept)**: host a headless `server.jar` (EULA must be accepted explicitly; no automatic download), then launch multiple clients from the same UI with auto `--server/--port` to 127.0.0.1, distinct offline names and separate logs. Instance management, LAN address / port checks and clean shutdown included. No virtual NIC is needed on one machine.
- **God view over RCON**: player list, arbitrary commands, op / deop / ban / kick / whitelist; on 1.13+ sample coordinates, inventory and motion via vanilla `/data get entity`, with an in-memory track. Flight detection is a heuristic hint only. Region auditing included.
- **Visual datapack editor**: read vanilla JSON recipes from worlds, mod jars and version jars; edit shaped / shapeless / cooking recipes and loot-table weights in a 3×3 grid, then generate a `pack.mcmeta` + `data/**` zip straight into `datapacks/`. JSON preview, export and deletion supported.
- **Runtime optimisation, with honest limits**: Windows user mode has no KSM, so a Python launcher cannot force two JVMs to share physical pages; hot-injecting a mod jar cannot work either (Instrumentation only rewrites method bodies, registries freeze at boot, Mixin runs at first class load). Instead: JVM memory profiles (CDS/AppCDS, G1 string dedup, per-instance heap sizing) plus mod change watching and a one-click apply-and-restart queue.
- **Python 3.15 lazy imports**: development/validation moved to 3.15.2; a cross-version `lazy.py` optionally enables PEP 810 on 3.15 and skips on older interpreters. All new code uses function-level lazy imports and background threads; sources remain 3.10+ compatible.

### v5.4.5 build and verification

- **Artifact**: `dist/MikanCL.exe`, 369.6 MB, PyInstaller onefile; Windows `FileVersion` / `ProductVersion` are both **5.4.5**; includes the 149.4 MB Electron standalone bundle. Rebuilt on 2026-11-15 17:50 with Python 3.15.2 + PyInstaller 6.22.3 (6 min 13 s). The previous `dist` binary actually carried version **5.4.3** (not 5.4.4) and is kept as `dist/MikanCL-5.4.3.exe`.
- **Validation**: 118 `.py` files compile without errors on 3.15.2; `node --check app.js` passes; all 274 frontend `call()` names resolve to `shell.py` methods; `TerrainGen.java` source v7 compiles and runs with 5 / 10 / 15 arguments; the version string matches in 7 places; Terracotta APIs are untouched.
- **UI smoke test**: PySide6 6.12.0 is available on 3.15.2. The three new Qt pages were constructed, shown, refreshed and their worker threads joined under `QT_QPA_PLATFORM=offscreen` with no exceptions. pywebview and Electron share `app.js`, so all three UIs are covered.
- **Version control**: commit `e441637` (v5.4.4 `eb7d0a7`, baseline `7bc2b48`), clean worktree; all build output is ignored by `.gitignore`.
- **Not end-to-end tested**: no `server.jar` was available, so the RCON god view and one-click multi-instance join were verified at protocol, widget and wiring level only. Biome and structure previews remain high-fidelity approximations; real terrain is generated by the game from the seed.

## v5.4.4: save repair, biome / structure preview, creator usability

- **Save repair (all three UIs)**: the new `save_repair.py` diagnoses corrupted worlds — it validates every Anvil chunk, reads the seed from `level.dat` / `level.dat_old`, and reports every issue. Every repair starts with a full zip backup, automatically pruned by the configurable backup limit.
- **Let the game rebuild the terrain**: corrupted chunks only have their region index entries cleared, so Minecraft regenerates their terrain, biomes and structures from the original seed. Intact chunks are never touched. "Same-seed rebuild" creates a new world with identical seed, rules and spawn but no region files, then migrates intact player data, advancements, stats and scoreboards.
- **Perlin noise completed**: the bundled Java generator is now source version 6, adding a user-defined world range (center X/Z + radius), 19 biome colors, and MC-style structure placement (villages, desert / jungle temples, swamp huts, ocean monuments, pillager outposts, woodland mansions, strongholds). This is a high-fidelity approximation; the game still generates the real terrain from the same seed.
- **Scoreboard tab** added to the web / Electron frontend, with lazy async loading; configurable maximum backup count so creator backups no longer pile up forever.
- **Every creator field explained**: tooltips for all numeric inputs, dropdowns, checkboxes and table headers, plus a "Field help" window in the classic UI. Five status-effect presets with one-click batch apply to every player, each with its own forced backup, transaction and readback verification.
- All new work uses lazy imports and background threads; the project is now under git with a `.gitignore`.

## v5.4.3: newer-version save fields and full value / object editing

- **Fields only newer versions have**: the World tab gains a "newer-version world fields" group — world name `LevelName`, rain ticks `rainTime`, thunder ticks `thunderTime`, clear-weather ticks `clearWeatherTime`, `LastPlayed` (TAG_Long, ms timestamp), `SpawnAngle` (1.16+), `WanderingTraderSpawnChance` / `WanderingTraderSpawnDelay` (1.14+), `DifficultyLocked`, `initialized` and `MapFeatures`. Fields are hidden and never submitted when the save predates their first version, so old saves never receive invalid NBT.
- **GameRules generated per save version**: beyond the 12 always-visible toggles, the remaining rules follow `DataVersion` and cover insomnia / patrol / trader spawning (1.14), forgive dead players and universal anger (1.14.4), sleeping percentage (1.17), warden spawning (1.19), vine spread (1.19.3), snow height and command block limit (1.19.4), the three explosion drop-decay rules and water / lava source conversion (1.20.1), fall / fire / drowning / freeze damage, global sound events and spawn chunk radius (1.21.2) — 44 rules in total, with integer rules entered as ticks or counts instead of a plain toggle.
- **All player values / all world values**: two collapsible grids list every scalar in `level.dat` and the player data, grouped by field, filterable, and only changed entries are submitted. 64-bit longs such as `RandomSeed` and `LastPlayed` travel as strings so the front end never loses precision. Covers weather timers, world border, seed, spawn angle, dragon fight, wandering trader, boss events, data packs, deep `WorldGenSettings` fields, and player Air / Fire / FallDistance / PortalCooldown / DeathTime / HurtTime / LastDamage / AttackTime / SleepTimer / XpTotal / XpSeed / Score / SelectedItemSlot / all state flags / Motion / Rotation / every ability speed and toggle.
- **Full item and block catalogue**: scans the selected version's own resources (1.21.2+ `assets/<ns>/items/*.json`, 1.13–1.21.1 `models/item/*.json`, 1.12- `.lang`). The candidate list stays visible, filters locally as you type, and falls back to spelling similarity when nothing matches exactly.
- **Place blocks / fill regions at coordinates**: choose dimension, coordinates, block ID and block properties; one fill is capped at 262,144 blocks. On 1.12- saves block properties are ignored with a notice, and chunk sections and palettes expand automatically.
- **Spawn / clear entities at coordinates**: spawn by coordinates, count (1–256), spread radius and custom NBT, or clear within a range. Every operation goes through token validation, a world lock, a forced backup and transactional rollback.
- **Item detail values**: max damage, repair cost, unbreakable, rarity, enchantment glint, food nutrition and saturation; clearing a field back to its default removes the NBT tag. Item counts are no longer forced non-negative and only follow the NBT type of that version.
- **Full attribute quick editing**: attack range, block / entity interaction range, mining efficiency, movement speed, max health and every other vanilla attribute, with the ID form switching automatically between the `generic.` prefix, namespaced IDs and the short IDs introduced in 1.21.2.
- **Localized effects and enchantments, plus expert mode**: 39 status effects and 42 enchantments show their official Chinese names in beginner mode; the "expert mode" toggle at the top of the panel switches to the raw `minecraft:` IDs (identical in the classic and web UIs). Entries are filtered by save version, numeric IDs are written before 1.20.2 and namespaced IDs after, and invalid IDs raise a clear message instead of being ignored.
- **Enchantment layout per version**: `ench` (short id / lvl) on 1.12-, `Enchantments` on 1.13–1.20.4, component-based `minecraft:enchantments.levels` on 1.20.5+, and all three formats are read.
- **Fixes**: the `KeyError: 'creator'` crash caused by the missing "Save Creator" toggle on the settings page, and the `${user_properties}` entry missing from the launch variable table.
- **Packaging**: unused Qt modules are still excluded, but the QtWebEngine runtime dependencies (QtQml / QtQuick / QtPositioning / QtOpenGL / QtOpenGLWidgets / QtPrintSupport) are kept, otherwise the classic built-in browser and Microsoft login crash on startup. The single-file `MikanCL.exe` is about 366 MB.
- **Docs and tutorials**: the tutorial centre is updated to revision 6 with the new version fields, expert mode and object editing.

## v5.4.2 improvement: read the save first, range hints and per-version slots

- **No more default preset**: opening a save or switching player fills health, absorption, hunger, exhaustion, XP, invulnerability, flying, difficulty, GameRules, position and items from the actual NBT; only fields you changed are submitted.
- **Field range hints**: every input shows min / max and a vanilla note, with caps derived from the save's version (health 0-1024, hunger 0-20, XP progress 0-1, position ±30,000,000, ender chest 0-26).
- **Legacy offhand and ender chest hints**: 1.8 and earlier have no offhand slot; 1.9-1.11 store it as -106; 1.12+ as 40; ender chest is 0-26. Unsupported slots are reported in the preview.
- **More player fields**: absorption `AbsorptionAmount`, exhaustion `foodExhaustionLevel`, XP progress `XpP`, invulnerability `Invulnerable`, flying `Flying` / `Mayfly`; the world tab adds difficulty, hardcore and allow-commands.
- **Nothing written when nothing changed**: an explicit "no changes detected" message replaces a pointless backup and write.
- **Tutorial, docs and i18n** updated, with new strings registered in the `CreatorPage` translation context.

## v5.4.1 fix: Save Creator edits now take effect

- **Write target matched to the save version**: 1.12 and earlier write `level.dat → Player`; 1.13+ treats `playerdata/<UUID>.dat` as authoritative; 26.1+ is detected as `players/data/<UUID>.dat`. Every copy of the same player is updated together, so the panel no longer reports success while the game ignores the change.
- **Read-back verification**: after each save the files are reloaded and health, XP, game mode, attributes, effects, time and weather are compared; failures list the exact fields instead of a bare "success".
- **Version shown per save**: the world list and panel header show the Minecraft version (from `Version.Name`, then an exact `DataVersion` map, with pre-`DataVersion` worlds labelled as 1.8.x legacy Anvil).
- **Per-version field formats**: 1.8 writes both `Health` and `HealF` and uses an integer `Dimension`; 1.20.5+ effects use `active_effects` with string `id`; 1.21+ attributes use `attributes` / `id` / `base` / `modifiers` with named operations; 1.20.5+ enchantment components store `levels` as an `{id: level}` map.
- **Items scanned from the save's own version**: reads `assets/<ns>/items/*.json` (1.21.2+), `models/item/*.json` (1.13–1.21.1) and `.lang` (1.12-) from that version's jar.
- **Weather and difficulty actually apply**: weather rewrites `rainTime` / `thunderTime` / `clearWeatherTime`; 26.1+ difficulty goes to `difficulty_settings`.
- **Startup crash fixed**: `name 'extra_jvm' is not defined` no longer appears.

## New in v5.4.0: Save Creator (cross-era deep save editing)

- **New page**: the sidebar gains "Save Creator" with Status, Inventory, Ability, World and Tools tabs that read and write `level.dat`, `playerdata/<UUID>.dat`, `advancements/<UUID>.json`, server `ops.json` and region files directly.
- **Status**: position, hunger and saturation, health, XP level, game mode, dimension and attributes. "Safe teleport" scans region files for the surface at the target X/Z on save and keeps the original Y with a warning when the chunk is not loaded.
- **Inventory**: 27+9, armor, offhand and ender chest. "Scan item IDs" reads language files from local version and mod jars, then you can freely set count, damage, enchantments, attribute modifiers (attack damage / armor / movement speed / attack speed / max health) and raw NBT; untouched display names, lore and container contents are preserved.
- **Ability**: attributes support per-entry modifiers (add / multiply); effects expose ID, amplifier, duration and particle visibility.
- **World**: time, weather, 11 common game rules (including randomTickSpeed), world border size and center, spawn point.
- **Tools**: tick individual advancements, edit `ops.json` (levels 0-4), global block replacement, legacy-format conversion entry, list and restore backups.
- **Cross-era**: saves from `rd-132211` (2009) onward are converted to Anvil first; flattened IDs (1.13+) and item components (1.20.5+) are detected automatically and written with era-correct NBT types; saves that cannot be migrated safely open read-only.
- **Vanilla caps**: health 1024, enchantment 255, XP level 21863, random tick speed 4000, with no bypass.
- **Safety**: exclusive `session.lock` check, full forced backup with SHA-256 manifest, transactional writes with rollback; a failed rollback keeps the journal for manual recovery.
- **All three UIs**: Classic (Qt), Enhanced (pywebview) and Standalone (Electron) share the same `creator_service`.
- **Agreement**: bumped to 1.10 with player, advancement, OP and chunk editing, type migration, locking and rollback terms.
- **Trimmed build**: only components actually referenced by the code are shipped — translations are `.qm` only, unreferenced Qt modules (QtSvg / QtDBus / QtOpenGL and others) are excluded, Electron locales keep only zh-CN / en-US, and bytecode uses `--optimize 2`. The single exe is about 328 MB; the Electron bundle is about 149 MB.

## New and fixed in v5.3.1

- **Standalone edition bundled into the single exe**: the Electron runtime is embedded as a compressed payload inside `MikanCL.exe`, so no separate build or download is required. On first switch it is extracted to `data/electron/app` and reused afterwards
- **Fixed "Standalone" doing nothing**: the v5.2.0 packaged backend did not recognize the `electron` value, showed "invalid frame argument", and reverted to Classic after restart. v5.3.1 rebuilds all three entry points: first-run dialog, Qt settings and web settings
- **Switch back to the main launcher**: choosing Classic / Enhanced inside Electron relaunches the main launcher; if the launcher cannot be found, you get a clear message instead of restarting Electron itself
- **Readable first-run dialog**: added a dark background so the three cards stay legible on light system themes
- **Standalone troubleshooting log**: extraction and launch steps are written to `data/logs/electron.log`
- **Larger but self-contained**: the single exe is about 160 MB larger than v5.2.0 and starts a little slower on first run, but ships Classic, Enhanced and Standalone together
- **Forbric parity in the web UI**: after the guided installer finishes, the Enhanced / Standalone UI registers and selects a "Forbric 26.2" instance and prefers Java 21, matching the Classic edition
- **Fix crash after in-app restart**: restarting from the settings page spawned a process that inherited PyInstaller's `_PYI_*` variables and reused the already-deleted extraction folder, showing "Failed to load Python DLL … python315.dll". These variables are now stripped before every restart, including handing back from the Standalone edition and reopening after an update. Launching the exe by double-click was always fine because Explorer provides a clean environment
- **Clearer first-run choice**: the whole framework card is clickable and the dialog shows the current choice ("✓ Classic · Qt"); the frame actually entered is written to `data/logs/launcher.log`

## New in v5.2.0 (history)

- **Standalone "Version Settings" page in the Polished edition**: fully ports all 7 tabs of the Classic edition's Version Settings (Overview, Game Settings, Mods, Resource Packs, Shader Packs, Modpacks, Version Management), including launch-script export, batch health check/repair, batch config export, saves and backups, and the world seed / screenshots / crash reports / mod graph / dependency tools; instances and versions can be switched at the top
- **Save format conversion and legacy world import**: multi-threaded conversion from 2009 Classic / Indev / Alpha / McRegion → Anvil → target game version, with block ID remapping and automatic backups; old naming schemes (`server_level.dat`, `*.mine`, a single `level.dat` inside a Classic archive) are detected and can be converted and imported in one click
- **Java package switching**: the Java Center supports ZIP / MSI / EXE installers; the ZIP variant is extracted automatically and its `bin` directory is added to PATH
- **Empty-state guidance**: when there is no version on the home page, no search in the Content Center or no task in the Download Center, the page now offers a "What to do next" button with a short tutorial and a direct link to download a version or install a modpack instead of just "Nothing here"
- **Adjustable glass effect**: Settings → Appearance adds sliders for glass brightness, corner radius, button size and text color, with one-click reset
- **Global drag and drop**: drop a mod or a whole mod folder to choose which version to import into; drop a modpack to choose "attach to an existing version" or "download a fresh vanilla version first"
- **Common / Advanced parameter views**: only common parameters are shown by default, with a "Show all" toggle
- **Rollback safety net**: "Restore the last launchable configuration" plus export of the current JVM / modpack configuration as a shareable `.mikan` snippet
- **Easier navigation**: a "Recently used" entry, related-feature suggestions at the bottom of feature pages, and a `Ctrl+K` command palette
- **Clearer launch summary**: after launching, the launcher explains which parameters were applied automatically (G1GC, memory, skipped custom GC flags) instead of hiding them in the log
- **Save metadata tools**: a save editor for world name, game mode, difficulty, weather, time, spawn point and common rules, plus retagging a world's `level.dat` to a target game version (the full format conversion is covered by "Save format conversion and legacy world import" above); `level.dat` is backed up automatically before writing (last 5 copies kept)
- **Multiplayer address probe**: the address generated by Terracotta is probed automatically for availability and latency, with a manual retry button, in both editions
- **User-chosen folders**: backup, download, world import target and modpack install locations are all chosen by the user instead of hard-coded defaults

## Fixes and Additions in This Round (Patch Update)

- **Switch framework dialog fix**: The restart command was changed to the standard empty-title form `start "" <program>`; previously `start MikanCL <program>` treated `MikanCL` as the file name to run, popping up "Windows cannot find 'MikanCL'"; restarting in source mode now uses `run.py` (the project has no `mc_launcher/__main__.py`)
- **Close acceleration**: Clicking close now persists the configuration first, then ends the process directly, skipping WebView2 environment teardown, so exiting no longer hangs for 1~2 seconds
- **Light mode backdrop**: The window base board and the pywebview background color follow the light/dark mode switch; daytime uses a light base and no longer leaks a dark "blackboard" block
- **Custom font color**: Settings → Appearance adds a "Font color" picker, which can customize the body text color or restore "Follow theme" in one click; after changes, muted text and the color picker are refreshed in sync and persisted with the configuration
- **High-version skin pack fix**: The root cause was that vanilla 1.19.4+ has 9 default skins assigned by player UUID, while the old resource pack only covered steve / alex; now the names of all 9 default skins are written with the same skin in both the `player/wide` and `player/slim` directories, so any UUID hits it
- **Skin pack auto-replacement logic**: It no longer "skips whenever any MikanCL-*.zip exists", but validates by "skin content fingerprint + arm model + version pack_format + actual pack location", and rewrites automatically after changing skin or upgrading the version; the fill-missing button validates before writing, and distinguishes "Updated / Already up to date"
- **Import skin pack to a specified version**: The Polished edition skin pack card adds a version dropdown and "Import skin pack…", which can import directly into the isolation directory of the selected installed version (the Classic edition's existing version dropdown remains available)
- **Home "recent skins" fix**: Previously the thumbnail only handled `data-skin`, and the `data-skin-path` used by the home page was not rendered, leaving the cards blank; now the head is cropped and displayed uniformly, and "skin library + current account skin + PNGs under data/skins" are merged, so it displays even when the skin library is empty
- **Classic edition home recent skins**: The Classic edition home page adds a "Recent skins" card, consistent with the Polished edition; clicking switches the skin directly and automatically adapts to installed versions

## Content Center and Instance Detection (This Round)

- **Mod details choose the game version first**: Clicking a project no longer expands all versions at once, but groups them by supported Minecraft version first; only after selecting a version are the Jars available for that version loaded and displayed grouped by "stable / beta", with file rows labeled with version type, loader, date and size
- **Required dependency check**: After entering the file list, the names and icons of required dependencies are resolved automatically; missing or additionally required dependencies can be clicked to jump directly; required dependencies are still filled in automatically during installation
- **PCL-style search categories**: The Content Center adds usage categories "All / Optimization / Technology / Magic…", and supports combined filtering by source, loader and game version; types are split into Mod, modpack, resource pack, texture pack and shader pack
- **Texture packs and resource packs separated**: Search types and copy now fully distinguish resource packs (resourcepack), texture packs (texturepack) and shader packs (shader), no longer conflating the three
- **Terracotta multiplayer share code**: The Polished edition multiplayer page adds create room, join room, end multiplayer and "Copy share code"; after creation it polls room status automatically and shows the room code in the card; the room code format is normalized automatically before joining
- **Data directory auto-detection**: When adding a data directory, it automatically recognizes the `.minecraft` root directory, the `versions` directory or a single version folder level, and switches to that directory; even if a version folder lacks a version JSON, as long as a game Jar exists in the directory it appears in "Installed versions" under the folder name (effective in both the Classic and Polished editions)

## Packaging Method (This Round)

- **Single-file exe**: `python build_exe.py` was changed to PyInstaller onefile, packing PySide6, pywebview, toolbelt and all frontend resources into a single `MikanCL.exe`, so distribution only needs one file; the first launch extracts the runtime first, which is a few seconds slower than onedir
- **Why PyInstaller (pyi)**: Nuitka has not yet adapted to Python 3.15 and cannot compile under Python 3.15; PyInstaller already supports Python 3.15, so v5.2.0 is packaged with PyInstaller without affecting features or runtime behavior

## UI Framework

- **Dual-framework first-run choice**: On startup a lightweight Qt selection dialog explains the differences and missing features of the Classic / Polished editions; after choosing, only the corresponding framework is loaded, and the other one does not occupy memory
- **Polished edition switched to pywebview + Edge WebView2**: Tile-style glass sidebar, floating glass cards, gradient launch button, theme panel and recent skins; rendered by Chromium, with visuals close to the referenced mainstream launchers
- **WebView2 Runtime distribution**: Registry + install directory detection; a dialog guides the download when missing; supports a bundled fixed version in the install directory `webview2/` (`WEBVIEW2_RUNTIME_PATH`); on rendering failure it prompts and can switch back to the Classic edition directly
- **Two-way framework switching**: The Classic and Polished editions share the same configuration, accounts, instances and download core; "Settings → Appearance → UI framework" can switch between them at any time (`switch_frame` + automatic restart), and the framework is no longer locked; the old `frame_locked` in existing configs is invalidated automatically
- **Frosted glass and fonts**: The Polished edition fully moves to semi-transparent frosted glass (`backdrop-filter`, with sidebar / title bar / status bar / cards / popups uniformly glassified), theme colors are overlaid in light tints on the frosted glass and follow theme switching; fonts switched to `Microsoft YaHei UI`, size 13.5px, line height 1.55, ClearType subpixel rendering restored on Windows, fixing blurry small text; low-end GPUs can disable frosted glass and animations with one click in settings

## Feature Parity

- **Full page set**: User agreement, home, Download Center (game versions / loaders / Java / Bedrock / download accelerator / tasks), Content Center (Modrinth / CurseForge), Instance Manager, accounts and skins, multiplayer, toolbox, Tutorial Center, built-in browser and settings are all available in the Polished edition
- **Shared download capability**: Games, loaders, content, Java, Bedrock and modpacks all go through the same multi-threaded downloader, supporting pause / cancel / resumable download and a concurrency cap; the Polished edition adds a "Download accelerator" tab, where pasting any direct link downloads with the same segmented downloader, with up to 328 threads
- **Aligned launch flow**: A complete checklist runs before launch (Java, memory not exceeding 70% of physical memory, mod conflicts, disk space > 2 GB, integrated GPU + shader warning); blocking items require user confirmation before forced launch; supports multi-select sequential batch launch, exporting bat / ps1 / sh launch scripts, version isolation and automatic world backup before launch
- **Account system**: Offline, Microsoft device-code account login, authlib-injector login; skin import, quick switching and Steve/Alex model switching
- **Skin workshop**: The Polished edition adds a 64×64 pixel canvas (brush / eraser / fill / eyedropper / undo) and a CSS 3D skin preview (drag to rotate, scroll to zoom); saving adds it to the library and applies it; skin packs support specifying the player, version, arm model and cape PNG
- **Version settings**: The instance page can directly edit per-version memory, isolation, process priority, window title, extra JVM / game arguments and auto-join server; the mod list supports enable / disable / delete; instances support move up / move down sorting that persists
- **Content and data tools**: Screenshot gallery (preview / export Zip / delete), crash reports (view / copy summary / delete), seed terrain preview (reusing the vanilla Perlin noise Java program), NBT editor (type tree + leaf editing + automatic .bak)
- **Toolbox**: Dependency scan and completion, third-party components, mod dependency graph (missing dependencies and circular dependencies highlighted), world backup / restore, logs, modpack and HMCL/PCL import, cache cleanup
- **Multiplayer**: Server list add/remove, Minecraft Server List Ping, connect on launch, Terracotta multiplayer install / start / stop
- **Tutorials and browser**: The Tutorial Center reads Markdown by UI language (9 built-in articles, auto-filled when missing); the built-in browser is a standalone WebView2 window that can play Bilibili videos directly
- **Content file management**: The instance page adds Mods / resource packs / shader packs category tabs, supporting enable / disable / delete / open directory, consistent with the Classic edition's `.disabled` convention
- **Save As**: The Polished edition completes all "Save As" entry points of the Classic edition — the content detail page can download without installing (Mod / modpack / resource pack / shader pack), the download page version row can save the vanilla client Jar separately, and the loader page can save the Forge / NeoForge / Fabric / Quilt / LiteLoader official installers separately, all through multi-threaded segmented download saved to a folder specified by the user
- **Task center parity**: Failed / cancelled tasks add "Retry", restarting with the original task parameters; pause / resume / cancel / clear completed and error details are retained
- **Instance repair**: The instance page adds "Repair instance", which validates and completes vanilla and loader files in one click, and automatically updates the instance version record afterwards
- **Home version list**: Adds a version search box (shown when there are 6 or more versions) and drag-and-drop sorting; the sort result is written to `config.version_order` and applies to both the Classic / Polished editions
- **Version manifest parsing fix**: The Polished edition download page previously did not unwrap the manifest cache wrapper, which made the vanilla version list empty and installation impossible; this is fixed, and vanilla / loader installation works again
- **Modpack export**: The instance page adds "Export modpack", which can package as a `.mikan` private backup or as a CurseForge modpack zip with `manifest.json` (including mods / resource packs / shader packs / config / options.txt)
- **Settings page parity**: Adds download source management (add / edit / delete / enable / set current / connectivity test, sharing `config.sources` with the Classic edition), content sources and mirrors (Modrinth CDN, CurseForge API Key / CDN), account and login (Microsoft OAuth Client ID, authlib-injector address), data directory section management, extra JVM arguments, window title and launch animation toggle
- **Settings**: Theme (including import / export JSON and switching), background image, language, memory, Java, isolation mode, threads (1~328), speed limit, proxy, game optimization toggles, preload JVM, feature module toggles, minimize on close, backup and agreement viewing; switching the UI language also syncs the agreement and tutorial content
- **User agreement upgraded to 1.7**: Adds notes that the two frameworks can switch both ways and share the same data, that frosted glass is rendered by WebView2 (Chromium) and DWM respectively, and that fonts are optimized for ClearType; synced across 5 languages (Chinese / English / Russian / French / Japanese)

## Window, Extensions and Wallpaper

- **Borderless window resizing**: In the Polished edition, all four edges / four corners can be dragged to resize the window, the title bar double-click maximizes, and the minimum size is 960×600; resizing is executed through Win32 window APIs and still matches mouse displacement under DPI scaling
- **Extension (plugin) mechanism**: Settings adds an "Extensions" page, supporting import of `.zip` / `.mikan-ext` extension packages, enable / disable / delete, open extension directory and refresh; enabled extensions add an entry in the sidebar, pages run in a sandboxed iframe and can call launcher bridge interfaces (accounts, versions, downloads, files, etc.) via `postMessage`; Python plugins under the Classic edition's `data/plugins` are listed as well
- **Dynamic wallpaper**: The Polished edition supports looping muted playback of MP4 / WebM videos and GIF / WebP animations, with a built-in local media service with Range support started on demand, and playback pauses automatically when the window goes to the background; the Classic edition supports GIF / WebP animated wallpapers (QMovie fills the window frame by frame), sharing the same settings as static background images
- **Skin workshop canvas zoom**: The canvas supports 2×–12× zoom and a scrolling viewport, so in small windows or at high zoom you can scroll up and down to the leg and foot pixels, fixing the previous inability to paint the feet; the Classic edition canvas is also placed in a scrollable viewport and can be scrolled after 6×/8× magnification

## Sidebar and Themes

- **Vertical icon sidebar**: The sidebar becomes a single vertical column of icons, showing only icons by default, with the name floating out on the right only on mouse hover; the content area is no longer squeezed horizontally, and the sidebar itself can scroll when there are too many entries
- **Multiple themes**: Adds 8 built-in themes (Forest Green / Ocean Blue / Twilight Purple / Crimson / Amber / Teal / Sakura Pink / Polar Night Blue), replacing the whole palette rather than only the accent color
- **Custom theme API**: Place `data/themes/*.json` or import through the settings page; supports exporting a template; plugins can call `themes.register()` to register dynamically; the default Forest Green keeps the original hue-rotation look
- **Quick skin switching**: Imported skins are added to the library automatically (sha1 deduplication, most recently used first, up to 60 entries); clicking the sidebar avatar pops up a "Recent skins" menu for one-click switch / import / open skin library

## Desktop Frosted Glass and Tile Navigation

- **True see-through desktop frosted glass**: Settings adds "See-through desktop (true frosted glass)", where the window background is composited by DWM to truly show the system desktop (Win11 uses `DWMWA_SYSTEMBACKDROP_TYPE=3`, Win10 falls back to `SetWindowCompositionAttribute` acrylic); when enabled, background images and dynamic wallpapers are ignored automatically and video playback paused, and the original background is restored immediately when disabled
- **Frosted glass intensity adjustment**: A 0–100 slider controls blur radius, tint density and card transparency in real time; the Polished edition previews while dragging, and the Classic edition's "Settings → UI effects" provides the same slider; both UIs share the `glass_strength` configuration
- **Windows 8 style glass tiles**: The sidebar is a single vertical column of glass tiles with centered icons and text hidden by default; the name floats out and lifts on hover, and the selected state has a theme outline; shadows are split into two layers, "outer drop shadow + inner highlight", retaining clear hierarchy over glass backgrounds; the Classic edition also becomes an 84px icon column + ToolTip

## Fixes

- **Black screen on startup**: The Polished edition window is created hidden + transparent and only shown after the first frame is drawn, at which point DWM glass is applied, no longer flashing a black base first
- **Version settings crash**: Fixed `version_settings` throwing `NameError: name 'ISOLATION_LABELS' is not defined`
- **Avatar cropping**: No longer stuffing the whole 64×64 skin into the avatar frame; the head is cropped uniformly by pixel position (face + hat layers); consistent across the sidebar, home, account page and recent skins list
- **One-click skin pack overwrite**: Adds "One-click overwrite install", which first cleans old skin packs in each game directory and then writes the current skin, supporting a specified player name, version, arm model and cape

## Fixes and Completions in This Round

- **Window can only be dragged by the top bar**: The Polished edition disables pywebview's whole-window `easy_drag` and uses pywebview's native drag-region (`DRAG_REGION_SELECTOR=.pywebview-drag-region`); only the left side of the title bar can be dragged, and controls such as the frosted glass intensity slider drag normally again; double-clicking the title bar toggles maximize
- **Right-click menu click not responding fix**: The menu itself intercepts `pointerdown` so it no longer bubbles, preventing the `document` close listener from removing the menu before `click` is dispatched; confirmation dialogs uniformly use the built-in `ask`, avoiding WebView2 blocking the native `confirm`
- **Frosted glass truly shows the desktop**: The Polished edition's web scrim was lowered from `.42/.56` to `.04/.10`, and the sidebar / top bar / status bar / cards use intensity-driven `--glass-a` / `--glass-a2` (cards keep a minimum tint so text is still readable over white backgrounds); toggling the switch or changing the intensity re-invokes the backend `glass_apply`, effective immediately in the packaged build too
- **UI misalignment fix**: Adds a `.flow` streaming page, where cards expand naturally with content and are no longer squashed by flex; the toolbox (dependency completion), Instance Manager and multiplayer pages switch to full-page scrolling, with the instance list / server list scrolling internally under their own height limits
- **Double-click quick install in the download list**: In the Polished edition Download Center, double-clicking any vanilla version row (or clicking "Details") opens the install details, where you can choose vanilla / Fabric / Quilt / Forge / NeoForge / LiteLoader / Forbric and pick the loader version, completing download and installation in one go without a separate trip to the loader page afterwards; Forbric still strictly validates 26.2
- **Home instance quick switching**: An instance dropdown is added next to the home version dropdown; after switching, the data directory switches immediately and the version list refreshes
- **Version settings entry**: Version details and the context menu add "Version settings", for configuring memory, isolation mode, process priority, window title, extra JVM / game arguments, auto-join server and port, with fields identical to the Classic edition
- **Bedrock PowerShell lookup fix**: Falls back to `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` when PATH is trimmed, with a fallback for `OSError`, preventing the Bedrock directory interface from throwing `FileNotFoundError`
- **Version details submenu completed**: In the Polished edition version list, clicking `›` or right-clicking opens version details, including launch / game directory / version directory / Mods directory / delete, loader type (6 kinds) and version dropdown, install or change loader, save installer, mod list enable / disable / delete and conflict hints; the context menu adds open game directory / version directory / Mods directory / copy version ID
- **Loader version display fix**: The Polished edition dropdown refetches by the current MC version and correctly echoes `selected`, clearing the old version when switching loader or MC; the Classic edition removes the hardcoded `0.16.10 / 49.1.0` defaults, so leaving it blank installs the latest stable version, and the MC version is brought in automatically from the current detail version
- **Delete download task (both editions)**: The Download Center adds "Delete task" per row; running tasks are cancelled first and then removed (already downloaded files are not deleted); the Polished edition goes through `task_delete`, and the Classic edition through `DownloadManager.remove`
- **Skin import gains arm type and overwrite**: The Polished edition import panel provides Steve / Alex radio options and an "Overwrite all installed versions" checkbox; quick skin switching follows the recorded model. After import or switching it automatically scans installed versions and generates adapted skin packs one by one via `resolve_game_dirs(...).skin_targets()`; when installing a new version / modpack later, `_auto_skin` completes it automatically, with no manual overwrite needed. The Classic edition account page also adds the overwrite checkbox and automatic adaptation, and quick skin switching in the sidebar also writes to each version
- **Fully isolated by default**: The `isolation_mode` default value, the `from_dict` fallback and the invalid-value fallback are all unified to `all`, so newly installed versions use the separate `versions/<id>/game` directory by default
- **Content overflow changed to scrolling**: The Polished edition `.stage` becomes `overflow-y:auto` with thin scrollbars added, so long content such as download tasks, settings and version details is no longer squeezed hard; the Classic edition pages were already in `QScrollArea`, and changing the sidebar to an icon column no longer squeezes the main content
- **Vertical single-column sidebar**: The Polished edition sidebar is 68px wide, a single column of icons + hover name (`.nav-tip`); the Classic edition sidebar is 84px with `ToolButtonIconOnly` 48×48 icons and retains ToolTip, consistent on both sides

## Performance and Build

- **Lazy imports**: QtWebEngine, the main window, Content Center and network modules are imported on demand per framework; when the Polished edition is selected, QtWebEngine is skipped entirely
- **Packaging changed to PyInstaller onedir**: No longer extracting on every launch; automatically collects pywebview / pythonnet / WebView2 interop assemblies; the whole `MikanCL` directory is distributed
- **Compatibility**: Adds configuration keys `frame_mode`, `frame_mode_asked`, `frame_locked`; old configs without them fall back to the classic Qt UI, requiring no manual migration; the version number is fixed at **5.1.0**, with README / RELEASE / i18n synced
- **Interface injection fix**: The Window / Config objects on js_api are marked `_serializable = False`, preventing pywebview from recursively walking WebView2 native COM objects during injection, which delayed or even broke interface injection (a "backend not ready" case appeared in non-debug mode); the frontend now polls `window.pywebview.api` continuously until ready, making the first launch more stable
- **First-run details**: A data directory dropdown is added next to the home version dropdown (shown when there are more than 2 directories); after switching, the version list refreshes immediately; the Java list uniformly shows bitness information

---

# MikanCL v5.0.0 Release Notes

Release date: 2026-11-07

## UI

- **Tile-style navigation**: The entire left navigation is changed to iOS / Bakaxl style tiles (3 columns, icon + short label), the sidebar is widened to 244px, and the selected state uses a theme-green outline
- **Frosted glass rework**: `WA_TranslucentBackground` is now always set before the window is created; Windows 11 uses DWM system acrylic (`DWMWA_SYSTEMBACKDROP_TYPE=3`), and Windows 10 falls back to BlurBehind; the root cause was that toggling the transparency attribute while running in the old version did not take effect, and AcrylicBlurBehind would blur the text. When enabled, the background is fully frosted glass, cards / buttons are semi-transparent white material retaining the theme accent color, and it is **off by default**
- **Page switch lag fix**: Removed the whole-page offscreen rasterization caused by adding `QGraphicsOpacityEffect` to `QScrollArea` (which was both laggy and blurred the text); page refresh now runs idle via `QTimer.singleShot(0, ...)`, and repeatedly clicking the current tile no longer refreshes again

## New

- **Genuine copy reminder**: Every 10 game launches, a "Support the genuine game!" prompt appears with two options, "Maybe next time" and "I'll go buy it now"; the latter opens the official store and provides an entry for purchasing the genuine game
- **Java scan completion**: Covers distribution directories under Program Files, Oracle javapath, the registry (including WOW6432Node), PATH, JDKs bundled with scoop / chocolatey / gradle / IDEs, the .minecraft runtime, HMCL / PCL directories and common paths on drives C–F; the same major version is collapsed by default, and right-click "View all Java versions" expands it
- **CurseForge update check**: `check_mod_updates()` adds CurseForge `/mods/fingerprint` (Murmur2 fingerprint) matching in addition to Modrinth SHA1, so "Check for updates" no longer skips half of the mods
- **World management + backup**: Version settings adds a world table (world / game mode / last played / size), supporting backup selected / all, restore backup and open backup directory; optional automatic backup before launch (deduplicated within 1 minute for the same world, keeping at most 20 copies)
- **Server list Ping**: Uses the Minecraft Server List Ping protocol (including legacy fallback) to show latency, online player count, MOTD, version and server icon, no longer relying on third-party APIs
- **Export script supports Linux/macOS**: Adds `.sh` generation (`#!/usr/bin/env bash`, automatic chmod 755)
- **Cape and elytra**: Skin packs / skin factory support importing 64×32 capes, written to `CustomSkinLoader/LocalSkin/capes`, and the 3D preview can toggle between cape / elytra forms
- **Offline self-check**: On startup it probes the version manifest and mirror sources; when offline it shows "Currently no network" and greys out network features in the navigation
- **Instance health**: Aggregates broken versions, missing files, mod conflicts / missing dependencies and memory over-allocation, shown as green / yellow / red in the version overview
- **Download speed limit**: Settings adds a global bandwidth cap (KB/s, 0 = unlimited), which applies to all download threads through a global token bucket
- **One-click missing dependency completion**: The dependencies page adds "Complete missing dependencies", automatically searching modid on Modrinth and installing the latest compatible version
- **Multi-instance batch operations**: Adds batch health checks, batch file completion and batch instance configuration export

## Architecture

- **ModpackPipeline**: `ModpackDropWorker` in `dropinstall.py` and `ContentInstallWorker` in `page_content.py` are merged into one "base version → loader → verify JSON → overrides" pipeline
- **resolve_game_dirs**: Isolation directory determination converges into `GameDirs` (main directory + isolation directory + skin / mods / world write targets); skins, the files page and imports call it uniformly, eliminating the repeated check that "skins have to be written twice when everything is isolated"

## Docs and Build

- User agreement upgraded to 1.5: adds notes on the fingerprint check and a disclaimer for world backups
- Tutorial Center adds "Launcher Quick Start: From Zero to In-Game", covering every step
- The build script changed to **Nuitka** (`python build_exe.py`, compiled to C for faster startup), with i18n translations updated
- Compilation: `python -m compileall mc_launcher` passes; offscreen smoke creation of the main window and traversal of all pages raise no exceptions

---

# MikanCL v4.9.4 Release Notes

Release date: 2026-11-06

## Fixes

- **Text ghosting when scrolling with the wheel in frosted glass mode**: With "frosted glass" enabled the window base color is semi-transparent, so when Qt repaints a region partially the previous frame's content was not erased, and after wheel scrolling card titles and body text overlapped with the new content into two layers of text (the packaged exe had frosted glass enabled in its default data directory while the source directory had it off, which is why it only surfaced on the exe before). The root container now uniformly uses `CompositionMode_Source` to directly overwrite the dirty region's base color (semi-transparent frosted glass uses `rgba(12,19,16,170)`, normal mode uses the opaque `#0c1310`), so every frame is drawn starting from a clean base color, and scrolling or page switching no longer leaves old text behind

## Build and Verification

- Reproduce: with the old exe (frosted glass on), after scrolling the wheel the page card text shows two overlapping layers
- Verify: running from source with frosted glass force-enabled, three consecutive scrolls with per-frame screenshots show clean pages with no ghosting; the repackaged exe with frosted glass on also shows no text overlap in consecutive scroll screenshots
- Compilation: `python -m compileall mc_launcher` passes (exit code 0)
- Artifact: `dist/MikanCL.exe`, 220,358,419 bytes ≈ 210.2 MB (2026-11-06 14:09:00), single file with all dependencies already embedded

---

# MikanCL v4.9.3 Release Notes

Release date: 2026-11-06

## New

- **Java Center supports official installers (EXE / MSI)**: The toolbar adds an "Install method" dropdown to switch between "ZIP portable" and "Official installer". Temurin / Azul Zulu / Amazon Corretto fetch the installer version list directly from the official APIs; after download, `msiexec` / the EXE wizard completes the installation (a UAC elevation prompt may appear), and afterwards it rescans automatically and shows the newly installed Java; distributions that do not provide installers keep only the ZIP option
- **ZIP portable auto-writes to the user PATH**: After the portable build is extracted and probed successfully, the Java `bin` directory is written automatically into `HKCU\Environment\Path` (existing entries are not appended again), while the current process PATH is updated and `WM_SETTINGCHANGE` is broadcast, so the command line, other launchers and games can all invoke it directly
- **Home "version folder" section**: A section dropdown and a "New / Select…" menu are added below the version list, allowing any local folder to be registered as a new version directory (a `versions/` subdirectory is created automatically when creating); after switching, the version list, mods and worlds all use the new directory, without interfering with modpack instances
- **Circular floating download button in the bottom-right corner**: Whenever there are download tasks (including queued ones), a circular button appears in the bottom-right corner of the window; left-click jumps to the Download Center, right-click returns to the page before entering the Download Center (keeping 20 entries of page navigation history), and it hides automatically when all tasks are finished

## Fixes

- **authlib-injector login export script userType error**: When exporting launch scripts, authlib-injector login accounts were uniformly written as `--userType msa`; now Microsoft accounts use `msa` while authlib-injector login and offline accounts use `legacy`, and authlib-injector's `-javaagent` and `--authServer` arguments are filled in, so exported scripts can enter verification servers directly
- **Home text after Bedrock exits**: Returning to home after a Bedrock launch no longer shows `将启动：__bedrock__`, but "Bedrock {version}"
- **Duplicate instance detection missing the default instance**: The download install page and modpack install now use `instance_list()` (including the dynamically constructed default instance), so repeated installation of the same version / same directory no longer creates duplicate instances
- **Keyboard memory adjustment not saved**: The memory slider now writes to the configuration on `valueChanged` with debounced persistence, so adjustments with the arrow keys / PageUp / PageDown are not lost after a restart
- **Cancel button ineffective after retry**: The cancel callbacks of content install and Save As tasks are now bound to each newly created download thread (`task.cancel` / `task.pause_event`), so failure → retry → cancel can now truly interrupt the new thread
- **Cache cleanup incomplete**: When cleaning cover / download caches, subdirectories are deleted recursively (`shutil.rmtree`), leaving no nested directories behind
- **Skin file read exception**: Local skin selection and skin pack application both catch `OSError` (no read permission, file exclusively locked), showing a dialog instead of throwing a traceback to the console
- **Missing page cleanup on close**: `closeEvent` now includes the download accelerator page, skin factory page and world seed page; the seed terrain thread is waited for, avoiding `QThread: Destroyed while thread is still running`
- **Log coloring misjudgement**: Error / warning keywords changed to regexes with word boundaries, so normal logs like `mirror` and `未失败` are no longer highlighted in red, and `[ERROR]` is correctly recognized
- **Miscellaneous**: The Java recommendation in the home crash dialog is changed to specify Temurin; removed the never-true `getattr(ctx, "installer")` branch; the frosted glass base color changed from reddish to a deep green-black consistent with the theme; the maximize button character changed to the more universal `▣`; deleted `page_loader.py`, which no module referenced

## Build and Verification

- Compilation: `python -m compileall mc_launcher` fully passes (exit code 0)
- Smoke: building the main window offscreen, all 21 checks pass — download floating button hidden / shown / hidden, page navigation history and right-click fallback, `game_path` switch after version folder registration, Java install method dropdown (Temurin 2 items / Microsoft ZIP only), Bedrock launch text, three log-level regex cases, recursive cache cleanup
- Network: Temurin 21 fetched `OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.msi`, Azul 21 fetched `zulu21.54.109-ca-jdk21.0.13.0.3-win_x64.msi`, Corretto 21 fetched `amazon-corretto-21.0.13.0.11-windows-x64.msi`
- Artifact: `dist/MikanCL.exe`, 220,358,041 bytes ≈ 210.1 MB (2026-11-06 13:37:18), single file with PySide6 / QtWebEngine, `translations`, `data`, `resources` and all other dependencies built in
- Launch verification: running `dist/MikanCL.exe` directly, `dist/data/logs/launcher.log` output "launcher is ready" at 13:38:14, the process kept running, and the test process was ended after verification

## Upgrade Notes

- This version fixes and adds on top of v4.9.2, with the version number updated to 4.9.3; simply overwrite the old file with the new `MikanCL.exe`, and the configurations, instances and download records under `data/` are all preserved
- The "Official installer" mode brings up the system installation wizard and may request administrator privileges; if installation is prohibited on a company computer, please use the ZIP portable version instead

---

Release date: 2026-11-05

# MikanCL v4.9.2 Release Notes

Release date: 2026-11-05

## New

- **"Download accelerator" tab**: A separate page is added to the sidebar; drop any direct download link into it and the launcher's high-thread segmented downloader downloads it; supports pasting multiple links or an entire block of text at once (automatically extracting http/https links, deduplicating, recognizing trailing punctuation), selecting the save directory separately, and up to 328 threads per task. Tasks are registered uniformly in the Download Center and can be paused / resumed / cancelled / retried after failure, with already downloaded fragments kept and resumed; files with the same name get an automatic sequence number appended, so they never overwrite or compete for the same file with an in-progress task
- **All downloads share a 328-thread budget**: `net.py` adds a global `BoundedSemaphore(328)`, acquired only at the leaf threads that actually read the network; version installation, Java download, content files, download accelerator and Bedrock chunked download all share this budget. Along the way the hard cap of 16 segments per file is lifted; segments are now split by `file size / 1 MB`, and actual concurrency is constrained by the global budget and the thread count in settings
- **Preload JVM (experimental, off by default)**: Settings → General adds a toggle and a "Java to preload" dropdown (defaults to automatically following the Java selected at launch). Once enabled, each launcher startup runs `-Xshare:auto -XX:+UseSerialGC -version` once in the background with the selected Java, warming core classes and native libraries into the system cache; everything runs on background threads and failures only write logs, without affecting the UI or the startup flow; the preload thread is waited for on window close
- **Startup speed optimization**: `scroll_page()` no longer inline-sets `setStyleSheet` for every page separately (the base color is now drawn uniformly by global rules in `theme.py`, with a new `QScrollArea#SidebarScroll` rule preserving the sidebar look); `MainWindow._apply_appearance()` adds a (background image, frosted glass) state cache and a window style sheet signature comparison, skipping `setStyleSheet` and per-ScrollArea setup entirely when the state is unchanged. Offscreen measurement shows main window construction dropping from about 5.7 seconds to about 3.5 seconds

## Fixes

- **More complete Java path detection**: In addition to the existing registry, `JAVA_HOME`, common distribution directories and launcher-managed directories, it adds `shutil.which`, all output lines of Windows `where java` / `where javaw`, and per-entry directory scanning of `PATH` (deduplicated uniformly by normalized lowercase paths, keeping only files that actually exist); as long as `java` runs on the command line, the launcher recognizes it
- **JVM preload path compatibility**: When the preload selection is a Java installation root directory, it automatically locates `bin\javaw.exe` and falls back to `bin\java.exe` when missing; matching the user-selected Java compares normalized paths, so case or slash differences do not cause a fallback to another version
- **QThread lifecycle**: Java scan and JVM preload thread objects are now released after the `finished` signal, avoiding destroying a still-running `QThread` inside the `done` slot

## Build and Verification

- Artifact: `dist/MikanCL.exe`, 221,202,421 bytes (2026-11-05 13:46:01), single file with PySide6 / QtWebEngine, `translations`, `data`, `resources` and all other dependencies built in
- Launch verification: 25 seconds after the exe started the process was still running, `data/logs/launcher.log` recorded "launcher is ready", with no crash
- Compilation verification: `python -m compileall mc_launcher` fully passes
- Smoke verification: all 27 offscreen checks pass — the 328 cap and thread count clamping, reading and writing of new config fields, the `where`/PATH detection entry, rejection of empty and non-existent preload paths, main window page count matching navigation count (19 pages in the current configuration), URL extraction / deduplication / default thread count on the download accelerator page, and the on-disk size and temporary file cleanup of a real HTTP direct-link download
- Download verification: a 3 MB local direct link submitted through the download accelerator page correctly falls back to a single stream when the server does not support Range and completes verification, with `.part` / `.merge` all cleaned up
- Segmentation verification: two 8 MB files downloaded concurrently in segments (128 threads/task) on a local Range server all pass verification; pausing preload for 1 second then resuming, and throwing `Cancelled` after cancellation both work normally; the global budget is voluntarily yielded during a pause, and the `BoundedSemaphore` count does not overflow
- Known issue: in offscreen scripts (`QT_QPA_PLATFORM=offscreen`), destroying the main window containing WebEngine before `os._exit` triggers a QtWebEngine exit crash (non-zero exit code, `0xC0000005` / `0xC0000409`), affecting only the offscreen test process; normal runs are handled by the "skip Qt/Python destruction in the exit phase" path in `main.py` and are unaffected

## Upgrade Notes

- This version adds features on top of v4.9.1, with the version number updated to 4.9.2; simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe
- Preload JVM is an experimental feature and is off by default; if startup slows down or Java paths behave abnormally, it can be disabled on the settings page

---

Release date: 2026-11-04

# MikanCL v4.9.1 Release Notes

## New

- **Java Center adds domestic mirror sources**: Adds "Tsinghua TUNA mirror (Temurin)" and "Huawei Cloud OpenJDK mirror", bringing the total number of distributions to 12; sources marked "domestic mirror" are noticeably faster for direct connections within China, with the Tsinghua mirror providing JRE / JDK and Huawei Cloud providing the full JDK
- **All large file downloads use multi-threaded segmentation**: `Http.download()` now applies to all resources — when the file is ≥ 4 MB and the server supports Range, it is automatically split into 8 segments downloaded concurrently and merged on disk, supporting pause, cancel and per-segment resumable download; when the server does not support segmentation it falls back to a single stream automatically, without affecting the existing source switching, verification and retry logic. Java installer downloads always use segmentation
- **Manually add a Java path**: Settings → General → Java runtime adds "Add manually…", where you can select `javaw.exe` / `java.exe` or fill in the installation directory directly; the path is written to the configuration and kept long-term, still recognized after restart
- **Import configuration from PCL2 / HMCL**: Settings → Game page adds "Import from PCL / HMCL…"; after selecting the other launcher's configuration directory (the launcher root directory or `.minecraft` directly) it scans versions automatically; only versions missing from this launcher are imported, and after checking them they are registered as instances pointing directly to the original game directory, so mods, worlds and resource packs need not be moved
- **Import game settings**: Reads PCL's `Setup.ini` / `PCL.ini` and HMCL's `hmclversion.cfg` / `.hmcl.json`, mapping version isolation, maximum memory, JVM arguments, window title, default Java path, etc. to this launcher's version settings; you can check whether to import global settings at the same time
- **Version settings adds a "Modpack" sidebar**: Reusing the `.mikan` package format, it can export the current version as a modpack, or pour files from `.mikan` / CurseForge / Modrinth modpacks directly into the current instance — recognizing the `overrides/` and `client-overrides/` prefixes as well as `mods` / `config` / `resourcepacks` / `shaderpacks` directories placed directly in the root (written according to the version isolation rules); the import runs on a background thread with progress display, and before overwriting files with the same name it counts them and asks for confirmation; no new instance is created; the export button on the "Version management" page moves here with a migration hint retained

## Fixes

- **Java detection sometimes present and sometimes not**: The root cause was that every refresh overwrote the list entirely with a single scan result, and the scan took only the first 60 items per directory, so a change in directory contents could hide a Java; it is now full enumeration + merging with the existing list by path, with detection results persisted to `java_known_paths` and manual paths saved to `java_manual_paths`; a refresh probes historical paths first, so "there this time, gone next time" no longer happens
- Java scan scope expanded: adds distribution directories for GraalVM, SapMachine, Dragonwell, Semeru, AdoptOpenJDK, Tencent, Alibaba, etc., plus `LOCALAPPDATA\Programs\Java`, `~/.gradle/jdks` and `~/.jdks`
- Uninstalled / invalid Java paths are removed from the list automatically on refresh, avoiding leftover invalid entries
- **Domestic mirror sources gain fallback**: The Tsinghua TUNA and Huawei Cloud mirrors both scrape HTML directory listings and are more susceptible to directory redesigns or temporary 503s than APIs; both now have the official Adoptium latest stable link as a fallback, so an unavailable source no longer directly shows "fetch failed"
- **Java scanning no longer truncated**: The cap on candidate subdirectories per installation root is raised from 400 to 2000, and on grandchild directories from 40 to 200, so pointing `JAVA_HOME` at a long-accumulated JDK directory (such as `~/.gradle/jdks`) no longer misses entries
- **Import instance idempotency now uses normalized paths**: Comparison first calls `resolve()` to collapse `..` and trailing slashes, then unifies case, so the same directory written as `E:\1.20.1-Fabric`, `E:\1.20.1-Fabric\` or with different case no longer creates duplicate instances
- **Segmented download residue cleanup**: Before a segmented download starts, the `.merge` merge file left by a previous interruption is deleted first, avoiding disk residue after a forced process kill; the `size` parameter of `_segmented_download()` explicitly accepts `None`, and the `Http.download()` documentation now states that `on_bytes` is incremental semantics and that resuming first tops up the already downloaded amount once
- Robustness cleanup for modpack import and mod conflict detection: conflict detection changed to module-level imports, with no more silently skipped `ImportError` branch; the two line-by-line fallbacks in `_read_ini()` are merged into `_parse_flat()`; the memory keywords are narrowed from `ram/memory/mem` to `ram/memory` to avoid false matches; the sidebar changed to `(key, label)` with pages mapped by key, so inserting a new page no longer misaligns; the table is no longer rebuilt repeatedly after a Java download completes

## Build and Verification

- Artifact: `dist/MikanCL.exe` (single file, 220,325,593 bytes ≈ 210.1 MB, with PySide6 / QtWebEngine, `translations`, `data`, `resources` and all other dependencies built in)
- Build time: 2026-11-04 20:57:55; the packaging log shows `Build complete`
- Launch verification: running `dist/MikanCL.exe` directly, `dist/data/logs/launcher.log` output "launcher is ready" at 20:58:41, the process kept running, and the test process was ended after verification
- Compilation verification: `python -m compileall mc_launcher` fully passes, and the offscreen smoke test reports no errors
- Functional verification: scanning the PCL test directory `E:\1.20.1-Fabric 0.19.5-OptiFine_I6` identified 1.16.5 (PCL / version isolation / description); after import the instance and version settings were written correctly, and the configuration was restored after testing
- Download verification: a 49 MB JRE from the Tsinghua TUNA mirror downloaded with 8 concurrent segments, finishing in 5.6 seconds, with all segmented temporary files cleaned up
- UI smoke: offscreen creation of the Java Center (12 distributions), settings page, version settings page (7 sidebar tabs) and the import dialog all build normally
- Review fix verification: `tuna` / `huawei` are present in `_FALLBACK_FETCHERS`; the same directory written with a trailing slash, different case or containing `..` yields an identical instance identifier; `_parse_flat()` can parse PCL `Ram:8192` and HMCL `maxMemory=4096`, and keys such as `remember` are no longer misjudged as memory; a synthetic `.mikan` (containing `overrides/`, `client-overrides/` and a root `mods/`) is recognized as 3 entries and all written to disk with the correct overwrite count, and `ImportPackWorker` progress goes 0→1 and ends normally; the 7 sidebar items match the page key mapping, and `_select_nav()` locates correctly; `_segmented_download(size=None)` no longer throws `TypeError`

## Upgrade Notes

- This version is a revision of v4.9.0, with the version number updated to 4.9.1; simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe
- PCL / HMCL instances already registered through module import need no re-import; after upgrading, the same directory is no longer judged a new instance

---

# MikanCL v4.8.2 Release Notes


Release date: 2026-11-03

## Fixes

- **Skin pack fails to load**: Reverted to the writing and loading approach of the old skin packs that worked — the resource pack writes both sets of paths, `textures/entity/steve.png`, `alex.png` and `textures/entity/player/wide/steve.png`, `slim/alex.png`, instead of writing only one according to the version; the `supported_formats` upper bound in `pack.mcmeta` is relaxed from "current pack_format" back to 1–99, so format differences between adjacent versions are no longer judged incompatible; 1.21.9+ / 26.x still uses `min_format` / `max_format`, keeping multi-version adaptation unchanged
- **Shared pack cannot be loaded directly**: The exported `.zip` no longer nests the resource pack inside a `resourcepack/` subdirectory, but places `pack.mcmeta` / `pack.txt` and textures directly in the pack root, so the file itself can be put into `resourcepacks` (or `texturepacks` for 1.5.2 and earlier) to load; launcher import still reads the root `skin.png` and regenerates an adapted pack for the locally selected version
- **Root cause of skin packs not taking effect**: The old code wrote only a single texture path per arm model (measured: the old `MikanCL-luohaocheng-皮肤包.zip` contained only `assets/minecraft/textures/entity/alex.png`, `pack_format=1`, `supported_formats` 1–1), and when the player actually used the Steve (wide) model that path was not loaded, so the resource pack showed "adapted" while the in-game skin was still the default; old packs wrote four paths including both `steve.png` and `alex.png`, so even when shown as red incompatible the skin still displayed correctly after being force-enabled. The old pack writing approach is now restored, writing the four paths at once and independently of the arm model
- **Reinstall once after upgrading**: Old `MikanCL-*.zip` files already written into game directories by the old code are not rewritten automatically; please use 4.8.2's "One-click add and overwrite old skin packs" or click install once again to generate a new pack containing the four texture paths

## New

- **"Dependency completion" tab**: A separate page is added to the sidebar, listing all third-party components that cannot be bundled due to license, size or official distribution channel restrictions — Terracotta multiplayer (Terracotta 0.4.2), authlib-injector, Java runtime, mod loaders (Forge / Fabric / NeoForge / Quilt) and Forbric; organized by category showing install status, version, license and path, with missing modules that can be downloaded directly showing "Download", installed ones showing "Locate", and those requiring an official installer showing "Go to" the corresponding page
- **Unified download entry for third-party components**: Clicking "Download" pulls from each component's official release address, registers the task in the Download Center, and supports pause / cancel / retry after failure just like normal downloads
- **Third-party component disclaimer**: The top of the dependencies page permanently shows a note — these components are provided only as a convenient download entry and are maintained independently by their respective authors; any problems arising during download or use are borne by the user, and the MikanCL author accepts no responsibility
- **Game missing dependency check**: After selecting any installed version, check with one click the required Java, client jar, `libraries` dependencies, `assets` resource index and objects, log4j logging configuration and version file; the results table lists "Missing / Complete" item by item along with specific explanations
- **Prompted silent completion**: When the check finds missing items, a dialog asks "Complete automatically now?"; after confirmation it runs silently in the background — missing Java downloads Adoptium JRE, missing files go through version completion that fills only the gaps, all tasks appear in the Download Center, and using the launcher continues unaffected until completion
- **User agreement upgraded to v1.4**: Adds article 11 "Third-party components", clarifying that third-party components have no affiliation, authorization, sponsorship or guarantee relationship with MikanCL, that the entry is provided purely for convenience, and that related risks are borne by the user; synced across 5 languages (Chinese / English / Russian / French / Japanese)
- **"Skin pack" tab**: A separate page is added to the sidebar, generating a shareable skin pack (`.zip`, containing `pack.json`, `skin.png`, version-adapted resource packs and instructions) by "target player + arm model + game version"; it can also be installed locally; supports importing others' skin packs or a single PNG
- **Per-player skins**: Instead of globally replacing the default skin texture, it writes `CustomSkinLoader/LocalSkin/skins/<player name>.png` and merges the `loadlist` in `CustomSkinLoader.json` (the `{USERNAME}` placeholder), so only the specified player shows this skin on servers while other players are unaffected
- **All-version skin pack adaptation**: 1.0–1.5.2 generates a `texturepacks` texture pack (`pack.txt` + `textures/entity/*.png`); 1.6.1–1.21.8 uses `pack.mcmeta`'s `pack_format` (automatically 1 / 2 / 3 … 64 by version) together with `supported_formats` 1–99; 1.21.9+ and 26.x (including the 26.4 beta) switch to `min_format` / `max_format`; both the old and new player texture paths (`textures/entity/steve|alex.png` and `entity/player/wide|slim`) are written at the same time, so any version hits
- **Arm model prompt**: Before importing a local skin, applying a skin factory work, importing a skin pack or exporting a skin pack, it asks whether to use Steve (classic) or Alex (slim); the choice is saved to the account's `skin_model` and reused for later automatic packing and for importing when downloading a new version
- **Automatic packing with the version**: When downloading and installing a new version, importing a modpack / direct-install pack or restoring an instance completes, a skin pack is generated automatically in that version's format and written to `CustomSkinLoader/LocalSkin`, with no need to launch again
- **One-click add and overwrite old skin packs**: The skin pack page adds a button that first cleans all `MikanCL-*.zip` files in the main directory and version isolation directories (including the old `MikanCL-离线皮肤.zip`) and the `file/MikanCL-*` enabled entries in `options.txt`, then writes the current skin; regular installation of a new pack also cleans automatically, preventing leftover old packs from making users think the new skin has taken effect
- **Smart JVM arguments**: Settings → General adds a toggle (on by default) that appends arguments automatically according to Java major version, game version and heap size: 1.21 and earlier use Aikar-style G1GC (young generation share, Region, IHOP, pause target, etc.), `AlwaysPreTouch` is enabled only when the heap is ≥ 4 GB, and 16 MB regions are used at ≥ 12 GB; 26.x (officially requiring Java 25) switches to generational ZGC (`-XX:+UseZGC`); it skips automatically when a GC (including the negative form `-XX:-UseG1GC`) or a same-named argument is already specified in the extra JVM arguments; Java 7 and earlier only gets `MaxPermSize=256M`; it warns of paging risk when allocated memory exceeds 60% of physical memory
- **Version-compatible launch arguments**: 1.12.2 and earlier automatically get `-Xss1M` (MC-129374) and `-Djava.util.Arrays.useLegacyMergeSort=true` (MC-61156); old Forge / modpacks with modified jars get `-Dfml.ignoreInvalidMinecraftCertificates=true` and `-Dfml.ignorePatchDiscrepancies=true`; old versions assigned to Java 9+ automatically get `--add-opens` module opening arguments; Java 24+ gets `--enable-native-access=ALL-UNNAMED`; macOS 1.13+ gets `-XstartOnFirstThread`. These arguments are not affected by the "Smart JVM" toggle and always apply
- **Version number recognition fix**: `infer_java_major` returns Java 25 for 26.x / 26w.. year-style version numbers (previously wrongly 21), and returns Java 8 for ancient versions (`a1.2.6` / `b1.7.3` / `c0.30` / `inf-` / `rd-` / `1.rv` / `2.0`) and pre-1.14 snapshots; `3d shareware v1.34` is also classified as Java 8
- **Up to 5 versions installed concurrently**: The download install page lifts the "only one version can be installed at a time" restriction, allowing up to 5 versions to be installed at once, each with independent progress, pause and cancel; the 6th version waits for a free slot

## Fixes and Improvements

- **Fixed modpack installation always crashing**: `ContentInstallWorker._emit()` accepted only progress and description but was passed `stage / files_done / files_total`, throwing `TypeError` so that all modpack installations failed at the content download stage; the signature is now extended and the stage merged into the description text
- If the user changes the selected loader while the download page is asynchronously estimating disk usage, the selection is no longer rolled back when the estimate completes; the installation is simply abandoned
- Offline UUIDs are provided uniformly by `auth.offline_uuid()`, and `launcher.py` no longer maintains a second implementation
- The game exit listener thread now receives the bus object, so closing the launcher no longer references possibly destroyed pages; the Bedrock delayed validation flag is also cleared on close
- When switching languages, if the target `.qm` translation file is missing, it prompts "Translation file missing, reverted to Chinese" and restores the previous choice, no longer saving a language that is still Chinese after a restart
- Settings → Feature toggles adds a "Dependency completion" tab switch; when turned off, no page is created and no background task starts; takes effect after restart
- Dependency completion tasks reuse the Download Center queue and retry mechanism, and the previous cancellation flag is cleared automatically before a retry, avoiding "retrying after a cancel immediately cancels again"
- Dependency scanning defensively handles unsupported CPU architectures, missing resource indexes and corrupted version JSON, so a failure on a single page does not affect other launcher features
- After completion, the Java list and version status refresh automatically, with a prompt that you can re-check or launch directly
- When installing multiple versions concurrently, shared dependency libraries / resource files may be requested by several threads at the same time: `Http.download()` now locks by target path and re-checks whether the file is already complete after acquiring the lock, avoiding `.part` write conflicts and duplicate downloads
- The Download Center's default number of concurrent tasks is adjusted from 2 to 5, consistent with the page's concurrent installation limit, with the remaining tasks queued automatically

## Build and Verification

- Artifact: `dist/MikanCL.exe` (single file, 221,115,875 bytes ≈ 210.9 MB, with PySide6 / QtWebEngine, `translations`, `data`, `resources` and all other dependencies built in)
- Build time: 2026-11-03 21:59:47; the packaging log shows `Build complete`
- Launch verification: running `dist/MikanCL.exe` directly, `data/logs/launcher.log` output "launcher is ready" at 22:01:24, the window title displayed normally, and the test process was ended after verification
- Offscreen smoke test passed: the sidebar shows "Dependency completion", the page is created, the module table has 5 rows (Terracotta / authlib-injector / Java runtime / mod loaders / Forbric), the settings page feature toggles include `deps`, and the "Go to Java Center" button correctly emits a navigation signal
- Dependency scan test passed: a synthetic version directory correctly identifies 5 kinds of missing items — Java, client Jar, dependency libraries, resource index and logging configuration; a non-existent version returns `kind="version"`
- Concurrency and skin test passed: `DownloadManager.max_concurrent == 5`, 5 tasks run in parallel on the download page with the 6th blocked by the limit, and the install button is disabled at the limit; `import_offline_skin()` correctly writes `CustomSkinLoader/LocalSkin/skins/<player name>.png`, merges the `loadlist` in `CustomSkinLoader.json` and generates a resource pack for the corresponding version; a missing `resourcepacks` directory in the game directory is created automatically first
- Skin pack version adaptation verification passed (old pack approach): 1.5.2 → `pack.txt` + `textures/entity/steve.png`, `alex.png`; 1.8.9 → `pack_format=1` + `supported_formats` 1–99; 1.12.2 → `pack_format=3`; 1.20.1 → `pack_format=15`; 1.21.8 → `pack_format=64`; 1.6.1+ all contain both the `textures/entity/steve|alex.png` and `entity/player/wide|slim` paths; 1.21.9 → `min_format=[69,0]` / `max_format=[999,0]`; 26.4-snapshot → `min_format=[97,0]` / `max_format=[999,0]`; the exported `.zip` root directly contains `pack.mcmeta` / `pack.txt` and textures and can be loaded by the game directly; when installing repeatedly for different players the `LocalSkin` entries are not duplicated and the user's existing `MojangAPI` and other skin sources are preserved
- Old skin pack overwrite verification passed: `purge_old_packs()` can delete `MikanCL-*.zip` under `resourcepacks` / `texturepacks` (keeping other resource packs) and remove the enabled entries from `options.txt` at the same time; before installing a new pack it cleans automatically, and in the end only one `MikanCL-*` fallback pack remains
- Smart JVM argument verification passed: Java 8 / 17 / 21 generate 19–20 arguments respectively; a 2 GB heap has no `AlwaysPreTouch`, an 8 GB heap has it; a 16 GB heap uses `G1HeapRegionSize=16M`; when the user specifies `-XX:+UseZGC` or `-XX:-UseG1GC` the G1 presets are skipped; `-XX:MaxGCPauseMillis=300` is not overridden; Java 7 returns `-XX:MaxPermSize=256M`; an unknown Java version returns an empty list
- Version-compatible argument verification passed: 1.7.10 → `-Xss1M` + legacy sorting; 1.7.10-forge → the two fml arguments appended; 1.12.2 + Java 17 → 7 `--add-opens` entries appended; 1.21.8 + Java 21 → no compatible arguments; 26.1 / 26w01a + Java 25 → `-XX:+UseZGC` with no G1GC; all versions on Java 24+ append `--enable-native-access=ALL-UNNAMED`
- Full command assembly verification passed: `build_launch_plan()` produces `-Xmx/-Xms` → tuning arguments → version-compatible arguments → encoding / branding → `-Djava.library.path` / `-cp` → main class; the order and content are correct for all three combinations 1.12.2, 1.21.8 and 26.1
- Ancient / special version recognition verification passed: `b1.7.3`, `a1.2.6`, `c0.30_01c`, `inf-20100618`, `rd-132211`, `1.rv-pre1`, `2.0`, `12w01a`, `17w43a` are all judged legacy; `20w14infinite` / `25w14craftmine` / `3d shareware v1.34` are classified as Java 8 with no legacy arguments appended; `26w01a` is judged Java 25

## Docs

- See [README.md](README.md) for the complete features, technical implementation and interface documentation
- See the v4.9.1 section at the top of this file for the change summary of this version

## Upgrade Notes

- Simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe
- Upgrading from v4.7.0 requires no re-confirmation of "User Agreement v1.4" (the agreement version is unchanged)
- Third-party components are downloaded on demand, and not downloading them does not affect the launcher's other features; please confirm the source, version and open-source license yourself before use

---

# MikanCL v4.6.2 Release Notes

Release date: 2026-10-31

## New

- **Skin 3D 360° free view**: The preview model supports mouse-drag rotation (horizontal yaw + vertical pitch), viewable from any angle; scroll to zoom, right-drag to pan; the reset button returns to the default view in one click
- **Brush / mouse dual-mode toggle**: The skin factory 3D preview adds mutually exclusive "Brush / Mouse" buttons — in brush mode the left button paints and the right button erases; in mouse mode dragging rotates, fully separating painting from viewing without relying on Shift
- **Zoom control**: The 3D preview adds "＋/－" zoom buttons and a percentage display, supporting 20%–800%
- **Actual skin fully viewable on the account page**: The skin preview on the account management page also supports 360° drag rotation, scroll zoom and panning, with rotate left / rotate right / reset / zoom buttons

## Fixes and Improvements

- Fixed the inability to adjust the view up and down when painting on the 3D skin (a pitch axis was added)
- Both painting 3D and actual skin 3D become fully viewable, with unified interaction logic
- The hint text is updated to describe the brush / mouse dual modes, synced across 5 languages

## Upgrade Notes

- Simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe

---

# MikanCL v4.6.1 Release Notes

Release date: 2026-10-31

## New

- **Classic / new noise toggle**: The seed terrain page adds a "Noise version" dropdown — Classic (1.7–1.17, `ImprovedNoise` 256 permutation table + 16-direction gradient table, 8 octaves stacked with persistence 0.5 / lacunarity 2) and New (1.18+, `Xoroshiro128++` random source + continentalness / erosion / weirdness climate noise); the parameters of both modes are the vanilla fixed values, with no additional adjustable options provided
- **No upper limit on seed terrain size**: The size input cap is removed (32 ~ 2147483647), default 256×256 (survival range); the larger the size, the longer generation takes; the render side downsamples automatically by size to avoid a vertex explosion at large sizes

## Fixes and Improvements

- **Skin 3D preview crash fix**: `_draw_texel` originally unpacked a 9-tuple hit record as 7 items, throwing `ValueError: too many values to unpack (expected 7, got 9)`; it now unpacks from `rec[2:]`
- **Fixed the flooding of `QBackingStore::endPaint() called with active painter`**: `paintEvent` is split into a wrapper + `_paint`, using `try/finally` to guarantee the painter is ended even on exception
- The terrain heightmap now uses a two-pass normalization against the current frame's min/max, so both Classic / New modes cover the full 0–255 height gradient, no longer producing distorted images that are entirely ocean or plains
- The seed page removes custom parameters such as the "relief" slider, generating strictly with vanilla fixed parameters
- Article 9 of the user agreement is updated in sync to the dual-mode wording (5 languages)

## Upgrade Notes

- Simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe

---

# MikanCL v4.6.0 Release Notes

Release date: 2026-10-31

## New

- **Terrain changed to Minecraft block rendering**: The 3D terrain of the world seed no longer uses a smooth triangle mesh but voxel column rendering — one block per cell, a flat top plus stepped sides exposed only toward lower neighbors, sea level flattened automatically, and sides darkened by orientation (0.60 in the x direction / 0.78 in the z direction), visually consistent with in-game block terrain
- **Terrain interaction button bar**: Below the 3D view, buttons "View ◀▶▲▼ / Zoom ＋－ / Pan ←→↑↓ / Reset view / Auto rotate" are added, allowing full view control without a mouse; drag rotation, scroll zoom and right-drag pan are retained, and double-click reset is added
- **Multi-layer skin painting**: The skin factory supports up to 8 layers, and a multi-layer editing area is added below the canvas — checklist toggles visibility, clicking switches the active layer, plus new / delete / move up / move down; the base layer cannot be deleted; exporting PNG, saving to the skin library and applying to the account automatically merge all visible layers
- **New brush tools**: Adds line, rectangle, ellipse (preview while dragging, commit on release) and airbrush (random dots according to brush size), giving ten tools in one toolbar row; when painting in 3D, shape tools degrade automatically to a single-pixel brush
- **Skin 3D view buttons**: The 3D preview view row adds "Rotate left / Rotate right / Reset view" buttons (15° each), no longer relying only on the slider and dragging
- All copy for the new features is wired into the 5-language (Chinese / English / Russian / French / Japanese) translation files

## Fixes and Improvements

- **Skin painting crash hardening**: In-progress strokes and shape previews are aborted automatically before switching tools / layers / undo redo / clear / loading an image; all `QPainter` calls are protected with try/finally; stroke start / end are idempotent; coordinates are uniformly clamped to bounds; a 30-round mixed-operation stress test passes
- Undo / redo changed to full layer snapshots, so the multi-layer structure (layer count, order, visibility, active layer) is fully restored along with history
- The 3D hover hint adds a UV out-of-bounds guard, avoiding color-picking crashes at extreme angles

## Upgrade Notes

- Simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe

---

# MikanCL v4.5.0 Release Notes

Release date: 2026-10-31

## New

- **Skin 3D painting**: The right side of the 3D preview adds a "Layer" dropdown (base layer / second layer), a "View" slider and an "Auto rotate" toggle; after selecting head / body / left and right arm / left and right leg, you can paint directly on the 3D model, with the left button drawing with the current tool, the right button erasing, Shift + drag rotating the model, and the status bar showing the hit part, texture coordinates and color value in real time
- **Second layer (overlay) rendering**: The second-layer UVs of the hat / jacket / sleeves / pant legs participate in 3D rendering together with the base layer, overlaid with a 0.6 pixel outward offset and kept semi-transparent; transparent pixels are not covered by the second layer
- 3D painting reuses all canvas tools (brush / eraser / fill / eyedropper / lighten / darken, brush size, mirror symmetry), pushing only one undo snapshot per stroke and staying in two-way real-time sync with the 2D canvas
- Both layer panels support mirroring: horizontal mirroring within the same part according to the rectangle of the base layer or second layer where the pixel actually resides
- **Terrain noise consistent with vanilla**: `TerrainGen.java` switches to the same Perlin gradient noise as Minecraft — `ImprovedNoise` (`Random(seed)` with three `nextDouble()*256` offsets, a 256 permutation table, a 16-direction gradient table, tricubic interpolation) + multi-octave stacking (persistence 0.5 / lacunarity 2); it still contains no biomes, terrain splines or density functions, so it is an unofficial terrain approximation
- The terrain source version number is upgraded (`SOURCE_VERSION=2`), and the old `TerrainGen.class` is invalidated automatically and recompiled
- User agreement upgraded to **v1.3**: article 8 supplements 3D painting and dual-layer editing, and article 9 changed to accurately describe "the noise algorithm and parameters are consistent with Minecraft, without biomes and terrain splines", synced across 5 languages

## Fixes and Improvements

- Fixed the issue where pixel alpha remained 255 after right-click erasing on the 2D canvas: erasing now uses `CompositionMode_Clear`, and 3D right-click erasing works the same way
- Isometric rendering of the 3D preview now covers all six faces (including the back and bottom), the painter's algorithm sorts by depth, and the second layer is always drawn after the base layer at the same depth
- 3D picking resolves the hit list in reverse order, so all six parts can still be hit accurately after rotating to any angle
- The seed page description is changed to "the same Perlin noise algorithm and parameters as Minecraft", and notes that biomes and terrain splines are not included

## Upgrade Notes

- Simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe
- The first launch of 4.5.0 asks you to confirm the upgraded "User Agreement v1.3"

---

# MikanCL v4.4.1 Release Notes

Release date: 2026-10-30

## New

- **Skin factory**: A built-in 64×64 pixel skin editor supporting six tools (brush / eraser / fill / eyedropper / lighten / darken), brush size, horizontal mirror symmetry, undo / redo (up to 40 steps, Ctrl+Z / Ctrl+Y), 4×~8× zoom and a grid toggle, highlighting the base and second-layer UV regions by part such as head, body and limbs, with real-time cursor coordinates and color value hints; live 3D preview for Steve / Alex models; a new local multi-skin library (`data/skins`) supporting save / load / apply / delete of multiple skins, exporting PNG or applying to the current account in one click
- **World seed and terrain preview**: Enter a seed (a number or any text), and the launcher calls the local Java runtime to execute the embedded `TerrainGen.java` (Perlin fBm noise, not Minecraft's official implementation, preferring the `javac` compiled cache and falling back to Java 11+ single-file source launch when no compiler is present) to generate the heightmap on a background thread, then renders the 3D terrain near the spawn point inline via `QWebEngineView` WebGL (drag to rotate, scroll to zoom, right-drag to pan), supporting size and relief adjustment and heightmap PNG export; terrain computation is no longer handled by Python, avoiding main process crashes
- **Page switch animation**: When switching tabs, the new page fades in and out (about 180ms, OutCubic easing), which can be disabled in "Settings → Appearance" to reduce GPU usage
- **Frosted glass background**: On Windows, an acrylic blur background is enabled through DWM `SetWindowCompositionAttribute`, without starting extra processes or using the network; it can be toggled in "Settings → Appearance", and unsupported systems fall back automatically to a semi-transparent dark background
- User agreement upgraded to **v1.2**, adding three truthful clauses: skin factory and offline skins, world seed and terrain preview, and UI effects and frosted glass (synced across 5 languages)

## Fixes and Improvements

- **Bedrock download changed to browser download**: No longer relying on offline-cached direct link sniffing; version entries become a one-click opening of the MCAPPX / Microsoft Store page in the built-in browser (Edge WebView2 core), where clicking the download button on the page lets Edge download to the local machine; the launcher monitors the download directory, and newly downloaded `.appx / .msix / .appxbundle / .msixbundle` files are archived automatically to `data/bedrock/`, after which you can "Install from local" directly
- Settings → Appearance adds a "UI effects" card for centralized management of the page switch animation and frosted glass toggles
- Settings → Feature toggles adds two tab switches, "Skin factory" and "World seed" (effective after restart)
- Main window navigation now looks up page numbers by page key, so newly added pages no longer need a synchronized numeric mapping
- The skin factory and seed terrain pages actively release background threads and web rendering resources on close, avoiding leftover processes on exit

## Upgrade Notes

- Simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe
- The first launch of 4.4.1 asks you to confirm the upgraded "User Agreement v1.2"

---

# MikanCL v4.4.0 Release Notes

Release date: 2026-10-30

## New

- **First-launch user agreement**: When the current agreement version has not been accepted, a confirmation dialog pops up before startup; all 7 clauses (unofficial statement / accounts and login / content and downloads / game data and operational risks / network requests and privacy / disclaimer and limitation of liability / agreement changes and termination) are shown side by side as tabs, and "Agree and continue" is not clickable until "I have read and agree" is checked; choosing "Decline and exit" closes the program directly without entering the main UI
- The agreement has Chinese, English, Russian, French and Japanese built in, switching automatically with the UI language
- After agreeing, the agreement version and consent time are written to `data/config.json`, so it no longer prompts afterwards; when the agreement version is upgraded it asks for confirmation again
- Settings → About adds a "User agreement" card: you can re-read the full agreement at any time and toggle off "Show user agreement confirmation on startup"

## Fixes and Improvements

- Bedrock download: leftover bytes from segmented resumes are truncated automatically before merging, no longer falsely reporting "file length mismatch"; store manifest queries can be cancelled, so closing the program is no longer held up by retries; the Download Center "Remaining files" column now shows completed segments / total segments
- Bedrock installed detection: changed to major version prefix matching, so MCAPPX directory entries (such as 1.8.1 versus the system's 1.8.102.0) can be correctly marked "installed"
- Bedrock installation: the grace period after the PowerShell success marker keeps refreshing with new output, so long logs are no longer killed by mistake
- Forbric: when the GitHub release API fails or assets are missing, it falls back automatically to the latest release direct link, no longer depending on a single third-party repository API
- Built-in browser (WebView2): COM interface queries simplified, IID constants unified, reducing pointer compatibility risks
- Sidebar navigation: changed to lookup by page key, so newly added pages no longer need a synchronized hand-written page number mapping, eliminating jump misalignment

## Upgrade Notes

- Simply download the new `MikanCL.exe` and overwrite the old file, and configurations and data remain under `data/` in the same directory as the exe
- The first launch of 4.4.0 asks you to read and agree to the "User Agreement"; if you do not agree, you cannot enter the main UI
