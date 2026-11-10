# MikanCL v5.1.0 Release Notes

[中文](RELEASE.md) · [English](RELEASE.en.md) · [Русский](RELEASE.ru.md) · [Français](RELEASE.fr.md) · [日本語](RELEASE.ja.md)

Release date: 2026-11-08

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
