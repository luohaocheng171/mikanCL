"""用户协议与免责声明：多语言文案 + 同意状态判定。

协议正文按语言分块存放（不经过 .qm），保证 5 种界面语言都能完整阅读；
同意状态记录在 config.json，协议版本号变化后会再次要求确认。
"""

from __future__ import annotations

from datetime import datetime

AGREEMENT_VERSION = "1.8"

# 每种语言：标题、确认文案、按钮文案、条款标签页（标签名 + 正文）
_TEXTS: dict[str, dict] = {
    "zh_CN": {
        "title": "MikanCL 用户协议与免责声明",
        "intro": "请完整阅读以下全部条款。点击「同意并继续」表示您已阅读、理解并接受全部内容；"
        "若不同意，请选择「不同意，退出」，本软件将立即关闭。",
        "checkbox": "我已阅读并同意以上全部条款",
        "accept": "同意并继续",
        "decline": "不同意，退出",
        "close": "关闭",
        "view": "查看用户协议",
        "prompt_switch": "启动时弹出用户协议确认",
        "version": "协议版本：{0}",
        "agreed_at": "同意时间：{0}",
        "not_accepted": "尚未同意",
        "sections": [
            (
                "一、非官方声明",
                "MikanCL 是第三方开源启动器，与 Mojang Studios、Microsoft、Bilibili、Modrinth、"
                "CurseForge、Minecraft Wiki 等均无隶属、授权或赞助关系。\n"
                "「Minecraft」「我的世界」及相关商标、图像、音效归其权利人所有。\n"
                "本软件不提供、不分发破解版游戏，也不包含绕过正版验证的功能；请通过官方渠道购买正版游戏。\n"
                "首次启动可选择「经典模式（Qt）」或「美化模式（pywebview + WebView2）」，"
                "二者共用同一套启动、下载、账号与联机内核，功能完全对齐；"
                "仅界面渲染方式不同，不改变任何数据、联网与启动行为。"
                "两套界面可在「设置 → 外观」中随时双向切换，切换后重启启动器生效，"
                "不会丢失下载进度、设置或账号数据。",
            ),
            (
                "二、账号与登录",
                "微软正版登录使用官方 OAuth 设备码流程；登录令牌仅保存在本机 data/accounts.json，"
                "不会上传到任何第三方服务器。\n"
                "外置登录（authlib-injector）会把凭据提交给您填写的皮肤站，其数据处理适用该站点的规则。\n"
                "离线登录（离线账号与离线皮肤）仅为官方后门（内部通道）保留，不具备正版验证能力；"
                "如有问题，可在「设置 → 功能开关」中手动关闭。\n"
                "账号共享、泄露、被盗或被平台封禁造成的损失由您自行承担。",
            ),
            (
                "三、内容与下载",
                "「内容中心」中的 Mod、整合包、资源包、光影包均来自 Modrinth / CurseForge 等第三方平台，"
                "其授权与使用条款以来源页面为准，请自行确认并遵守对应许可（含再分发限制）。\n"
                "第三方内容可能包含不稳定代码、恶意行为、与其他 Mod 冲突或与游戏版本不兼容，"
                "安装前请备份存档并自行判断风险。\n"
                "「检查更新」会按照文件指纹（SHA1 / Murmur2）向 Modrinth 与 CurseForge 查询项目信息，"
                "仅用于识别本地 Mod 对应的项目与最新兼容版本，不会上传 Mod 文件本身。\n"
                "本软件仅提供下载与安装的技术通道，不对第三方内容的合法性、安全性作出任何担保。",
            ),
            (
                "四、游戏数据、备份与运行风险",
                "安装版本、加载器、整合包会写入并修改 Minecraft 目录（含 libraries、assets、mods、config、"
                "saves 等），误操作可能损坏存档或导致游戏无法启动。\n"
                "启动前请在「版本设置」中确认 Java、内存与隔离策略；重要存档请自行定期备份。\n"
                "本软件提供存档列表、Zip 备份 / 恢复与可选的启动前自动备份，但备份目录同样位于本机磁盘，"
                "无法防御磁盘损坏、误删或恶意软件，且不保证每次备份都成功；重要存档请另存到其他设备。\n"
                "关闭启动器时若仍有下载 / 安装任务，会先询问是否中断；确认关闭将立即终止进程，"
                "可能留下未完成的临时文件，下次启动时会重新校验并按需补全。\n"
                "本软件不承诺任何数据可恢复性，也不对存档丢失、配置损坏承担责任。",
            ),
            (
                "五、网络请求与隐私",
                "为完成安装、登录与内容检索，本软件会向 Mojang、BMCLAPI、Modrinth、CurseForge、"
                "GitHub、rg-adguard 及您配置的镜像站发送网络请求，请求中可能包含版本号、界面语言与账号标识。\n"
                "本软件不收集、不上传您的存档、日志与本地文件，不向任何第三方出售或共享您的个人信息。\n"
                "「截图图库」与「崩溃报告」仅读取本机 screenshots 与 data/logs/crashes 目录，"
                "预览、打包与删除操作均只在本机执行，不会上传任何图片或日志。\n"
                "内置浏览器访问的第三方站点（含 Bilibili）适用其各自的隐私政策与服务条款。",
            ),
            (
                "六、免责与责任限制",
                "本软件按「现状」提供，不附带任何明示或暗示的担保，包括但不限于适销性、"
                "特定用途适用性与不侵权担保。\n"
                "在适用法律允许的最大范围内，开发者不对因使用或无法使用本软件而产生的任何直接、间接、"
                "附带、特殊或后果性损失承担责任，包括但不限于存档丢失、账号封禁、设备损坏与收益损失。\n"
                "若您所在地区的法律不允许上述部分限制，则该部分限制在您所在地区不适用。",
            ),
            (
                "七、协议变更与终止",
                "协议内容更新后，启动时会再次提示确认；不同意新条款可停止使用并删除本软件。\n"
                "您可在「设置 → 关于」中随时重新查看本协议，或关闭启动前的确认提示"
                "（关闭后仍以您上一次同意的内容为准）。\n"
                "本协议适用中华人民共和国法律（不含冲突法规则）。",
            ),
            (
                "八、皮肤工厂与离线皮肤",
                "本软件内置「皮肤工厂」，可在本地像素级编辑 64×64 皮肤（含第二层遮罩），"
                "支持画笔、橡皮、填充、取色、镜像与多部件分区，也可在 3D 模型上选中部位后"
                "直接作画（底层与第二层均可编辑），成品保存为 PNG 并可直接应用到"
                "离线或外置账号。皮肤文件仅保存在本机 data/skins，不会上传至任何服务器。\n"
                "Minecraft 及相关美术素材的版权归 Mojang Studios / Microsoft 及原作者所有，"
                "请勿用于商业用途或侵犯他人权益。",
            ),
            (
                "九、世界种子与地形预览",
                "「种子 / 地形」页输入世界种子后，启动器调用本机 Java 运行时执行内置的"
                "高度图程序（TerrainGen），提供经典（1.7–1.17，ImprovedNoise 置换表与 16 向"
                "梯度表，多 octave 叠加 persistence 0.5、lacunarity 2）与新版（1.18+，"
                "Xoroshiro128++ 随机源与气候噪声）两种噪声模式，参数均为原版固定值，"
                "不提供额外可调项；但不包含生物群系、地形样条与密度函数，仍属非官方地形示意；"
                "生成结果会渲染为出生点附近的 3D 地形。\n"
                "该预览仅供选择种子时参考，不保证与游戏内实际地形完全一致；"
                "实际地形与生物群系以 Minecraft 本体的生成结果为准。",
            ),
            (
                "十、界面效果与毛玻璃",
                "页面切换淡入淡出等界面动画与毛玻璃背景均为可选增强，可在「设置」中关闭"
                "以降低 GPU 与内存占用。\n"
                "美化模式下的半透明毛玻璃由 Edge WebView2（Chromium）渲染，主题色以淡色叠加在"
                "毛玻璃之上；经典模式下的毛玻璃依赖 Windows 桌面窗口管理器（DWM）合成。"
                "两种实现均不额外启动进程、不联网；在不支持的系统或关闭该选项时，"
                "会自动回退为不透明/半透明深色背景。\n"
                "字体渲染按 Windows ClearType 亚像素方案优化，关闭毛玻璃或界面动画不影响任何功能。",
            ),
            (
                "十一、第三方模块",
                "「依赖补全」页会列出陶瓦联机（Terracotta）、authlib-injector 等第三方模块，"
                "并由您点击后从各自官方发布地址下载。这些模块由各自作者独立开发与维护，"
                "MikanCL 与其作者无隶属、授权、赞助或担保关系，也不对其代码、更新与可用性负责。\n"
                "提供下载入口仅为方便用户；下载、安装或使用过程中出现的任何问题（包括但不限于"
                "游戏崩溃、存档或文件损坏、联机中断、账号或安全风险、设备损害等）由您自行承担，"
                "MikanCL 作者概不负责。\n"
                "第三方模块适用其自身的开源许可（如 AGPL-3.0），请自行确认来源、版本与许可后再使用；"
                "如不需要，可忽略该页面而完全不影响启动器其余功能。",
            ),
            (
                "十二、基岩版与商店安装包",
                "「基岩版」页展示 MCAPPX 提供的离线安装包索引，本软件只做展示与版本匹配，"
                "不随软件分发任何游戏安装包。\n"
                "安装通过 Windows 的 Add-AppxPackage 接口部署由微软签名的 .appx / .msix，"
                "需要系统允许旁加载；部署耗时取决于磁盘性能与包体积，进度长时间停留在部署阶段属正常现象。\n"
                "部分历史版本需通过内置浏览器自行下载，下载站点的可用性与内容不由本软件控制；"
                "安装、更新与卸载遵循 Microsoft Store 与 Windows 的规则，"
                "本软件不对安装失败、系统策略拦截或卸载后的残留负责。",
            ),
            (
                "十三、扩展、主题与界面定制",
                "「扩展」支持导入 .zip / .mikan-ext，启用后显示在侧边栏，并运行在沙箱 iframe 中，"
                "仅能通过 postMessage 与后端通信。扩展由第三方作者提供，可能包含任意前端代码，"
                "请在确认来源可信后再启用；本软件不对扩展造成的数据或安全问题负责。\n"
                "主题、皮肤与动态壁纸均可自定义：主题与皮肤以 JSON 保存在本机 data/themes，"
                "壁纸支持 MP4 / WebM / GIF / WebP；自定义资源可能包含大文件或特殊编码，"
                "可能导致界面卡顿或内存占用升高。\n"
                "毛玻璃强度、模糊半径、窗口圆角与界面动画均可在「设置」中调整或关闭。",
            ),
            (
                "十四、版本管理与其他功能",
                "版本目录分区、从 PCL / HMCL 导入、多版本批量启动、启动脚本、Java 中心、教程中心、"
                "截图图库、崩溃报告、NBT 编辑器、Mod 关系图与多人联机均为本机功能。\n"
                "「从其他启动器导入」只登记版本，不复制或移动原目录中的文件；"
                "但导入的设置会写入本启动器配置，实际行为可能与原启动器不同。\n"
                "启动脚本与自定义 JVM 参数会以当前用户权限执行您填写的命令，请只运行可信内容，"
                "由此产生的后果由您承担。\n"
                "多人联机与内置浏览器访问的服务器、房间与网页均由第三方提供，"
                "其内容、可用性与安全性不由本软件控制。\n"
                "教程内容随版本更新，可能与当前系统或游戏版本存在差异，仅供操作参考。",
            ),
        ],
    },
    "en_US": {
        "title": "MikanCL User Agreement & Disclaimer",
        "intro": "Please read every section below in full. Clicking “Agree and continue” confirms that you "
        "have read, understood and accepted all of it. If you disagree, choose “Disagree, exit” and the "
        "application closes immediately.",
        "checkbox": "I have read and agree to all terms above",
        "accept": "Agree and continue",
        "decline": "Disagree, exit",
        "close": "Close",
        "view": "View user agreement",
        "prompt_switch": "Show the user agreement at startup",
        "version": "Agreement version: {0}",
        "agreed_at": "Accepted at: {0}",
        "not_accepted": "Not accepted yet",
        "sections": [
            (
                "1. Unofficial notice",
                "MikanCL is a third-party open-source launcher. It is not affiliated with, authorised or "
                "sponsored by Mojang Studios, Microsoft, Bilibili, Modrinth, CurseForge or Minecraft Wiki.\n"
                "“Minecraft” and all related trademarks, artwork and sounds belong to their respective owners.\n"
                "This software neither provides nor distributes pirated game files and contains no feature "
                "that bypasses legitimate ownership checks. Please buy the game through official channels.",
            ),
            (
                "2. Accounts and sign-in",
                "Microsoft sign-in uses the official OAuth device-code flow; the token is stored only in "
                "data/accounts.json on this machine and is never uploaded to third-party servers.\n"
                "External sign-in (authlib-injector) submits credentials to the skin site you configure, "
                "whose own policy governs that data.\n"
                "Offline sign-in (offline accounts and offline skins) is kept only as an official "
                "backdoor (internal channel) and cannot prove ownership; if anything goes wrong, "
                "switch it off manually in Settings → Feature toggles.\n"
                "You are responsible for losses caused by sharing, leaking or losing your account, or by "
                "a platform ban.",
            ),
            (
                "3. Content and downloads",
                "Mods, modpacks, resource packs and shaders in the Content Center come from third-party "
                "platforms such as Modrinth and CurseForge. Their licence and usage terms apply; verify and "
                "respect them, including any restriction on redistribution.\n"
                "Third-party content may contain unstable or malicious code, conflict with other mods or be "
                "incompatible with your game version. Back up your saves and judge the risk yourself.\n"
                "This software only provides a technical channel for downloading and installing such content "
                "and gives no warranty about its legality or safety.",
            ),
            (
                "4. Game data and runtime risk",
                "Installing versions, loaders and modpacks writes to your Minecraft directory (libraries, "
                "assets, mods, config, saves, etc.). A wrong operation can damage saves or break the game.\n"
                "Check Java, memory and isolation settings before launching, and back up important saves "
                "regularly.\n"
                "No guarantee of data recoverability is given, and no liability is accepted for lost saves "
                "or damaged configuration.",
            ),
            (
                "5. Network requests and privacy",
                "To install, sign in and search content, the launcher contacts Mojang, BMCLAPI, Modrinth, "
                "CurseForge, GitHub, rg-adguard and any mirror you configure; requests may include the game "
                "version, UI language and account identifier.\n"
                "The launcher does not collect or upload your saves, logs or local files, and never sells or "
                "shares your personal information.\n"
                "Sites opened in the built-in browser (including Bilibili) are governed by their own privacy "
                "policies and terms.",
            ),
            (
                "6. Disclaimer and limitation of liability",
                "The software is provided “as is”, without any express or implied warranty, including "
                "merchantability, fitness for a particular purpose and non-infringement.\n"
                "To the maximum extent permitted by law, the developer is not liable for any direct, indirect, "
                "incidental, special or consequential loss arising from use of, or inability to use, this "
                "software, including lost saves, account bans, device damage and lost profits.\n"
                "Where local law does not allow part of these limits, those parts do not apply to you.",
            ),
            (
                "7. Changes and termination",
                "When the agreement changes, confirmation is requested again at startup. If you disagree, "
                "stop using the software and delete it.\n"
                "You can re-read this agreement at any time in Settings → About, or switch off the startup "
                "prompt (your previous acceptance then remains on record).\n"
                "This agreement is governed by the laws of the People's Republic of China, excluding its "
                "conflict-of-law rules.",
            ),
            (
                "8. Skin factory and offline skins",
                "The built-in Skin Factory lets you pixel-edit a 64×64 skin locally "
                "(including the second-layer overlay), with brush, eraser, fill, colour picker, "
                "mirror and per-part editing, and you can also paint directly on the 3D model "
                "after selecting a body part (both layers are editable). The result is saved as a "
                "PNG and can be applied directly to offline or authlib accounts. Skin files are "
                "stored only on this machine in data/skins and are never uploaded.\n"
                "Minecraft and related art assets are the property of Mojang Studios / Microsoft "
                "and their respective authors. Do not use them commercially or infringe others' rights.",
            ),
            (
                "9. World seeds and terrain preview",
                "On the Seed / Terrain page, entering a world seed makes the launcher run a "
                "built-in Java height-map program (TerrainGen) on the local Java runtime. It offers "
                "two noise modes with vanilla fixed parameters and no extra knobs: Classic "
                "(1.7–1.17, ImprovedNoise permutation and 16-direction gradient tables, multi-octave "
                "with persistence 0.5 and lacunarity 2) and Modern (1.18+, Xoroshiro128++ random "
                "source with climate noise). It contains no biomes, terrain splines or density "
                "functions, so it remains an unofficial terrain approximation. The result is "
                "rendered as 3D terrain near the spawn point.\n"
                "The preview is only a reference for choosing a seed; it is not guaranteed to "
                "match the actual in-game terrain, which is generated by Minecraft itself.",
            ),
            (
                "10. UI effects and frosted glass",
                "Page-switch fade animations and the frosted-glass background are optional "
                "enhancements and can be turned off in Settings to reduce GPU and memory usage.\n"
                "In the enhanced (pywebview) mode the translucent frosted glass is rendered by "
                "Edge WebView2 (Chromium), with the theme colour layered over it as a light tint; "
                "in classic mode it relies on the Windows Desktop Window Manager (DWM). "
                "Neither implementation spawns extra processes or accesses the network. On "
                "unsupported systems, or when the option is off, it falls back to an opaque or "
                "translucent dark background.\n"
                "Text rendering is tuned for Windows ClearType; disabling glass or animations "
                "does not affect any feature.",
            ),
            (
                "11. Third-party modules",
                "The Dependency Completion page lists third-party modules such as Terracotta and "
                "authlib-injector, which are downloaded from their own official release pages only "
                "after you click download. These modules are developed and maintained solely by their "
                "respective authors; MikanCL has no affiliation, authorisation, sponsorship or "
                "endorsement relationship with them and is not responsible for their code, updates or "
                "availability.\n"
                "The download entry is provided merely for your convenience. Any problem arising from "
                "downloading, installing or using such modules (including but not limited to game "
                "crashes, damaged saves or files, interrupted multiplayer sessions, account or security "
                "risks, or device damage) is borne by you alone; the MikanCL author accepts no liability.\n"
                "Third-party modules are governed by their own open-source licences (e.g. AGPL-3.0). "
                "Verify the source, version and licence before use; ignoring this page does not affect "
                "any other feature of the launcher.",
            ),
            (
                "12. Bedrock and Store packages",
                "The Bedrock page shows the offline package index provided by MCAPPX. The launcher only "
                "displays and matches entries and never redistributes game packages.\n"
                "Installation deploys a Microsoft-signed .appx / .msix through the Windows Add-AppxPackage "
                "interface and requires sideloading to be allowed. Deployment time depends on disk speed and "
                "package size; a long “Deploying” phase is normal.\n"
                "Some historical builds must be downloaded manually through the built-in browser, and the "
                "availability and content of those sites are outside our control. Installation, updates and "
                "uninstall follow Microsoft Store and Windows rules; we are not liable for failed installs, "
                "policy blocks or leftovers after uninstall.",
            ),
            (
                "13. Extensions, themes and interface customisation",
                "Extensions import .zip / .mikan-ext files, appear in the sidebar and run inside a sandboxed "
                "iframe that can only talk to the backend through postMessage. Extensions are supplied by "
                "third parties and may contain arbitrary front-end code; enable them only from sources you "
                "trust, and we accept no liability for data or security issues they cause.\n"
                "Themes, skins and animated wallpapers are customisable: themes and skins are stored as JSON "
                "under data/themes on this machine, and wallpapers support MP4 / WebM / GIF / WebP. Custom "
                "assets may be large or use unusual encodings and can slow the interface or raise memory use.\n"
                "Glass strength, blur radius, window corner radius and UI animations can all be adjusted or "
                "disabled in Settings.",
            ),
            (
                "14. Version management and other features",
                "Version-folder partitions, importing from PCL / HMCL, batch launching, launch scripts, the "
                "Java Center, the tutorial center, screenshot gallery, crash reports, NBT editor, mod graph "
                "and multiplayer all run locally.\n"
                "“Import from other launchers” only registers versions and never copies or moves files in the "
                "original folder, but imported settings are written into this launcher's configuration and may "
                "behave differently from the source launcher.\n"
                "Launch scripts and custom JVM arguments execute the commands you enter with your user "
                "privileges; only run trusted content and accept the consequences.\n"
                "Servers, rooms and web pages reached through multiplayer or the built-in browser are provided "
                "by third parties; we do not control their content, availability or safety.\n"
                "Tutorials are updated with releases and may differ from your system or game version; treat "
                "them as operational guidance only.",
            ),
        ],
    },
    "ru_RU": {
        "title": "Пользовательское соглашение и отказ от ответственности MikanCL",
        "intro": "Прочитайте все разделы полностью. Нажатие «Согласен и продолжить» подтверждает, что вы "
        "прочитали, поняли и принимаете их. При несогласии выберите «Не согласен, выйти» — приложение "
        "немедленно закроется.",
        "checkbox": "Я прочитал(а) и принимаю все условия выше",
        "accept": "Согласен и продолжить",
        "decline": "Не согласен, выйти",
        "close": "Закрыть",
        "view": "Открыть соглашение",
        "prompt_switch": "Показывать соглашение при запуске",
        "version": "Версия соглашения: {0}",
        "agreed_at": "Принято: {0}",
        "not_accepted": "Ещё не принято",
        "sections": [
            (
                "1. Неофициальный статус",
                "MikanCL — сторонний лаунчер с открытым кодом. Он не связан, не авторизован и не "
                "спонсируется Mojang Studios, Microsoft, Bilibili, Modrinth, CurseForge или Minecraft Wiki.\n"
                "«Minecraft» и связанные товарные знаки, изображения и звуки принадлежат их владельцам.\n"
                "Программа не предоставляет и не распространяет пиратские копии игры и не содержит "
                "функций обхода проверки лицензии. Приобретайте игру официально.",
            ),
            (
                "2. Учётные записи и вход",
                "Вход Microsoft использует официальный поток OAuth с кодом устройства; токен хранится "
                "только в data/accounts.json на этом компьютере.\n"
                "Внешний вход (authlib-injector) передаёт данные сайту скинов, который вы указали; "
                "там действует его политика.\n"
                "Офлайн-вход (офлайн-аккаунты и скины) сохранён только как служебный «чёрный ход» "
                "(внутренний канал) и не подтверждает лицензию; при проблемах отключите его вручную "
                "в «Настройки → Переключатели функций».\n"
                "Риски, связанные с передачей, утечкой или блокировкой аккаунта, несёт пользователь.",
            ),
            (
                "3. Контент и загрузки",
                "Моды, сборки, наборы ресурсов и шейдеры в Центре контента берутся с Modrinth, "
                "CurseForge и других сторонних платформ; действуют их лицензии и условия использования.\n"
                "Сторонний контент может содержать нестабильный или вредоносный код, конфликтовать с "
                "другими модами или не подходить вашей версии игры. Сделайте резервную копию миров.\n"
                "Программа лишь предоставляет технический канал загрузки и не гарантирует законность "
                "или безопасность такого контента.",
            ),
            (
                "4. Данные игры и риски запуска",
                "Установка версий, загрузчиков и сборок изменяет каталог Minecraft (libraries, assets, "
                "mods, config, saves и др.); ошибка может повредить миры или нарушить запуск.\n"
                "Перед запуском проверьте Java, память и изоляцию; важные миры копируйте регулярно.\n"
                "Восстановление данных не гарантируется, ответственность за потерю миров или "
                "повреждение настроек не принимается.",
            ),
            (
                "5. Сетевые запросы и конфиденциальность",
                "Для установки, входа и поиска контента лаунчер обращается к Mojang, BMCLAPI, Modrinth, "
                "CurseForge, GitHub, rg-adguard и вашим зеркалам; запросы могут содержать версию игры, "
                "язык интерфейса и идентификатор аккаунта.\n"
                "Программа не собирает и не выгружает ваши миры, журналы и локальные файлы, не продаёт "
                "и не передаёт персональные данные.\n"
                "На сторонние сайты во встроенном браузере (включая Bilibili) распространяются их "
                "собственные политики.",
            ),
            (
                "6. Отказ от гарантий и ограничение ответственности",
                "Программа предоставляется «как есть», без явных или подразумеваемых гарантий, включая "
                "товарную пригодность, соответствие цели и отсутствие нарушений прав.\n"
                "В пределах, допускаемых законом, разработчик не отвечает за прямой, косвенный, "
                "случайный, особый или последующий ущерб от использования или невозможности "
                "использования программы, включая потерю миров, блокировку аккаунта, повреждение "
                "оборудования и упущённую выгоду.\n"
                "Если местный закон не допускает часть ограничений, они к вам не применяются.",
            ),
            (
                "7. Изменения и прекращение",
                "При обновлении соглашения подтверждение запрашивается снова при запуске. При несогласии "
                "прекратите использование и удалите программу.\n"
                "Соглашение можно перечитать в «Настройки → О программе» или отключить запрос при "
                "запуске (ранее данное согласие сохраняется).\n"
                "Применяется законодательство Китайской Народной Республики без коллизионных норм.",
            ),
            (
                "8. Фабрика скинов и офлайн-скины",
                "Встроенная «Фабрика скинов» позволяет локально редактировать скин 64×64 по "
                "пикселям (включая второй слой наложения) с помощью кисти, ластика, заливки, "
                "пипетки, зеркального режима и редактирования по частям тела, а также рисовать "
                "прямо по 3D-модели после выбора части тела (доступны оба слоя). Результат "
                "сохраняется в PNG и может быть применён к офлайн- или authlib-аккаунту. "
                "Файлы скинов хранятся только на этом компьютере в data/skins и никуда не "
                "загружаются.\n"
                "Minecraft и связанные графические материалы принадлежат Mojang Studios / "
                "Microsoft и их авторам. Не используйте их в коммерческих целях и не "
                "нарушайте права других.",
            ),
            (
                "9. Сид мира и предпросмотр ландшафта",
                "На странице «Сид / ландшафт» после ввода сида лаунчер запускает встроенную "
                "Java-программу карты высот (TerrainGen) на локальной среде Java. Доступны два "
                "режима шума с фиксированными параметрами оригинала и без дополнительных настроек: "
                "классический (1.7–1.17, таблица перестановок ImprovedNoise и 16 направлений "
                "градиента, многооктавное суммирование с persistence 0.5 и lacunarity 2) и новый "
                "(1.18+, генератор Xoroshiro128++ и климатический шум). Биомы, сплайны рельефа и "
                "функции плотности не реализованы, поэтому это по-прежнему неофициальная "
                "аппроксимация. Результат отображается как 3D-ландшафт возле точки появления.\n"
                "Предпросмотр служит лишь ориентиром при выборе сида; он не гарантирует "
                "совпадения с реальным ландшафтом в игре, который генерирует сам Minecraft.",
            ),
            (
                "10. Эффекты интерфейса и матовое стекло",
                "Анимация затухания при переключении страниц и матовое стекло являются "
                "необязательными улучшениями и могут быть отключены в настройках, чтобы "
                "снизить нагрузку на GPU и память.\n"
                "В расширенном режиме (pywebview) полупрозрачное матовое стекло отрисовывает "
                "Edge WebView2 (Chromium), а цвет темы накладывается поверх как лёгкая подцветка; "
                "в классическом режиме используется композиция DWM (диспетчер окон рабочего стола "
                "Windows). Обе реализации не запускают дополнительные процессы и не обращаются к "
                "сети. На неподдерживаемых системах или при отключении опции фон становится "
                "непрозрачным либо полупрозрачным тёмным.\n"
                "Отрисовка текста оптимизирована под Windows ClearType; отключение стекла или "
                "анимаций не влияет на функции.",
            ),
            (
                "11. Сторонние модули",
                "На странице «Дополнение зависимостей» перечислены сторонние модули, такие как "
                "Terracotta и authlib-injector; загрузка начинается с их официальных страниц релизов "
                "только после нажатия кнопки вами. Эти модули разрабатывают и поддерживают "
                "исключительно их авторы; MikanCL не связан с ними, не авторизован и не даёт никаких "
                "гарантий в отношении их кода, обновлений и доступности.\n"
                "Ссылка для загрузки предоставлена исключительно для удобства. Любые проблемы, "
                "возникшие при загрузке, установке или использовании таких модулей (включая, помимо "
                "прочего, сбои игры, повреждение миров или файлов, обрыв сетевой игры, риски для "
                "аккаунта или безопасности, повреждение оборудования), несёте вы; автор MikanCL "
                "ответственности не несёт.\n"
                "На сторонние модули распространяются их собственные открытые лицензии "
                "(например, AGPL-3.0). Перед использованием проверьте источник, версию и лицензию; "
                "если они не нужны, страницу можно просто игнорировать — остальные функции лаунчера "
                "работают как обычно.",
            ),
            (
                "12. Bedrock и пакеты из Store",
                "Страница «Bedrock» показывает каталог офлайн-пакетов, предоставленный MCAPPX. Лаунчер "
                "только отображает и сопоставляет записи и не распространяет игровые пакеты.\n"
                "Установка разворачивает подписанный Microsoft пакет .appx / .msix через системный "
                "Add-AppxPackage и требует разрешённой боковой загрузки. Время развёртывания зависит от "
                "скорости диска и размера пакета; долгая фаза «Развёртывание» — это нормально.\n"
                "Некоторые исторические версии приходится скачивать вручную через встроенный браузер; "
                "доступность и содержимое таких сайтов от нас не зависят. Установка, обновление и удаление "
                "подчиняются правилам Microsoft Store и Windows; мы не отвечаем за неудачную установку, "
                "блокировку политиками или остатки после удаления.",
            ),
            (
                "13. Расширения, темы и оформление интерфейса",
                "Расширения импортируются в формате .zip / .mikan-ext, отображаются в боковой панели и "
                "работают в изолированном iframe, общаясь с бэкендом только через postMessage. Расширения "
                "предоставляют третьи авторы, они могут содержать произвольный внешний код; включайте "
                "только доверенные источники, и мы не несём ответственности за проблемы с данными или "
                "безопасностью, вызванные расширениями.\n"
                "Темы, скины и анимированные обои настраиваются: темы и скины хранятся в JSON в "
                "data/themes на этом компьютере, обои поддерживают MP4 / WebM / GIF / WebP. Большие или "
                "необычные ресурсы могут замедлить интерфейс или увеличить потребление памяти.\n"
                "Сила стекла, радиус размытия, скругление углов окна и анимации интерфейса настраиваются "
                "или отключаются в настройках.",
            ),
            (
                "14. Управление версиями и другие функции",
                "Разделы папок версий, импорт из PCL / HMCL, пакетный запуск, скрипты запуска, Java-центр, "
                "центр обучения, галерея скриншотов, отчёты о сбоях, редактор NBT, граф модов и сетевая "
                "игра работают локально.\n"
                "«Импорт из других лаунчеров» только регистрирует версии и не копирует и не перемещает "
                "файлы исходной папки, но импортированные настройки записываются в конфигурацию этого "
                "лаунчера и могут вести себя иначе, чем в исходном.\n"
                "Скрипты запуска и пользовательские аргументы JVM выполняют введённые вами команды с "
                "правами вашей учётной записи; запускайте только доверенное содержимое и принимайте "
                "последствия.\n"
                "Серверы, комнаты и веб-страницы, доступные через сетевую игру или встроенный браузер, "
                "предоставляются третьими сторонами; мы не контролируем их содержимое, доступность и "
                "безопасность.\n"
                "Учебные материалы обновляются вместе с релизами и могут отличаться от вашей системы или "
                "версии игры; используйте их только как руководство.",
            ),
        ],
    },
    "fr_FR": {
        "title": "Contrat utilisateur et clause de non-responsabilité MikanCL",
        "intro": "Lisez intégralement chaque section ci-dessous. Cliquer sur « Accepter et continuer » "
        "confirme que vous les avez lues, comprises et acceptées. En cas de refus, choisissez "
        "« Refuser, quitter » : l'application se ferme immédiatement.",
        "checkbox": "J'ai lu et j'accepte l'ensemble des conditions ci-dessus",
        "accept": "Accepter et continuer",
        "decline": "Refuser, quitter",
        "close": "Fermer",
        "view": "Voir le contrat utilisateur",
        "prompt_switch": "Afficher le contrat au démarrage",
        "version": "Version du contrat : {0}",
        "agreed_at": "Accepté le : {0}",
        "not_accepted": "Pas encore accepté",
        "sections": [
            (
                "1. Mention non officielle",
                "MikanCL est un lanceur open source tiers, sans affiliation, autorisation ni parrainage de "
                "Mojang Studios, Microsoft, Bilibili, Modrinth, CurseForge ou Minecraft Wiki.\n"
                "« Minecraft » ainsi que les marques, images et sons associés appartiennent à leurs "
                "titulaires respectifs.\n"
                "Le logiciel ne fournit ni ne distribue de copie piratée du jeu et n'inclut aucune fonction "
                "contournant la vérification de licence. Achetez le jeu par les canaux officiels.",
            ),
            (
                "2. Comptes et connexion",
                "La connexion Microsoft utilise le flux officiel OAuth par code d'appareil ; le jeton est "
                "stocké uniquement dans data/accounts.json sur cette machine.\n"
                "La connexion externe (authlib-injector) transmet les identifiants au site de skins que vous "
                "configurez, selon sa propre politique.\n"
                "La connexion hors ligne (comptes et skins hors ligne) n'est conservée qu'en tant que "
                "porte dérobée officielle (canal interne) et ne prouve pas la licence ; en cas de "
                "problème, désactivez-la dans « Paramètres → Interrupteurs de fonctions ».\n"
                "Vous assumez les pertes liées au partage, à la fuite ou au bannissement de votre compte.",
            ),
            (
                "3. Contenus et téléchargements",
                "Les mods, modpacks, packs de ressources et shaders du Centre de contenu proviennent de "
                "plateformes tierces (Modrinth, CurseForge…) : leurs licences et conditions s'appliquent.\n"
                "Ces contenus peuvent comporter du code instable ou malveillant, entrer en conflit avec "
                "d'autres mods ou être incompatibles avec votre version. Sauvegardez vos mondes.\n"
                "Le logiciel ne fournit qu'un canal technique de téléchargement et ne garantit ni la "
                "légalité ni la sûreté de ces contenus.",
            ),
            (
                "4. Données de jeu et risques d'exécution",
                "L'installation de versions, de chargeurs et de modpacks écrit dans le dossier Minecraft "
                "(libraries, assets, mods, config, saves…) ; une mauvaise manipulation peut corrompre les "
                "sauvegardes ou empêcher le lancement.\n"
                "Vérifiez Java, la mémoire et l'isolation avant de lancer, et sauvegardez régulièrement.\n"
                "Aucune récupération de données n'est garantie et aucune responsabilité n'est acceptée pour "
                "la perte de sauvegardes ou la corruption de configuration.",
            ),
            (
                "5. Requêtes réseau et vie privée",
                "Pour installer, se connecter et rechercher, le lanceur contacte Mojang, BMCLAPI, Modrinth, "
                "CurseForge, GitHub, rg-adguard et vos miroirs ; les requêtes peuvent inclure la version du "
                "jeu, la langue de l'interface et l'identifiant du compte.\n"
                "Le lanceur ne collecte ni ne téléverse vos sauvegardes, journaux ou fichiers locaux, et ne "
                "vend ni ne partage vos informations personnelles.\n"
                "Les sites ouverts dans le navigateur intégré (dont Bilibili) relèvent de leurs propres "
                "politiques.",
            ),
            (
                "6. Absence de garantie et limitation de responsabilité",
                "Le logiciel est fourni « en l'état », sans garantie expresse ou implicite, y compris de "
                "qualité marchande, d'adéquation à un usage particulier ou d'absence de contrefaçon.\n"
                "Dans les limites permises par la loi, le développeur n'est pas responsable des dommages "
                "directs, indirects, accessoires, spéciaux ou consécutifs découlant de l'utilisation ou de "
                "l'impossibilité d'utiliser le logiciel, notamment la perte de sauvegardes, le bannissement "
                "de compte, l'endommagement du matériel et le manque à gagner.\n"
                "Si votre loi locale interdit une partie de ces limites, elles ne s'appliquent pas à vous.",
            ),
            (
                "7. Modifications et résiliation",
                "En cas de mise à jour du contrat, une confirmation est redemandée au démarrage. En cas de "
                "refus, cessez l'utilisation et supprimez le logiciel.\n"
                "Vous pouvez relire ce contrat dans « Paramètres → À propos » ou désactiver l'invite au "
                "démarrage (votre acceptation précédente reste enregistrée).\n"
                "Le présent contrat est régie par le droit de la République populaire de Chine, hors règles "
                "de conflit de lois.",
            ),
            (
                "8. Fabrique de skins et skins hors ligne",
                "La « Fabrique de skins » intégrée permet d'éditer localement un skin 64×64 "
                "pixel par pixel (y compris le second calque), avec pinceau, gomme, pot de "
                "peinture, pipette, mode miroir et édition par partie du corps, et de peindre "
                "directement sur le modèle 3D après avoir choisi une partie (les deux calques "
                "sont éditables). Le résultat est "
                "enregistré en PNG et peut être appliqué directement à un compte hors ligne ou "
                "authlib. Les fichiers de skin ne sont stockés que sur cette machine dans "
                "data/skins et ne sont jamais téléversés.\n"
                "Minecraft et les ressources artistiques associées appartiennent à Mojang "
                "Studios / Microsoft et à leurs auteurs. Ne les utilisez pas à des fins "
                "commerciales et ne portez pas atteinte aux droits d'autrui.",
            ),
            (
                "9. Graines de monde et aperçu du terrain",
                "Sur la page « Graine / terrain », après avoir saisi une graine de monde, le "
                "lanceur exécute un programme Java de carte de hauteur intégré (TerrainGen) sur "
                "le runtime Java local. Deux modes de bruit à paramètres fixes, sans réglage "
                "supplémentaire, sont proposés : le mode classique (1.7–1.17, table de "
                "permutation et 16 directions de gradient d'ImprovedNoise, octaves multiples avec "
                "persistence 0,5 et lacunarity 2) et le mode moderne (1.18+, source aléatoire "
                "Xoroshiro128++ et bruit climatique). Ni biomes, ni splines de terrain, ni "
                "fonctions de densité ne sont inclus : il reste donc une approximation non "
                "officielle. Le résultat est rendu sous forme de terrain 3D près du point "
                "d'apparition.\n"
                "L'aperçu n'est qu'une référence pour choisir une graine ; il n'est pas garanti "
                "de correspondre au terrain réel en jeu, qui est généré par Minecraft lui-même.",
            ),
            (
                "10. Effets d'interface et verre dépoli",
                "Les animations de fondu au changement de page et le fond en verre dépoli sont "
                "des améliorations facultatives et peuvent être désactivées dans les paramètres "
                "pour réduire la charge GPU et la mémoire.\n"
                "En mode enrichi (pywebview), le verre dépoli translucide est rendu par Edge "
                "WebView2 (Chromium), la couleur du thème étant appliquée en légère teinte ; en "
                "mode classique, il repose sur la composition du Gestionnaire de fenêtres du "
                "bureau (DWM) de Windows. Aucune des deux implémentations ne lance de processus "
                "supplémentaire ni n'accède au réseau. Sur les systèmes non pris en charge, ou "
                "si l'option est désactivée, le fond devient opaque ou sombre translucide.\n"
                "Le rendu du texte est optimisé pour ClearType ; désactiver le verre ou les "
                "animations n'affecte aucune fonction.",
            ),
            (
                "11. Modules tiers",
                "La page « Complétion des dépendances » répertorie des modules tiers tels que "
                "Terracotta et authlib-injector, téléchargés depuis leurs propres pages de publication "
                "officielles uniquement après votre clic. Ces modules sont développés et maintenus "
                "exclusivement par leurs auteurs respectifs ; MikanCL n'a aucun lien d'affiliation, "
                "d'autorisation, de parrainage ou de garantie avec eux et n'est pas responsable de leur "
                "code, de leurs mises à jour ni de leur disponibilité.\n"
                "L'accès au téléchargement n'est fourni que pour votre commodité. Tout problème "
                "découlant du téléchargement, de l'installation ou de l'utilisation de ces modules "
                "(notamment plantages du jeu, sauvegardes ou fichiers endommagés, interruption du "
                "multijoueur, risques pour le compte ou la sécurité, dommages matériels) est à votre "
                "charge ; l'auteur de MikanCL décline toute responsabilité.\n"
                "Ces modules relèvent de leurs propres licences open source (par exemple AGPL-3.0). "
                "Vérifiez la source, la version et la licence avant utilisation ; ignorer cette page "
                "n'affecte aucune autre fonction du lanceur.",
            ),
            (
                "12. Bedrock et paquets du Store",
                "La page « Bedrock » affiche le catalogue de paquets hors ligne fourni par MCAPPX. Le lanceur "
                "ne fait qu'afficher et associer des entrées et ne redistribue jamais de paquets de jeu.\n"
                "L'installation déploie un .appx / .msix signé par Microsoft via l'interface Windows "
                "Add-AppxPackage et exige que le chargement latéral soit autorisé. La durée dépend du disque "
                "et de la taille du paquet ; une phase « Déploiement » prolongée est normale.\n"
                "Certaines versions historiques doivent être téléchargées manuellement via le navigateur "
                "intégré ; la disponibilité et le contenu de ces sites échappent à notre contrôle. "
                "L'installation, les mises à jour et la désinstallation suivent les règles du Microsoft Store "
                "et de Windows ; nous déclinons toute responsabilité en cas d'échec, de blocage par une "
                "stratégie ou de résidus après désinstallation.",
            ),
            (
                "13. Extensions, thèmes et personnalisation de l'interface",
                "Les extensions s'importent au format .zip / .mikan-ext, apparaissent dans la barre latérale "
                "et s'exécutent dans une iframe isolée qui ne communique avec le backend que par postMessage. "
                "Elles sont fournies par des tiers et peuvent contenir du code front-end arbitraire ; "
                "n'activez que des sources de confiance et nous n'assumons aucune responsabilité pour les "
                "problèmes de données ou de sécurité qu'elles causent.\n"
                "Thèmes, skins et fonds d'écran animés sont personnalisables : thèmes et skins sont stockés "
                "en JSON dans data/themes sur cette machine, les fonds d'écran acceptent MP4 / WebM / GIF / "
                "WebP. Des ressources volumineuses ou inhabituelles peuvent ralentir l'interface ou "
                "augmenter la mémoire utilisée.\n"
                "L'intensité du verre, le rayon de flou, l'arrondi des coins de fenêtre et les animations "
                "peuvent être ajustés ou désactivés dans les paramètres.",
            ),
            (
                "14. Gestion des versions et autres fonctions",
                "Les partitions de dossiers de versions, l'import depuis PCL / HMCL, le lancement par lots, "
                "les scripts de lancement, le Java Center, le centre de tutoriels, la galerie de captures, "
                "les rapports de plantage, l'éditeur NBT, le graphe de mods et le multijoueur s'exécutent "
                "localement.\n"
                "« Importer depuis d'autres lanceurs » ne fait qu'enregistrer des versions et ne copie ni ne "
                "déplace aucun fichier du dossier d'origine, mais les réglages importés sont écrits dans la "
                "configuration de ce lanceur et peuvent se comporter différemment de ceux du lanceur source.\n"
                "Les scripts de lancement et les arguments JVM personnalisés exécutent les commandes saisies "
                "avec les privilèges de votre compte ; n'exécutez que du contenu de confiance et assumez les "
                "conséquences.\n"
                "Les serveurs, salons et pages web atteints via le multijoueur ou le navigateur intégré sont "
                "fournis par des tiers ; nous ne contrôlons ni leur contenu, ni leur disponibilité, ni leur "
                "sécurité.\n"
                "Les tutoriels évoluent avec les versions et peuvent différer de votre système ou version du "
                "jeu ; considérez-les comme une aide opérationnelle.",
            ),
        ],
    },
    "ja_JP": {
        "title": "MikanCL 利用規約・免責事項",
        "intro": "以下のすべての条項を最後までお読みください。「同意して続行」を押すと、全文を読み、"
        "理解し、同意したものとみなされます。同意しない場合は「同意しない・終了」を選ぶと、"
        "ソフトは直ちに終了します。",
        "checkbox": "上記の全条項を読み、同意します",
        "accept": "同意して続行",
        "decline": "同意しない・終了",
        "close": "閉じる",
        "view": "利用規約を表示",
        "prompt_switch": "起動時に利用規約の確認を表示",
        "version": "規約バージョン：{0}",
        "agreed_at": "同意日時：{0}",
        "not_accepted": "未同意",
        "sections": [
            (
                "一、非公式の告知",
                "MikanCL は第三者が開発するオープンソースのランチャーであり、Mojang Studios、Microsoft、"
                "Bilibili、Modrinth、CurseForge、Minecraft Wiki といかなる提携・許諾・スポンサー関係もありません。\n"
                "「Minecraft」および関連する商標・画像・音源は各権利者に帰属します。\n"
                "本ソフトは海賊版ゲームを提供・配布せず、正規ライセンス確認を回避する機能も含みません。"
                "ゲームは公式チャネルで購入してください。",
            ),
            (
                "二、アカウントとログイン",
                "Microsoft ログインは公式の OAuth デバイスコード方式を使用し、トークンは本機の "
                "data/accounts.json にのみ保存されます。\n"
                "外部ログイン（authlib-injector）は、指定したスキンサイトに認証情報を送信し、"
                "その取り扱いは当該サイトの規定に従います。\n"
                "オフラインログイン（オフラインアカウントとオフラインスキン）は公式の裏口"
                "（内部チャネル）としてのみ残されており、正規ライセンスを証明できません。"
                "問題がある場合は「設定 → 機能スイッチ」で手動で無効化できます。\n"
                "アカウントの共有・漏洩・停止などによる損害は利用者が負担します。",
            ),
            (
                "三、コンテンツとダウンロード",
                "コンテンツセンターの Mod・Modpack・リソースパック・シェーダーは Modrinth / CurseForge "
                "などの第三者プラットフォーム由来で、各ライセンスと利用条件が適用されます。\n"
                "第三者のコンテンツには不安定なコードや悪意ある挙動、他の Mod との競合、"
                "バージョン不整合が含まれる可能性があります。導入前にセーブデータをバックアップしてください。\n"
                "本ソフトはダウンロードと導入の技術的経路のみを提供し、内容の合法性や安全性を保証しません。",
            ),
            (
                "四、ゲームデータと実行リスク",
                "バージョン・ローダー・Modpack の導入は Minecraft フォルダ（libraries、assets、mods、"
                "config、saves 等）を書き換えます。誤操作はセーブデータの破損や起動不能を招く恐れがあります。\n"
                "起動前に Java・メモリ・隔離設定を確認し、重要なセーブデータは定期的にバックアップしてください。\n"
                "データ復旧は保証されず、セーブデータの消失や設定破損について責任を負いません。",
            ),
            (
                "五、通信とプライバシー",
                "導入・ログイン・検索のため、Mojang、BMCLAPI、Modrinth、CurseForge、GitHub、rg-adguard "
                "および設定したミラーへ通信し、バージョン・表示言語・アカウント識別子が含まれる場合があります。\n"
                "本ソフトはセーブデータ・ログ・ローカルファイルを収集・送信せず、"
                "個人情報を第三者へ販売・共有しません。\n"
                "内蔵ブラウザで開く第三者サイト（Bilibili を含む）には、それぞれのプライバシーポリシーが適用されます。",
            ),
            (
                "六、免責と責任の制限",
                "本ソフトは「現状のまま」提供され、商品性・特定目的への適合性・非侵害性を含め、"
                "明示または黙示の保証を一切行いません。\n"
                "法律で許される最大限の範囲で、開発者は本ソフトの使用または使用不能に起因する直接的・"
                "間接的・偶発的・特別・結果的損害（セーブデータ消失、アカウント停止、機器故障、逸失利益等）"
                "について責任を負いません。\n"
                "お住まいの法令がこれらの制限の一部を認めない場合、その部分は適用されません。",
            ),
            (
                "七、規約の変更と終了",
                "規約を更新した場合は起動時に再度確認を求めます。同意しない場合は使用を中止し、"
                "本ソフトを削除してください。\n"
                "「設定 → このアプリについて」からいつでも再確認できます。起動時の確認表示は無効にできます"
                "（無効にしても前回の同意内容が有効です）。\n"
                "本規約は中華人民共和国の法律（抵触法規を除く）に準拠します。",
            ),
            (
                "八、スキンファクトリーとオフラインスキン",
                "内蔵の「スキンファクトリー」では、64×64 スキン（第2レイヤー含む）を"
                "ローカルでピクセル編集できます。ブラシ・消しゴム・塗りつぶし・スポイト・"
                "ミラー・部位別編集に対応し、部位を選んで 3D モデル上に直接描くこともできます"
                "（第1・第2レイヤーの両方を編集可能）。仕上がりは PNG で保存され、オフラインまたは "
                "authlib アカウントに直接適用できます。スキンファイルは本機の "
                "data/skins にのみ保存され、いかなるサーバーにもアップロードされません。\n"
                "Minecraft および関連する画像素材の著作権は Mojang Studios / Microsoft "
                "および各原作者に帰属します。営利目的での使用や他人の権利侵害にご注意ください。",
            ),
            (
                "九、ワールドシードと地形プレビュー",
                "「シード / 地形」ページでワールドシードを入力すると、ランチャーはローカルの "
                "Java ランタイム上で内蔵のハイトマッププログラム（TerrainGen）を実行します。"
                "パラメータを固定した 2 種類のノイズモード（追加の調整項目はありません）を"
                "切り替えられます：クラシック（1.7–1.17、ImprovedNoise の置換表と 16 方向の"
                "勾配表、persistence 0.5・lacunarity 2 のマルチオクターブ）と"
                "新版（1.18+、Xoroshiro128++ 乱数源と気候ノイズ）です。"
                "バイオーム・地形スプライン・密度関数は含まないため、"
                "非公式の地形近似であることに変わりはありません。生成結果は"
                "スポーン地点周辺の 3D 地形として描画されます。\n"
                "このプレビューはシード選びの参考に過ぎず、ゲーム内の実際の地形と完全に"
                "一致する保証はありません。実際の地形・バイオームは Minecraft 本体の生成結果に"
                "従います。",
            ),
            (
                "十、UI エフェクトとすりガラス",
                "ページ切り替えのフェードアニメーションやすりガラス背景はオプションの"
                "強化機能で、GPU とメモリの負荷を減らすため設定でオフにできます。\n"
                "拡張モード（pywebview）では、半透明のすりガラスを Edge WebView2（Chromium）が"
                "描画し、テーマ色を淡い色合いとして重ねます。クラシックモードでは Windows の"
                "デスクトップ ウィンドウ マネージャー（DWM）による合成を使用します。"
                "いずれも追加のプロセス起動やネットワーク通信は行いません。"
                "非対応システムやオプションがオフの場合、不透明または半透明の濃い背景に"
                "自動でフォールバックします。\n"
                "文字描画は Windows ClearType 向けに最適化されており、すりガラスやアニメーションを"
                "オフにしても機能に影響はありません。",
            ),
            (
                "十一、第三者モジュール",
                "「依存関係の補完」ページには、Terracotta（陶瓦联机）や authlib-injector などの"
                "第三者モジュールが一覧表示され、あなたがクリックした場合にのみ各公式リリースページから"
                "ダウンロードされます。これらのモジュールは各作者が独自に開発・保守しており、"
                "MikanCL はその作者と提携・許諾・スポンサー・保証の関係を一切持たず、"
                "コード・更新・提供状況について責任を負いません。\n"
                "ダウンロード入口の提供はあくまで利便性のためです。これらのモジュールのダウンロード・"
                "インストール・使用に起因するあらゆる問題（ゲームのクラッシュ、セーブデータや"
                "ファイルの破損、マルチプレイの中断、アカウントやセキュリティ上のリスク、"
                "機器の故障などを含みますがこれらに限りません）は利用者自身が負担し、"
                "MikanCL の作者は一切責任を負いません。\n"
                "第三者モジュールには各々のオープンソースライセンス（AGPL-3.0 など）が適用されます。"
                "使用前に提供元・バージョン・ライセンスを確認してください。不要な場合はこのページを"
                "無視してもランチャーの他の機能には影響しません。",
            ),
            (
                "十二、Bedrock とストアのインストールパッケージ",
                "「Bedrock」ページは MCAPPX が提供するオフラインインストールパッケージの索引を表示する"
                "だけで、本ソフトがゲームのパッケージを再配布することはありません。\n"
                "インストールは Microsoft 署名済みの .appx / .msix を Windows の Add-AppxPackage で"
                "展開するため、サイドロードが許可されている必要があります。所要時間はディスク性能と"
                "パッケージサイズに依存し、「展開中」が長時間続くのは正常です。\n"
                "一部の過去バージョンは内蔵ブラウザから手動でダウンロードする必要があり、"
                "そのサイトの可用性や内容は本ソフトの管理外です。インストール・更新・アンインストールは"
                "Microsoft Store と Windows の規則に従い、失敗・ポリシーによるブロック・"
                "アンインストール後の残存について本ソフトは責任を負いません。",
            ),
            (
                "十三、拡張機能・テーマ・画面のカスタマイズ",
                "拡張機能は .zip / .mikan-ext を読み込め、有効にするとサイドバーに表示され、"
                "サンドボックス化された iframe 内で動作して postMessage 経由でのみバックエンドと"
                "通信します。拡張機能は第三者が提供し、任意のフロントエンドコードを含む可能性があるため、"
                "信頼できる提供元のみ有効にしてください。拡張機能によるデータやセキュリティの問題について"
                "本ソフトは責任を負いません。\n"
                "テーマ・スキン・動く壁紙はカスタマイズ可能です。テーマとスキンは本機の data/themes に"
                "JSON で保存され、壁紙は MP4 / WebM / GIF / WebP に対応します。大きなファイルや特殊な"
                "エンコードの素材は画面の重さやメモリ使用量の増加につながることがあります。\n"
                "すりガラスの強度・ぼかし半径・ウィンドウの角の丸み・画面アニメーションは設定で"
                "調整または無効化できます。",
            ),
            (
                "十四、バージョン管理とその他の機能",
                "バージョンフォルダの分割、PCL / HMCL からのインポート、複数バージョンの一括起動、"
                "起動スクリプト、Java センター、チュートリアルセンター、スクリーンショットギャラリー、"
                "クラッシュレポート、NBT エディター、Mod グラフ、マルチプレイはすべて本機で動作します。\n"
                "「他のランチャーからインポート」はバージョンを登録するだけで、元のフォルダのファイルを"
                "コピーも移動もしませんが、取り込んだ設定は本ランチャーの設定に書き込まれ、"
                "元のランチャーと動作が異なる場合があります。\n"
                "起動スクリプトと独自の JVM 引数は、入力したコマンドを現在のユーザー権限で実行します。"
                "信頼できる内容のみを実行し、結果についてはご自身で負担してください。\n"
                "マルチプレイや内蔵ブラウザで接続するサーバー・ルーム・Web ページは第三者が提供するもので、"
                "その内容・可用性・安全性を本ソフトは管理しません。\n"
                "チュートリアルはリリースに合わせて更新されるため、お使いのシステムやゲームバージョンと"
                "異なる場合があります。操作の参考としてご利用ください。",
            ),
        ],
    },
}


def _normalize_language(lang: str) -> str:
    """未知语言回退中文，与 i18n 的约定保持一致。"""
    return lang if lang in _TEXTS else "zh_CN"


def texts(lang: str) -> dict:
    """返回该语言的协议标题、按钮与全部条款。"""
    return _TEXTS[_normalize_language(lang)]


def accepted(config) -> bool:
    """是否已同意当前版本的协议。"""
    return str(getattr(config, "agreement_version", "") or "") == AGREEMENT_VERSION


def needs_prompt(config) -> bool:
    """是否需要弹出协议确认：设置里关闭提示、或已同意当前版本时跳过。"""
    if not bool(getattr(config, "agreement_prompt", True)):
        return False
    return not accepted(config)


def accept(config) -> None:
    """记录同意：写入版本号与时间戳，并立即落盘。"""
    config.agreement_version = AGREEMENT_VERSION
    config.agreement_accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        config.save()
    except Exception:  # noqa: BLE001 - 写盘失败不应阻止本次启动
        pass


def accepted_at(config) -> str:
    return str(getattr(config, "agreement_accepted_at", "") or "")


__all__ = [
    "AGREEMENT_VERSION",
    "texts",
    "accepted",
    "needs_prompt",
    "accept",
    "accepted_at",
]
