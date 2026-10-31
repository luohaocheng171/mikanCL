"""用户协议与免责声明：多语言文案 + 同意状态判定。

协议正文按语言分块存放（不经过 .qm），保证 5 种界面语言都能完整阅读；
同意状态记录在 config.json，协议版本号变化后会再次要求确认。
"""

from __future__ import annotations

from datetime import datetime

AGREEMENT_VERSION = "1.3"

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
                "本软件不提供、不分发破解版游戏，也不包含绕过正版验证的功能；请通过官方渠道购买正版游戏。",
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
                "本软件仅提供下载与安装的技术通道，不对第三方内容的合法性、安全性作出任何担保。",
            ),
            (
                "四、游戏数据与运行风险",
                "安装版本、加载器、整合包会写入并修改 Minecraft 目录（含 libraries、assets、mods、config、"
                "saves 等），误操作可能损坏存档或导致游戏无法启动。\n"
                "启动前请在「版本设置」中确认 Java、内存与隔离策略；重要存档请自行定期备份。\n"
                "本软件不承诺任何数据可恢复性，也不对存档丢失、配置损坏承担责任。",
            ),
            (
                "五、网络请求与隐私",
                "为完成安装、登录与内容检索，本软件会向 Mojang、BMCLAPI、Modrinth、CurseForge、"
                "GitHub、rg-adguard 及您配置的镜像站发送网络请求，请求中可能包含版本号、界面语言与账号标识。\n"
                "本软件不收集、不上传您的存档、日志与本地文件，不向任何第三方出售或共享您的个人信息。\n"
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
                "毛玻璃效果依赖 Windows 桌面窗口管理器（DWM）合成，不额外启动进程、不联网；"
                "在不支持的系统上会自动回退为半透明深色背景。",
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
                "The frosted-glass effect relies on the Windows Desktop Window Manager (DWM) "
                "for composition; it does not spawn extra processes or access the network. On "
                "unsupported systems it falls back to a translucent dark background.",
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
                "Анимация затухания при переключении страниц и матовое (акриловое) стекло "
                "являются необязательными улучшениями и могут быть отключены в настройках, "
                "чтобы снизить нагрузку на GPU и память.\n"
                "Эффект матового стекла использует композицию DWM (диспетчер окон рабочего "
                "стола Windows), не запускает дополнительные процессы и не обращается к сети. "
                "На неподдерживаемых системах он заменяется полупрозрачным тёмным фоном.",
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
                "L'effet de verre dépoli repose sur la composition du Gestionnaire de fenêtres "
                "du bureau (DWM) de Windows ; il ne lance aucun processus supplémentaire et "
                "n'accède pas au réseau. Sur les systèmes non pris en charge, il est remplacé "
                "par un fond sombre translucide.",
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
                "すりガラス効果は Windows のデスクトップ ウィンドウ マネージャー（DWM）に"
                "よる合成に依存し、追加のプロセス起動やネットワーク通信は行いません。"
                "非対応システムでは半透明の濃い背景に自動でフォールバックします。",
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
