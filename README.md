# MikanCL v4.9.3 官方文档

<div align="center">

<img src="assets/mikan.png" width="96" alt="MikanCL Logo" />

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-Qt6-brightgreen.svg)](https://www.qt.io/)
[![License](https://img.shields.io/badge/License-GPL--3.0-red.svg)](https://www.gnu.org/licenses/gpl-3.0.html)

**MikanCL** — 正版登录 + 外置登录 + 5 大加载器一键安装 + Modrinth/CurseForge 内容中心（含中文译名）+ 整合包管理 + 陶瓦联机 + Java 中心 + 教程 Wiki + NBT 编辑器 + 启动动画

*AI 辅助开发工具：DeepSeek*

</div>

---

## 项目概述

MikanCL 是一款面向 Windows 的 Minecraft 启动器，采用 **PySide6（Qt6）** 构建深色主题界面，目录结构兼容 HMCL / PCL 的常见习惯。项目以**单文件可执行程序**为目标，可通过 PyInstaller 打包为 `MikanCL.exe`，双击即用，无需 Python 环境。

启动器按**实例（Instance）**组织游戏：每个实例绑定一个 Minecraft 版本与一个可选加载器，可独立配置 Java、内存、JVM 参数、隔离策略与 Mod 列表；整合包导入后自动成为独立实例，互不干扰。

### 版本信息

- **当前版本**：v4.9.3
- **框架**：PySide6（Qt6，Fusion 深色主题 + 自绘标题栏）
- **Python 要求**：3.10+
- **运行平台**：Windows 10 / 11（x64）
- **Mod 加载器**：5 款主流加载器 + 1 款实验性加载器（Forbric）
- **账号体系**：微软正版 / 外置登录（authlib-injector）/ 离线账号
- **内容平台**：Modrinth、CurseForge（内置默认 API Key，可替换）
- **下载源**：Mojang 官方源、BMCLAPI 镜像、自定义源（可增删、可排序）
- **界面语言**：简体中文 / English / Русский / Français / 日本語（5 种，设置内切换）
- **依赖管理**：「依赖补全」页集中管理所有不可内置的第三方依赖（联机、登录、运行时、加载器），并支持缺失依赖体检与静默补全
- **许可证**：GPL-3.0（GNU General Public License v3.0，见[许可证](#许可证)章节）

---

## 运行截图与效果图

| 皮肤工厂（像素编辑器 + 3D 预览） | 世界种子 · 3D 地形预览 |
| :---: | :---: |
| ![皮肤工厂](assets/screenshots/skin_factory.png) | ![地形预览](assets/screenshots/terrain_preview.png) |

| 毛玻璃（Acrylic）界面 | 主界面（深色主题） |
| :---: | :---: |
| ![毛玻璃界面](assets/screenshots/acrylic_ui.png) | ![Logo](assets/mikan.png) |

> 上图为功能效果示意图；皮肤工厂、种子地形、毛玻璃均可在「设置 → 外观 / 功能开关」中开启或关闭，关闭动画可进一步降低 GPU 占用。

---

## MikanCL 能做什么

它不是「只能点启动」的壳子：从装版本、装加载器、装整合包，到找 Mod、找材质包、开联机、换 Java、查崩溃原因，都在同一个窗口里完成。

| 你想做的事 | MikanCL 里的做法 |
| :--- | :--- |
| 装一个原版游戏 | 「下载安装」选版本 → 自动下载客户端、依赖库、natives、3000+ 资源文件 → 主页双击启动 |
| 装基岩版（Bedrock） | 「基岩版」页按 MCAPPX 历史版本 / 微软商店正式版 / 预览版分类浏览，点「在浏览器下载」用内置 Edge 内核打开下载页，下载完成的 Appx 自动归档到本地，再一键安装、启动或卸载 |
| 加 Forge / Fabric / NeoForge / Quilt / LiteLoader | 同一页面选择加载器版本一键安装，自动匹配所需 Java 主版本 |
| 装整合包 | 拖进窗口或拖进「整合包」页 → 自动装基础版本 → 装加载器 → 刷入 overrides → 注册独立实例 |
| 找 Mod、整合包、资源包、光影包、材质包 | 「内容中心」双平台搜索，可按 MC 版本 / 加载器 / 材质分辨率过滤，一键装进实例或另存为 |
| 用中文找 Mod | 直接搜「机械动力」「物品管理器」等中文关键词，卡片自动显示中文译名 |
| 和朋友联机 | 「多人联机」用陶瓦（Terracotta）房间码组网，无需端口映射或公网 IP |
| 换 Java / 装 Java | 「Java 中心」一键下载 12 家发行版（新增清华 TUNA、华为云国内镜像），可只装轻量 JRE 或完整 JDK；安装方式支持「ZIP 便携版」（自动解压到 `data/runtime` 并写入用户 PATH）与「官方安装程序」（Temurin / Azul / Corretto 的 EXE / MSI 向导安装）；大文件自动多线程分段下载；「设置」里可手动添加 Java 路径、自动匹配或一键检测硬件推荐内存 |
| 看有哪些第三方依赖没装 | 「依赖补全」页按联机 / 登录 / 运行环境 / 加载器分类列出陶瓦、authlib-injector、Java 运行时、Mod 加载器与 Forbric，显示已安装 / 缺失 / 按需安装，缺失的可直接下载或前往对应页面 |
| 游戏缺文件 / 缺 Java | 「依赖补全」选版本 → 检查 Java、客户端 Jar、依赖库、资源与日志配置 → 弹窗确认后静默补全，任务全部进入下载中心 |
| 管账号与皮肤 | 微软正版设备码登录、皮肤站外置登录、离线账号，皮肤查询 / 上传 / 本地皮肤 |
| 从 PCL / HMCL 换过来 | 「设置 → 游戏」选择对方的配置目录 → 扫描并导入本启动器没有的版本，同时沿用对方的隔离、内存、JVM 参数等设置，mod 与存档仍留在原目录 |
| 排查「装上了但起不来」 | 启动预检 5 项拦截 + Mod 冲突检测 + 崩溃弹窗一键「去装对应 Java」「补全缺失文件」「修复版本」+ 启动卡死看门狗 + 界面日志与 `install_error.log` 落盘 |
| 不会装 / 装崩了想查教程 | 「教程中心」内置 8 篇 Markdown 攻略（Forge / Fabric / 光影 / 内存 / Mod 冲突 / Java / NBT / 离线皮肤），支持标题与正文搜索 |
| 想改世界种子 / 游戏模式 | 「NBT 编辑器」可视化读写 `level.dat` 与 `playerdata/*.dat`，双击改值、右键增删标签，首次保存自动备份 `.bak` |
| 多个版本互不干扰 | 4 种隔离模式（不隔离 / 仅模组 / 仅存档 / 全部隔离），整合包自动独立目录；主页「版本文件夹」可直接切换 / 新建本机任意目录作为新的版本分区 |
| 下载进度随手看 | 有下载任务时窗口右下角出现圆形下载按钮，左键直达下载中心，右键回到上一页 |
| 小屏幕 / 想调窗口 | 无边框窗口可拖四边四角自由缩放，默认 1080×680，内容放不下自动变滚轮滚动 |
| 自己画皮肤（含第二层遮罩） | 「皮肤工厂」像素级编辑 64×64 皮肤，画笔 / 橡皮 / 填充 / 取色 / 加亮 / 加深 / 直线 / 矩形 / 椭圆 / 喷枪十种工具，镜像对称、撤销重做、缩放与网格开关，按部位高亮 UV；最多 8 层多层绘画（新建 / 删除 / 排序 / 显隐，导出自动合并）；右侧 3D 模型支持选中部位后直接作画（底层 / 第二层可切换，左转 / 右转 / 复位视角按钮或滑块旋转、自动旋转），可保存到多皮肤库或一键应用到当前账号 |
| 挑世界种子不想进游戏 | 「世界种子」页输入种子 → 启动器调用本机 Java 执行内嵌 TerrainGen（与 Minecraft 相同的 ImprovedNoise 柏林噪声算法与参数）生成高度图 → 内联 WebGL 把地形渲染成 Minecraft 风格方块（体素柱：平顶 + 阶梯侧面），按钮 / 拖动旋转、缩放、平移、复位与自动旋转，支持尺寸 / 起伏调节与高度图导出 |
| 想要更炫的界面又怕卡 | 页面切换淡入淡出动画 + Windows DWM 毛玻璃背景，均在「设置 → 外观」中开关，关闭可降低 GPU / 内存占用 |

---

## 独家特色

以下是与常见启动器相比，MikanCL 做得更细的地方（全部为本项目自研实现）：

1. **内容中文译名（在线词典 + 本地词表）**
   卡片的英文标题会在后台逐张补上中文名（如 `Sodium → 钠`、`Iris → 虹膜光影`），译名来自 MC百科搜索结果的「中文名 (English Name)」配对，带 1 秒节流、磁盘缓存与失败负缓存；本地常用词表优先命中，缺词才联网，不阻塞搜索结果渲染。

2. **中文关键词搜索**
   直接输入中文即可检索：先查本地词表，未命中时回退在线词典把中文反查成英文项目名，再交给平台搜索接口。

3. **材质包独立分类**
   内容中心把「材质包」从「资源包」里拆出来，按 8x / 16x / 32x / 48x / 64x / 128x / 256x / 512x+ 分辨率分类检索，安装时落到实例的 `resourcepacks/`。

4. **统一的下载中心**
   原版安装、加载器、整合包、内容文件、Java 运行时、纯文件「另存为」全部是同一类任务：统一进度、速度、暂停 / 恢复 / 取消 / 重试 / 打开目录。

5. **「只下载不安装」系列**
   加载器安装器可另存为到指定目录、原版客户端 Jar 可单独下载，方便归档、离线部署或交给别的启动器使用。

6. **启动前五项预检**
   Java 主版本不匹配（可确认强启）、内存超过物理内存 70%、Mod 冲突、磁盘剩余 < 2GB、核显 + 光影组合，启动前直接说清楚问题出在哪。

7. **Mod 冲突检测**
   解析 `fabric.mod.json` / `META-INF/mods.toml` / `mcmod.info`，检测重复 modid、前置缺失、版本范围不满足，在 Mod 表格里标红并给出处理建议。

8. **整合包「直装包」兜底**
   没有清单但含 `mods/` 或 `config/` 的压缩包按直装包处理并推断 MC 版本；安装失败的部分 Mod 会写入 `missing_mods.txt`，不中断整体流程。

9. **双格式整合包备份**
   CurseForge 分享格式（`manifest.json` + `overrides`）与私有 `.mikan` 格式（`instance.json` + 内容）双向导入导出。

10. **多选启动队列**
    主页勾选多个版本按顺序依次启动，可中途停止，适合一次开多个客户端场景。

11. **界面适配小屏幕**
    无边框窗口可拖边缩放（默认 1080×680，最小 900×540），页面统一包在滚动容器里，窗口变矮就出滚轮而不是把内容压扁；筛选条件分两行、内容卡片按宽度自动 4 → 3 → 2 列重排。

12. **内置陶瓦联机**
    自动下载并校验官方发行包，房主创建房间、朋友输房间码加入，结束后一键关闭联机进程。

13. **五语言界面**
    简中 / 英 / 俄 / 法 / 日随设置切换；界面文案通过 Qt 翻译机制（`tr()` + `.qm`）加载，缺失翻译条目或 `.qm` 文件不存在时回退简体中文。

14. **单文件免安装**
    一个 `MikanCL.exe`，双击即用，配置与缓存写在 exe 同目录的 `data/`，换机直接拷走。

15. **PCL 风格用途分类**
    内容中心新增一排「优化 / 辅助 / 前置 / 装饰 / 科技 / 魔法 / 冒险 / 农业 / 世界生成」等分类按钮，点一下即按用途过滤；分类由本地词表 + 平台标签 + 中英文关键词共同判定，不额外依赖网络。

16. **主题色与自定义背景**
    内置森林绿 / 海蓝 / 暮紫 / 赤红 / 琥珀 / 青碧 6 套主题色，支持取色器自定义，切换即时生效；可指定任意图片作为启动器整体背景，按窗口比例等比铺满并居中裁切（不拉伸变形），侧边栏与标题栏自动半透明保证可读。

17. **插件扩展**
    `data/plugins/` 下放一个 `.py` 文件即可新增侧边栏页面，通过 `setup(api)` 使用启动器 API（版本、实例、内容搜索、下载、安装、后台线程等），无需改源码或重新打包；单个插件出错只记录日志，不影响启动器运行。

18. **内置教程 Wiki**
    启动器自带 8 篇 Markdown 教程（安装 Forge / Fabric、装光影、内存不足、Mod 冲突、Java 版本、NBT 编辑器、离线皮肤），中 / 英 / 俄 / 法 / 日五种语言各一套，首次运行按界面语言自动写入 `data/wiki/<语言代码>/`，可直接改文件扩充；教程中心支持按标题与正文搜索，外链交给系统浏览器，站内锚点就地跳转。

19. **启动动画**
    点启动后主页覆盖一层半透明遮罩，256×256 草方块按真实下载进度逐格填满，下方显示阶段文字与百分比，并从 255 条彩蛋启动词中随机挑一条固定展示（每次启动不重复轮播），进度完成或失败时 400ms 淡出；可在设置里关闭。

20. **NBT 编辑器**
    纯 Python 手写的 NBT 读写（13 种标签、自动识别 gzip、写回时严格保留原标签类型），配合树形编辑器可视化查看 `level.dat` / `playerdata`：双击改叶子值、右键增删标签、根节点保护、未保存提醒，首次保存自动在同目录生成 `.bak` 副本。

21. **账号头像即皮肤头部**
    主页卡片、侧边栏与账号详情不再用随机像素头像，而是直接从皮肤文件裁出「头部 + 帽子层」生成圆角头像；本地无皮肤时异步拉取 `skin_url` 补全，失败自动回退像素头像。

22. **浏览器用 Edge 内核，视频直接能看**
    内置浏览器默认托管系统自带的 Edge WebView2（完整 Chromium，自带 H.264/AAC），B 站视频在启动器里直接播放、支持全屏，不需要再切系统浏览器；Cookie 与登录态存在 `data/browser/webview2`，一次登录长期有效。只有系统缺失 WebView2 运行时时才回退到 QtWebEngine，并显示「视频可能无法播放」的提示条。

23. **崩溃一键修复**
    崩溃弹窗直接给修复入口：识别到 `UnsupportedClassVersionError` 时提供「去装 Java 21」（自动跳 Java 中心并预选发行版与主版本）；`libraries` / `assets` 缺失时提供「补全缺失文件」（复用 `ensure_version()` 只补缺口）；版本 JSON 损坏时在版本设置里提供「修复版本」（备份坏 JSON、从清单重拉写回，保留本地 jar 与库）。

24. **启动卡死看门狗**
    启动后 30 秒内既没检测到游戏窗口、进程又仍存活（或 CPU 时间始终为 0）时，日志写入「游戏可能卡在初始化」并弹出「强制结束并查看日志」按钮，复用窗口轮询结果，不额外开销。

25. **安装前磁盘空间预估**
    「安装所选版本」前按清单估算所需空间（客户端 + 依赖库 + 资源索引 objects 总大小），本地还没有版本 JSON 时在线估算，资源索引拉不到按 350MB 兜底；空间不足提前提示「约需 X GB，当前剩 Y GB」，而不是下到一半失败。

26. **版本目录一键清理与启动脚本导出**
    版本设置里可一键清理启动器日志（保留最近 3 个）、`versions/*/natives`、`*.tmp` / `*.part` 与 7 天前的 `crash-reports`；还能把当前版本导出为 `.bat` / `.ps1` 启动脚本（含完整命令行与工作目录），方便脱离启动器直接运行或排查是否是启动器问题。

27. **首次启动强制同意用户协议**
    未同意当前协议版本时，启动会先弹出协议确认框：全部条款以标签页并列展示（非官方声明、账号与登录、内容与下载、数据与运行风险、隐私、免责、协议变更、世界种子、界面效果、第三方模块等共 11 项，当前版本 v1.4），确认勾选框与「同意 / 不同意」按钮固定在标签页下方，未勾选时「同意」不可点击；点「不同意」直接退出，不进入主界面。同意后把版本号与时间写入 `data/config.json`，此后不再打扰；协议文档随程序内置 5 种语言。设置 → 关于页可随时重新查看全文，也可关闭「启动前提示」（协议版本升级时会再次要求确认）。

28. **更多细节**
    NBT 编辑器顶部搜索框可按 key 跳转并高亮匹配节点；皮肤预览补上披风层（64×64 皮肤的 `(0,0,10,16)` 区域，配合皮肤站 `cape_url` 一起贴）；多人联机房间码 26px 等宽大字并支持一键复制（2 秒内显示「已复制 ✓」）；教程中心支持「新建教程」，在 `data/wiki/<语言代码>/` 下创建空 Markdown 并调用系统编辑器打开，刷新后出现在列表里。

29. **依赖补全页（不可内置依赖统一管理）**
    侧边栏新增独立页面，集中列出所有因许可、体积或官方分发渠道限制而**不能随启动器内置**的第三方依赖：陶瓦联机、authlib-injector、Java 运行时、Forge / Fabric / NeoForge / Quilt 加载器与 Forbric。按「联机组件 / 登录组件 / 运行环境 / Mod 加载器」分类展示，标明版本、许可、安装路径与不可内置原因；可直接下载的缺失项显示「下载」，已安装显示「定位」，需官方安装器的显示「前往」对应页面。页面顶部固定展示免责声明，并同步写入《用户协议》第十一条。

30. **缺失依赖体检与询问式静默补全**
    选择任意已安装版本即可检查所需 Java、客户端 Jar、`libraries` 依赖库、`assets` 资源索引与对象、log4j 日志配置与版本文件；结果表格逐项标注「缺失 / 完整」及具体路径。发现缺失时先弹窗询问「是否现在自动补全」，确认后缺 Java 自动下载 Adoptium JRE、缺文件走 `ensure_version()` 只补缺口，任务全部进入下载中心，可暂停 / 取消 / 重试，补全过程不阻塞启动器继续使用。

31. **Java 轻量安装与硬件推荐内存**
    Java 中心新增「安装类型」选择：Adoptium Temurin 等发行版可只装 JRE（体积小、适合仅运行游戏），也可装完整 JDK；安装完成后自动按硬件推荐值写入最大内存。设置 → 通用页新增「自动检测」按钮，按物理内存与 CPU 核心数推荐最大内存并写回配置，避免手动填出超过物理内存 70% 的值。

32. **最多 5 个版本并发安装**
    下载安装页不再限制「一次只能安装一个版本」：每个版本拥有独立的安装任务、进度、暂停与取消，最多同时进行 5 个；达到上限后按钮禁用并提示，空出槽位后自动恢复。下载中心默认并发同步为 5，其余任务排队。

33. **离线皮肤下载后自动生效（按玩家名，不污染其他玩家）**
    离线账号的皮肤写好以后，新版本安装完成、整合包 / 直装包导入完成或实例恢复完成时，会自动把皮肤写入 `CustomSkinLoader/LocalSkin/skins/<玩家名>.png` 并合并 `CustomSkinLoader.json` 的 `loadlist`，再按该版本格式生成兜底资源包；资源包默认不启用，避免把服务器上其他默认皮肤玩家也变成这张皮肤。游戏目录缺少 `resourcepacks` 时会先自动创建，版本隔离为「全部」时同时写入 `versions/<版本>/game`。

34. **「皮肤包」标签页与全版本适配**
    侧边栏新增「皮肤包」：选择皮肤来源、目标玩家、Steve / Alex 手臂模型与目标版本后，可导出可分享的 `.zip` 皮肤包或直接安装到本机；导入他人皮肤包 / PNG 时会先询问手臂模型。版本适配：1.0–1.5.2 生成 `texturepacks` 纹理包（`pack.txt`），1.6.1–1.21.8 使用 `pack_format`（1 / 2 / 3 … 64）+ `supported_formats` 1–99，1.21.9+ 与 26.x（含 26.4 测试版）使用 `min_format` / `max_format`。生成方式沿用旧版可用皮肤包：同时写入 `textures/entity/steve.png`、`alex.png` 与 `entity/player/wide/steve.png`、`slim/alex.png` 两套路径，避免 1.19.3 / 1.20.2 等版本分界导致某条路径不生效；导出的皮肤包本身就是完整资源包，可直接放进 `resourcepacks`（或 1.5.2 及更早的 `texturepacks`）加载，也可由启动器导入。其他玩家安装同一个皮肤包并启用 CustomSkinLoader 后，就能在服务器按玩家名看到这张皮肤。页面提供「一键添加并覆盖旧皮肤包」：先清理主目录与版本隔离目录下所有旧 `MikanCL-*.zip`（含旧版 `MikanCL-离线皮肤.zip`）及 `options.txt` 中的启用项，再写入当前皮肤，避免旧包残留被误认为新皮肤已生效；普通安装新包时也会自动清理旧包。

35. **智能 JVM 参数（按 Java 版本与游戏版本自适应）**
    设置 → 通用页新增「智能 JVM 参数」开关（默认开启）。启动时按 Java 主版本、游戏版本与分配内存自动追加参数：1.21 及更早使用 Aikar 风格 G1GC（`G1NewSizePercent=30` / `G1MaxNewSizePercent=40`、`G1ReservePercent=20`、`InitiatingHeapOccupancyPercent=15`、`MaxGCPauseMillis=200`、`SurvivorRatio=32`、`MaxTenuringThreshold=1` 等），并关闭 `System.gc()` 显式回收与 perf 共享内存写入；堆 ≥ 4 GB 才启用 `AlwaysPreTouch`，≥ 12 GB 使用 16 MB Region，避免小堆启动变慢；26.x（官方要求 Java 25）改默认分代 ZGC（`-XX:+UseZGC`）。若用户已在额外 JVM 参数里指定 GC（G1 / ZGC / Shenandoah / Parallel / Serial / Epsilon，含 `-XX:-UseG1GC` 这类负向写法）或同名参数，则自动跳过对应项，不覆盖用户配置；Java 7 及更早只补 `MaxPermSize=256M`，Java 版本未知时不追加，防止参数不识别导致启动失败。分配内存超过物理内存 60% 时在启动日志与预检中提示换页风险。

36. **版本兼容启动参数（不受「智能 JVM」开关影响）**
    部分老版本与特殊版本需要额外参数，缺失时会直接崩溃，因此这些参数始终生效：1.12.2 及更早追加 `-Xss1M`（MC-129374 线程栈过小）与 `-Djava.util.Arrays.useLegacyMergeSort=true`（MC-61156 旧比较器排序崩溃）；旧版 Forge / 改过 jar 的整合包追加 `-Dfml.ignoreInvalidMinecraftCertificates=true`、`-Dfml.ignorePatchDiscrepancies=true`；旧版本被指定到 Java 9+ 时自动补 `--add-opens=java.base/java.lang` 等模块开放参数，避免 Forge 反射失败；Java 24+ 追加 `--enable-native-access=ALL-UNNAMED`，消除 LWJGL 受限 JNI 警告；macOS 上 1.13+ 追加 `-XstartOnFirstThread`（LWJGL3 要求主线程启动）。版本号识别覆盖远古版本（`a1.2.6` / `b1.7.3` / `c0.30` / `inf-` / `rd-` / `1.rv` / `2.0`）、愚人节版本与 26.4 / 26w.. 年份版本号，并按 1.21.9+ / 26.x 要求自动匹配 Java 21 / 25；启动日志会打印本次实际追加的版本兼容参数。

---

## 插件扩展

MikanCL 支持用单个 `.py` 文件扩展页面，无需修改启动器源码、无需重新打包。

- 用户插件目录：`data/plugins/*.py`（不存在时自动创建）
- 直接把 `.py` 文件拖进启动器窗口即可安装插件：文件会被复制到 `data/plugins/` 并立即加载，侧边栏出现新页面
- 插件加载失败不会影响启动器，错误会写进控制台日志并在状态栏提示

最小插件：

```python
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

PLUGIN_NAME = "我的插件"

def setup(api):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(QLabel(f"你好，{api.app_name} {api.app_version}"))
    api.add_page("我的插件", page)   # 侧边栏出现「我的插件」
```

### 插件 API 一览

| API | 说明 |
| :--- | :--- |
| `api.app_name` / `api.app_version` | 启动器名称与版本 |
| `api.config` | 当前 `Config` 对象，可直接读写字段（改完调用 `config.save()`） |
| `api.data_dir` / `api.plugins_dir` | 数据目录与插件目录 |
| `api.add_page(标题, QWidget)` | 新增侧边栏页面；页面可提供 `refresh()`，切页时自动调用 |
| `api.log(文本)` / `api.toast(文本)` | 写控制台日志 / 状态栏提示 |
| `api.navigate(名称)` | 跳转内置页：`home` `download` `downloads` `content` `modpack` `account` `control` `loaders` `multiplayer` `browser` `forbric` `java` `deps` `wiki` `bedrock` `skin_factory` `seed_terrain` `settings` |
| `api.open_url(网址)` / `api.open_folder(路径)` | 用内置浏览器打开网址 / 打开本地目录 |
| `api.list_instances()` | 实例列表（id / 名称 / MC 版本 / 加载器 / 路径 / 是否选中） |
| `api.list_versions(实例 id)` | 已安装版本列表（id / 类型 / 加载器 / 基础版本 / 路径） |
| `api.current_account()` | 当前账号（名称 / UUID / 类型） |
| `api.list_java()` | 已检测到的 Java |
| `api.search(...)` | 调用 Modrinth / CurseForge 搜索，返回纯字典列表 |
| `api.download_file(网址, 目标路径, 进度回调)` | 直接下载文件（同步，建议放进 `background`） |
| `api.install_version(MC 版本, 实例 id, 进度/完成/失败回调)` | 后台安装原版版本 |
| `api.background(函数, 完成回调, 失败回调)` | 把耗时任务放到后台线程，不卡界面 |

> 插件代码与启动器同权限运行，请只安装可信来源的插件。

---

## 设计参考

MikanCL 的界面布局、安装流水线与交互细节参考了以下启动器（**仅借鉴产品形态与流程思路，未复制其代码**）：

| 参考对象 | 借鉴的部分 |
| :--- | :--- |
| **PCL2（Plain Craft Launcher 2）** | 左侧导航 + 右侧卡片的整体布局、版本卡片与启动按钮的交互、整合包「先装版本再装加载器最后刷内容」的安装顺序、下载页的信息密度 |
| **HMCL（Hello Minecraft! Launcher）** | 实例 / 版本隔离目录的组织方式、Java 自动匹配策略、外置登录（authlib-injector）集成思路、下载源与镜像的概念、陶瓦联机的使用方式 |
| **Prism Launcher / MultiMC** | 「一个实例 = 一套独立目录」的实例模型、实例级 Java 与内存覆盖配置的概念 |
| **Minecraft 官方启动器** | 版本 JSON、资源索引（asset index）、natives 解压等官方安装规范 |
| **Modrinth App** | 内容中心的搜索 / 筛选 / 一键安装到实例的交互形态 |

---

## 核心功能特性

### 基础功能

- **版本管理**：原版版本下载与安装、版本列表双击启动、最多同时安装 5 个版本、版本重命名/删除
- **版本分类**：正式版（草方块）、测试版（命令方块）、远古版（原石）、愚人节（TNT）四类标签，默认只显示正式版，点哪个标签加载哪一类；顶部常驻「最新正式版 / 最新测试版」卡片，可一键进入详情；所有版本图标均为自绘像素图
- **下载中心**：独立任务页，统一管理原版安装、加载器安装、整合包、内容下载、Java 下载、纯文件下载、下载加速等任务，默认最多 5 个任务并发、其余排队，支持暂停 / 恢复 / 取消 / 重试 / 打开目录
- **下载加速**：侧边栏独立页，把任意直链（可整段粘贴，自动提取 http/https 链接）交给启动器高线程分段下载；线程数单独可调（1–328，默认至少 64），任务同样出现在下载中心，可暂停、取消与失败重试
- **版本隔离**：不隔离、仅隔离模组、仅隔离存档、全部隔离（独立游戏目录）四种模式，可按版本单独覆盖
- **数据目录**：支持添加多个 `.minecraft` 目录，通过侧边栏下拉框快速切换
- **从 PCL / HMCL 导入**：设置 → 游戏页选择对方的配置目录（含 `.minecraft` 的那一层，也可直接选 `.minecraft`），扫描后勾选要导入的版本；只导入本启动器没有的版本，并读取 PCL `Setup.ini` / HMCL `hmclversion.cfg` / `.hmcl.json` 中的隔离、内存、JVM 参数等设置，实例直接指向原游戏目录，mod 与存档无需搬移
- **多线程下载**：线程数可配置（1–328，默认 16），所有下载（版本安装、Java、内容文件、下载加速、基岩版等）共用一个 328 线程的全局预算，不会因多个任务同时并发把线程数打爆；单个大文件按 `文件大小 / 1 MB` 切段，段数上限由全局预算与线程数设置决定，服务器不支持 Range 时自动回退单流
- **日志与诊断**：界面日志同步落盘 `data/logs/launcher.log`（5MB × 3 轮转）；安装失败时额外写入 `data/logs/install_error.log` 并自动复制日志到剪贴板
- **单实例保护**：基于 QSharedMemory，避免两个进程同时读写配置与浏览器缓存

### 启动与运行

- **启动预检（Preflight）**：启动前检查 Java 版本是否匹配所需主版本、分配内存是否 ≤ 物理内存 70%、`mods/` 是否存在冲突、磁盘剩余空间是否 > 2GB、集成显卡 + 光影包组合是否警告；关键项失败可弹窗确认后仍强制启动
- **多选启动**：在主页勾选多个版本后按顺序依次启动，支持中途停止队列
- **进程优先级**：启动游戏时可设置进程优先级（低 / 正常 / 高 / 实时）
- **启动后行为**：隐藏启动器、关闭启动器、保持打开等可选；可配置游戏退出后是否保留启动器
- **启动动画**：启动时草方块按进度逐格填充、随机彩蛋词条、淡入淡出，可在设置中关闭
- **自动连接服务器**：启动时自动进入配置好的服务器地址
- **代理支持**：HTTP 代理可同时应用于下载与游戏 JVM 参数
- **内存自动分配**：设置 → 通用页「自动检测」按物理内存与 CPU 逻辑核心数推荐最大内存并写回配置；Java 中心安装完成后也自动应用推荐值，避免超过物理内存 70%
- **智能 JVM 参数**：设置 → 通用页开关（默认开启）按 Java 版本、游戏版本与堆大小自动追加调优参数（1.21 及更早 G1GC，26.x 分代 ZGC），已在额外参数中指定 GC / 同名项时自动跳过；Java 7 及更早只补 PermGen；分配超过物理内存 60% 时提示换页风险
- **预加载 JVM（实验性，默认关闭）**：开启后每次启动启动器都会在后台用所选 Java 执行一次 `-version` 预热，把核心类与本地库加载进系统缓存，随后启动游戏可快一些；Java 版本在设置页自行选择（默认自动跟随启动时选中的 Java），预热失败只写日志、不影响启动器使用
- **版本兼容参数**：1.12.2 及更早自动加 `-Xss1M` 与 legacy 排序参数，旧版 Forge 加 fml 校验放宽参数，旧版本跑 Java 9+ 自动补 `--add-opens`，Java 24+ 自动加 `--enable-native-access`，macOS 1.13+ 自动加 `-XstartOnFirstThread`
- **系统托盘**：最小化到托盘、托盘快捷启动

### 下载与内容生态

- **原版安装**：按版本 JSON 安装客户端 Jar、54+ 依赖库、natives 解压、资源索引与 3000+ 资源文件
- **Mod 加载器**：Forge、NeoForge、Fabric、Quilt、LiteLoader 一键安装，自动选择对应 Java 主版本，安装器输出实时回显
- **加载器源文件下载**：独立「加载器源文件（另存为）」卡片，按 MC 版本 + 加载器版本直接下载安装器 Jar 到指定目录，不安装到游戏
- **仅下载客户端 Jar**：只保存某个版本的原版客户端 Jar，便于归档或手动部署
- **内容中心**：Modrinth 与 CurseForge 双平台搜索与浏览，覆盖 Mod、整合包、资源包、光影包；按 MC 版本与加载器过滤，展示下载量与简介，详情页懒加载 Mod 列表
- **一键安装到实例**：内容下载完成后自动投放到对应实例的 `mods/`、`resourcepacks/`、`shaderpacks/`
- **另存为**：Mod / 整合包 / 资源包 / 光影包 / 原版客户端 Jar 均支持「另存为到指定文件夹」，以纯下载任务的形式出现在下载中心
- **Mod 冲突检测**：扫描每个 Jar 的 `fabric.mod.json`、`META-INF/mods.toml`、`mcmod.info`，解析 modid、版本与依赖；检测重复 modid、版本范围不满足、前置缺失，在版本设置的 Mod 表格中红色标记并给出「禁用其中一个」建议

### 整合包

- **导入方式**：拖入窗口、拖入整合包页、从本地文件选择
- **安装流程（参考 PCL / HMCL）**：先完整安装整合包对应的 Minecraft 版本（客户端、依赖库、natives、资源文件）→ 再安装所需加载器 → 确认版本 JSON 有效 → 最后刷入整合包内容（`mods/`、`config/`、`resourcepacks/`、`shaderpacks/`、`saves/` 等 overrides）
- **多源重试**：版本安装、加载器安装、单文件下载均自带重试（连接类异常重试 3 次，HTTP 错误不重试）
- **容错**：部分 Mod 下载失败不中断整体安装，失败清单写入 `missing_mods.txt`；支持嵌套目录结构的整合包
- **直装包兜底**：无清单但包含 `mods/` 或 `config/` 的压缩包按「直装包」处理，自动推断 MC 版本
- **双格式备份**：支持 CurseForge 分享格式（manifest.json + overrides）与私有 `.mikan` 备份格式（`instance.json` + 内容），可导入、可导出；也可单独「导出整合包源文件」
- **版本设置里的「整合包」侧边栏**：沿用 `.mikan` 包格式，可把当前版本导出为整合包，也可把 `.mikan` / CF / Modrinth 整合包刷入当前实例——识别 `overrides/`、`client-overrides/` 前缀与根目录直接放置的 `mods`、`config`、`resourcepacks`、`shaderpacks` 等目录（走版本隔离目录），后台线程执行并显示进度，覆盖同名文件前会统计并询问确认，不额外新建实例
- **实例注册**：安装成功后写入 `instance.json`、自动选中实例、刷新主页版本列表

### 基岩版（Bedrock）

- **分类版本列表**：与 Java 版一致的卡片式页面，左侧分类下拉框提供「历史版本（MCAPPX）」「微软商店 · 正式版」「微软商店 · 预览版」三类来源，配合架构（自动 / x64 / x86 / arm）与关键字搜索过滤，表格展示版本、架构、大小、发布日期、来源与状态
- **离线目录**：内置 `mc_launcher/data/bedrock_catalog.json`（随 exe 打包），收录 32 个主版本、82 条具体发行版（含 1.8、1.8.1 等历史版本），记录包 ID、各架构体积、SHA256 与 mcappx 直链
- **浏览器下载**：表格中每个版本提供「在浏览器下载」，点击后切到内置浏览器（优先 Edge / WebView2 内核）打开该版本下载页，由 Edge 的下载能力完成保存（内嵌下载气泡可查看进度），不再依赖启动器内置的离线直链
- **下载自动归档**：监听系统「下载」文件夹，新出现的 `.appx` / `.msix` / `.appxbundle` / `.msixbundle` 会延迟 1.5 秒后自动归档到基岩版下载目录，并提示可「从本地安装」
- **一键安装**：下载完成后点击「从本地安装」选择安装包，调用 `Add-AppxPackage -ForceUpdateFromAnyVersion` 安装（微软签名包无需开发者模式），首次失败会自动补装 VCLibs 等运行库依赖后重试
- **启动与卸载**：安装完成后页面顶部显示已安装版本、架构与安装位置，按钮「启动基岩版」通过 `explorer.exe shell:AppsFolder\<AUMID>` 拉起游戏（AUMID 由 `Get-AppxPackageManifest` 解析，失败回退官方标识），并可一键卸载；下载目录可一键打开
- **下载中心集成**：基岩版本地安装任务统一进入下载中心，支持暂停、取消、重试与打开目录，界面按版本与架构展示当前阶段
- **与 Java 版统一入口**：下载页顶部提供「基岩版」入口卡片；启动页版本列表把已安装基岩版作为独立条目置顶并标注「基岩版」徽标，选中后可直接启动（无需 Java），并参与版本统计与搜索

### 账号与皮肤

- **微软正版登录**：设备码（Device Code）OAuth 流程，自动刷新令牌
- **外置登录**：基于 authlib-injector，支持任意皮肤站 / 外置登录服务器；自动下载并注入 `authlib-injector.jar`
- **离线账号**：自定义玩家名，生成离线 UUID
- **皮肤管理**：正版皮肤查询、按用户名查找皮肤、上传皮肤；离线皮肤支持 Steve / Alex 手臂模型，导入时询问模型并保存到账号，写入 `CustomSkinLoader/LocalSkin/skins/<玩家名>.png` 并合并 `loadlist`；下载安装新版本、导入整合包 / 直装包或恢复实例完成后按该版本格式自动打包，无需再启动一次；游戏内显示需搭配 CustomSkinLoader Mod
- **皮肤包**：独立「皮肤包」标签页，可按目标玩家 + 手臂模型 + 游戏版本导出可分享的 `.zip`，也可直接安装到本机或导入他人皮肤包；「一键添加并覆盖旧皮肤包」会先清理旧的 `MikanCL-*.zip` 与 `options.txt` 启用项再写入，避免旧包残留误导；服务器上只影响指定玩家，其他玩家外观不变
- **皮肤头像**：主页卡片、侧边栏、账号详情直接使用皮肤「头部 + 帽子层」生成圆角头像，无本地皮肤时异步拉取 `skin_url`，失败回退像素头像

### 扩展与实验性功能

- **内置浏览器**：优先用 ctypes 托管系统 Edge WebView2 内核（完整 Chromium，H.264/AAC 齐全），B 站等站点视频直接在启动器内播放并支持全屏，多标签、弹窗转标签、Ctrl+T / Ctrl+W 快捷键齐备；用户数据目录固定在 `data/browser/webview2`，Cookie 与登录态自动持久化。系统缺失 WebView2 运行时（Windows 10/11 一般已预装）时自动回退到 QtWebEngine，并亮出「视频可能无法播放 / 用系统浏览器打开」提示条
- **教程中心**：内置 8 篇 Markdown 攻略，左侧目录 + 右侧渲染，支持搜索、内部锚点与外链跳转，可从教程页直接打开 NBT 编辑器
- **NBT 编辑器**：纯手写 NBT 读写（13 种标签、gzip 自动识别、类型完整保留），树形查看 / 编辑 `level.dat` 与 `playerdata`，右键增删标签，首次保存自动生成 `.bak`
- **Java 中心**：Adoptium Temurin、清华 TUNA 镜像（Temurin）、华为云 OpenJDK 镜像、Microsoft OpenJDK、Azul Zulu、Amazon Corretto、Alibaba Dragonwell、Tencent Kona、BellSoft Liberica、IBM Semeru、SAP SapMachine、GraalVM Community 共 12 个发行版，按主版本下载安装；标有「国内镜像」的发行版国内下载更快；支持选择「JRE（仅运行）」或「JDK（含开发工具）」，JRE 体积更小；大文件自动启用多线程分段下载（段数按 `文件大小 / 1 MB` 计算，实际并发受全局 328 线程预算与设置里的线程数约束，服务器不支持 Range 时自动退回单流），自动解压到 `data/` 并在设置中选中，安装完成后按硬件推荐值自动写入最大内存
- **Java 检测与手动添加**：自动扫描 JAVA_HOME、注册表、各发行版安装目录、启动器自带运行时、`.gradle/jdks`、`PATH` 逐项目录，并解析 `shutil.which` 与 Windows `where java` / `where javaw` 的全部输出（统一规范化去重、只保留真实存在的文件）；检测结果与历史记录合并持久化，刷新时不会再出现「这次有、下次没了」；「设置 → 通用 → Java 运行时」新增「手动添加…」，可选择 `javaw.exe` / `java.exe` 或直接填写安装目录，添加后会长期记住
- **Forbric 引导式安装**：实验性 Fabric/Forge/NeoForge 三合一加载器，通过 GitHub Releases 自动获取最新安装器与 `Forbric-Installer.bat`，用 Java 21 拉起官方 GUI，后台轮询 `versions/26.2-forbric/26.2-forbric.json`，生成后自动注册实例
- **预加载 JVM（实验性，默认关闭）**：设置 → 通用页开关 + 「预加载的 Java」下拉（默认自动跟随启动时选中的 Java）。开启后每次启动启动器都会在后台用所选 Java 跑一次 `-Xshare:auto -XX:+UseSerialGC -version`，把核心类与本地库预热进系统缓存；失败只写日志，不弹窗、不阻塞界面，退出时最多等预热线程 2 秒

### 界面与联机

- **多语言界面**：简体中文 / English / Русский / Français / 日本語，设置内即时切换
- **自由缩放窗口**：无边框窗口支持拖四边四角改大小（默认 1080×680，最小 900×540），小屏按可用区域自动收缩
- **滚轮自适应版面**：所有页面包在滚动容器中，窗口变矮时纵向滚动而不是压扁内容；侧边栏导航、筛选条件、内容卡片列数都会随宽度调整
- **陶瓦联机**：内置 Terracotta（房间码 P2P 组网），自动下载 / 校验官方发行包，创建房间、加入房间、复制房间码、结束联机
- **中文内容检索**：本地词表 + MC百科在线词典，支持中文名展示与中文关键词搜索
- **系统托盘与单实例**：可最小化到托盘，重复启动会提示而不是开两个进程
- **下载加速**：侧边栏独立页，把任意直链（或整段网页文本，自动提取 http/https 链接并去重）丢给启动器的高线程分段下载器；单任务线程数独立可调（1–328，默认至少 64），保存目录可自选，任务统一进入下载中心，支持暂停 / 恢复 / 取消 / 失败重试与断点续传；同名文件自动追加序号，不会覆盖已有文件或与进行中的任务写同一个路径
- **启动速度**：页面底色改由全局样式表统一绘制，不再为每个滚动页单独 `setStyleSheet`；外观刷新增加状态缓存，背景图 / 毛玻璃没变时直接跳过整窗样式重算。离屏实测主窗口构建从约 5.7 秒降到约 3.5 秒

### 依赖补全与第三方组件

- **不可内置依赖清单**：「依赖补全」页按「联机组件 / 登录组件 / 运行环境 / Mod 加载器」分类列出陶瓦联机（Terracotta）、authlib-injector、Java 运行时、Forge / Fabric / NeoForge / Quilt 加载器与 Forbric，标明版本、许可、安装路径与不可内置原因
- **状态一目了然**：已安装项显示绿色「已安装」并可「定位」打开目录；缺失项显示红色「缺失」并可「下载」；加载器这类需按版本使用官方安装器的项显示「按需安装」并可「前往」对应页面
- **第三方模块下载**：陶瓦联机与 authlib-injector 由本页直接下载安装，任务登记到下载中心，与普通下载一致支持暂停 / 取消 / 失败重试
- **缺失依赖体检**：选择已安装版本后一键检查所需 Java、客户端 Jar、`libraries` 依赖库、`assets` 资源索引与对象、log4j 日志配置与版本文件，表格逐项标注状态与具体路径
- **询问式静默补全**：检测到缺失时弹窗询问是否立即补全；确认后缺 Java 下载 Adoptium JRE、缺文件只补缺口，全部任务显示在下载中心，补全期间可继续使用启动器
- **免责声明与协议**：依赖页顶部展示第三方模块免责声明，并同步写入《用户协议 v1.4》第十一条（5 种语言），明确第三方模块与 MikanCL 无隶属 / 授权 / 担保关系，提供入口仅为便利
- **功能开关**：设置 → 功能开关中的「依赖补全」可隐藏该页；关闭后不创建页面、不启动后台任务

---

## 关键技术详解

### 1. 整合包安装流水线

**问题**：早期版本直接解压 overrides，依赖「游戏目录里已存在对应版本」，导致「装不上 / 找不到版本」。

**方案**（对齐 PCL / HMCL 的行为）：

```
安装基础版本 → 安装加载器 → 校验版本 JSON → 刷入整合包内容 → 注册实例
    ↓                ↓              ↓                  ↓
 3 次重试          3 次重试     失败则回退原版 / 报错    部分失败写清单
```

| 阶段 | 说明 |
| :--- | :--- |
| 安装基础版本 | 调用 `GameInstaller.install_version()`，完整下载客户端 Jar、依赖库、natives、资源文件 |
| 安装加载器 | `install_loader()` 安装 Forge / NeoForge / Fabric / Quilt / LiteLoader |
| 校验版本 JSON | 加载器未生成有效 JSON 时，回退到原版版本 JSON；仍失败则抛出「加载器安装失败，未生成有效的版本 JSON」 |
| 刷入内容 | 解析 manifest / instance.json，将 overrides 与文件清单刷入实例目录；单个文件失败不中断 |
| 注册实例 | 写入 `instance.json`、`config.add_instance()`、选中实例并刷新主页 |

**取消语义**：用户取消属于正常流程（`net.Cancelled`），不写 `install_error.log`、不复制剪贴板、不弹错误框，下载中心任务状态显示「已取消」；已下载的 `.part` 文件保留，重新导入可断点续传。

### 2. 断点续传与多源下载

- **临时文件**：下载写入 `目标文件.part`，完成后原子改名
- **Range 续传**：对已有 `.part` 发起 `Range: bytes=N-` 请求，服务端返回 `206` 时追加写入；返回 `200` 时降级为全量重新下载
- **重试策略**：每个候选地址最多 3 次尝试，仅对连接类异常（10053 / 10054 / 超时）重试并短暂等待，HTTP 4xx/5xx 直接切下一个源
- **镜像改写**：`rewrite_url()` 按下载源配置把 Mojang 域名（`piston-*`、`resources.download.minecraft.net`、`libraries.minecraft.net`）改写为 BMCLAPI 镜像路径
- **暂停与恢复**：任务级 `threading.Event` 控制，暂停时不销毁连接配额，恢复后继续；取消时保留未完成分片
- **并发文件锁**：多版本同时安装时，同一个库 / 资源文件可能被多个 worker 请求；`Http.download()` 按目标路径取 `RLock` 后再复查文件是否完整，避免重复下载与 `.part` 写冲突

### 3. Mod 元数据扫描与冲突检测

```python
from mc_launcher.content import scan_mod_metadata, detect_mod_conflicts

metadata = scan_mod_metadata(instance_dir / "mods")   # {Path: {modid, name, version, loader, depends}}
issues = detect_mod_conflicts(metadata)               # [{kind, modid, files, detail}]
```

| 检测项 | 常量 | 说明 |
| :--- | :--- | :--- |
| 重复 modid | `duplicate_modid` | 两个 Jar 声明了相同 modid（通常是同一 Mod 的重复版本） |
| 前置缺失 | `missing_dependency` | 依赖的 modid 在 `mods/` 内不存在（可区分必需 / 可选） |
| 版本不匹配 | `version_mismatch` | 依赖声明的版本范围不满足当前安装版本（semver 范围解析） |

在「版本设置 → Mod 管理」中，`_reload_files("mods")` 完成后对冲突项标红并追加 tooltip，页面顶部给出红色汇总提示与「禁用其中一个」建议。

### 4. 启动预检（Preflight）

`LaunchWorker.run()` 开头执行 `_preflight()`，结果通过日志信号输出，拦截项弹窗确认：

| 检查项 | 判定 | 处理 |
| :--- | :--- | :--- |
| Java 主版本 | 版本 JSON 声明的 Java 与当前 Java 不一致 | 阻断（可确认后强启） |
| 内存上限 | 分配内存 > 物理内存 × 70% | 警告 |
| Mod 冲突 | 存在重复 modid / 前置缺失 | 警告 |
| 磁盘空间 | 游戏目录所在盘剩余 < 2GB | 警告 |
| 集成显卡 + 光影 | 检测到核显且实例存在 `shaderpacks/` 内容 | 警告 |

### 5. 版本隔离与目录重定向

| 模式 | 常量 | 行为 |
| :--- | :--- | :--- |
| 不隔离 | `none` | 所有版本共用 `.minecraft` 下的模组与存档 |
| 仅隔离模组 | `mods` | 为版本建立独立 `mods/`，其他共享 |
| 仅隔离存档 | `saves` | 为版本建立独立 `saves/`，其他共享 |
| 全部隔离 | `all` | 为版本建立独立游戏目录（`data/instances/<实例>`） |

隔离目录按需创建：未隔离的子目录通过目录联接 / 复制回共享目录，切换模式时自动断开旧的链接。

### 6. Forbric 引导式安装

- **版本绑定**：`FORBRIC_SUPPORTED_MC = "26.2"`，实例绑定的 MC 版本不受支持时禁用安装按钮并标红说明
- **获取安装器**：请求 `https://api.github.com/repos/Ray-T-r/Minecraft-Forbric-mod-loader/releases/latest`，从 `assets` 中匹配最新的 `forbric-kernel-installer-*.jar` 与 `Forbric-Installer.bat`
- **拉起 GUI**：`subprocess.Popen([java, "-jar", jar])`，不加 `CREATE_NO_WINDOW`（否则官方 GUI 无法弹出），输出重定向到日志
- **结果监控**：`QThread` 每 2 秒检查 `versions/26.2-forbric/26.2-forbric.json`，超时 30 分钟；检测到即注册实例并提示成功

### 7. Java 下载与 Java 中心

- **扫描**：注册表 + 常见安装路径（`Program Files\Java`、`Program Files\Eclipse Adoptium`、`%LOCALAPPDATA%\Programs` 等）+ 启动器自管目录 + `JAVA_HOME` + `PATH` 逐项目录 + `where java` / `where javaw` 输出 + `shutil.which`，只要系统的 `java` 能在命令行跑起来就能被找到
- **预加载（实验性）**：设置里开启后，每次启动启动器都会用所选 Java 执行 `-Xshare:auto -version` 预热一次 JVM；失败只记录日志，不弹窗、不阻塞界面
- **匹配**：`pick_java()` 优先完全匹配所需主版本，其次取高于需求的最近版本，最后回退任意可用 Java
- **下载**：`download_java()` 支持 `on_bytes` 进度回调、取消与暂停，解压后返回可执行路径；Java 中心统一登记到下载中心，可暂停 / 取消 / 重试
- **安装类型**：Java 中心可切换「JRE / JDK」，请求 key 形如 `temurin:21:jre`；Adoptium 按 `image_type` 拉取 JRE 包，部分只提供 JDK 的发行版会自动回退
- **内存推荐**：`hardware.py` 读取物理内存与 CPU 逻辑核心数，按「物理内存约 1/4、上限随内存增长」的规则给出最大内存建议；Java 安装完成后与设置页「自动检测」按钮共用同一套推荐逻辑

### 8. 单实例、落盘与退出

- `QSharedMemory` 实现单实例；重复启动时提示已运行
- 配置采用防抖写盘，退出时通过 `QApplication.aboutToQuit` 绑定 `final_save()` 强制落盘 `config.json` 与 `accounts.json`，避免数据丢失
- 打包版启动时将工作目录重定向到 exe 所在目录，`data/` 在同目录自动生成
- 退出阶段跳过 Qt/Python 析构，避免后台线程尚未收尾时崩溃

### 9. 内容中文译名与中文搜索

数据来源为 MC百科（`search.mcmod.cn`）的搜索结果，标题形如 `[缩写] 中文名 (English Name)`，解析后得到「英文名 → 中文名」配对。

| 环节 | 实现 |
| :--- | :--- |
| 请求 | 浏览器 UA + `Referer: https://www.mcmod.cn/`（应用 UA 会被拦截返回空页），单次超时 8 秒 |
| 节流 | 进程内串行，两次请求间隔 ≥ 1 秒；并发抓取会触发站点限流 |
| 解析 | 按 `class="result-item"` 分块，取 `<div class="body">` 之前的标题链接，去掉 `[XX]` 缩写前缀 |
| 匹配 | 只接受英文名归一化后**完全一致**的条目，避免把「XX GTNH 版」误当成本体 |
| 缓存 | `data/cache/cn_names.json`（`names` + `queries` 两段），原子写入；未命中 / 失败分别写入 30 分钟与 10 分钟负缓存 |
| 展示 | 搜索结果返回后由 `TranslateWorker` 后台逐张补名，命中即刷新卡片，不阻塞列表渲染 |
| 搜索 | `translate_query()` 本地词表优先，未命中再走在线词典，把中文反查为英文项目名 |

### 10. 基岩版安装与启动链路

基岩版走的是「UWP 安装包」路径，与 Java 版完全不同：

| 环节 | 实现 |
| :--- | :--- |
| 版本目录 | 内置 `mc_launcher/data/bedrock_catalog.json`（32 个主版本 / 82 条发行版），标记包 ID、架构、体积与直链；1.8.1 另含 SHA256 |
| 商店直链 | `POST store.rg-adguard.net/api/GetFiles`（`type=url`、`ring=Retail/RP`），正则解析 `.appx` 链接；链接中的 `&amp;` 必须 `html.unescape()`，否则 CDN 返回 403 |
| 下载 | 自研 `MultiPartDownload`：Range 探测真实总大小 → 按 2 MB 最小分段切分 → 线程池并发写入 `.partN` → 合并 → SHA256/SHA1 校验；已存在分片参与续传，进度回调传绝对字节数保证单调 |
| 安装 | `Add-AppxPackage -Path ... -ForceUpdateFromAnyVersion -ForceApplicationShutdown`，微软签名包无需开发者模式；PowerShell 输出交给独立线程 + 队列读取，标记 `INSTALL_OK` 出现后额外等待收尾，避免超时误杀 |
| 依赖 | 首次安装失败时自动从商店清单取 VCLibs 等依赖补装并重试一次（本地安装包同样适用） |
| 启动 | `Get-AppxPackageManifest` 解析 `包族名!应用Id` → `explorer.exe shell:AppsFolder\<AUMID>`；20 秒后检查主进程是否真的起来 |
| 失败诊断 | 读取 `Microsoft-Windows-TWinUI/Operational` 的激活失败事件（Id 5961），把 `0x803F8001`（无授权）等 HRESULT 译成可读提示 |

### 11. 缺失依赖扫描与静默补全

依赖体检全部集中在 `mc_launcher/dependencies.py`，页面只负责展示与提交下载任务：

| 环节 | 实现 |
| :--- | :--- |
| 版本读取 | `load_version(game_dir, version_id)` 合并继承链；失败返回 `kind="version"`，不弹补全 |
| Java | `required_java()` 取版本 JSON 的 `javaVersion.majorVersion`（缺省 21），`AppContext.javas` 中没有任何 `major >= required` 即缺失 |
| 客户端 | `client_jar_path()` 指向 `versions/<id>/<id>.jar`，文件不存在且 JSON 含 `downloads.client.url` 时记为缺失 |
| 依赖库 | 逐个检查 `merged.libraries` 中带 URL 的 `path` 是否存在于 `config.libraries_path`，缺多个时聚合为一行并给出示例路径 |
| 资源 | 读取 `assets/indexes/<assets_id>.json` 的 `objects`，逐个检查 `objects/<sha1[:2]>/<sha1>`；索引文件本身缺失也单独上报 |
| 日志配置 | `logging_file_path()` 对应的 log4j XML 不存在且版本声明了 logging 时记为缺失 |

补全流程：

1. `CheckWorker` 在后台线程完成扫描，结果表格逐项列出缺失项；全部完整时显示「完整」
2. 有缺失则弹出 `QMessageBox.question`：「是否现在自动补全？补全任务会显示在下载中心，可暂停或取消」
3. 用户确认后按类型拆分任务：Java 缺失 → `JavaInstallWorker`（Adoptium JRE，落盘 `data/runtime`）；文件缺失 → `VersionRepairWorker`（`GameInstaller.ensure_version()` 只补缺口）
4. 两类任务都走 `DownloadManager.submit()`，与普通下载共享排队、暂停 / 取消 / 重试与进度展示
5. 完成后刷新 `AppContext.javas` 与版本列表，提示可重新检查或直接启动；失败时任务标记为失败并写入日志

> 扫描只读文件系统，不联网、不修改游戏目录；只有用户确认补全后才会发起下载。

---

## 内部接口参考

### 核心模块

| 模块 | 职责 |
| :--- | :--- |
| `mc_launcher/config.py` | 全局路径常量、下载源定义、`Config` 读写、实例（Instance）与版本设置、隔离策略 |
| `mc_launcher/net.py` | `Http` 请求与下载（Range / `.part` / 重试）、`SourceManager` 版本清单与镜像改写、代理 |
| `mc_launcher/installer.py` | `GameInstaller`：版本 JSON 解析、类库与 natives、资源索引与资源文件批量下载 |
| `mc_launcher/modloader.py` | 加载器版本查询与安装（Forge / NeoForge / Fabric / Quilt / LiteLoader）、`java_for_mc()` |
| `mc_launcher/launcher.py` | 启动命令拼装、natives 准备、隔离目录处理、authlib-injector 注入、进程启动 |
| `mc_launcher/jvm.py` | 智能 JVM 参数：按 Java 版本 / 游戏版本 / 堆大小生成 G1GC 或 26.x 分代 ZGC 参数，并生成旧版兼容参数（`-Xss1M`、legacy 排序、旧版 Forge 校验、Java 9+ `--add-opens`、Java 24+ `--enable-native-access`、macOS `-XstartOnFirstThread`），检测用户 GC 与同名参数、内存超配警告 |
| `mc_launcher/auth.py` | 账号存储、微软设备码登录、外置登录、皮肤查询 / 上传 / 本地皮肤 |
| `mc_launcher/skinpack.py` | 皮肤包：按玩家名写入 LocalSkin、合并 CustomSkinLoader 配置、全版本资源包 / 纹理包格式适配 |
| `mc_launcher/content.py` | Modrinth / CurseForge 客户端、整合包解析与安装、Mod 元数据扫描与冲突检测 |
| `mc_launcher/downloads.py` | 下载中心任务模型与调度（并发上限、暂停 / 恢复 / 取消 / 重试） |
| `mc_launcher/java.py` | Java 探测、版本匹配、Java 下载与解压（支持 JRE / JDK 安装类型） |
| `mc_launcher/dependencies.py` | 不可内置第三方依赖清单（联机 / 登录 / Java 运行时 / 加载器）、游戏缺失依赖扫描（Java / 客户端 / 依赖库 / 资源 / 日志） |
| `mc_launcher/forbric.py` | Forbric 安装器获取 / 下载 / 启动、版本结果轮询 |
| `mc_launcher/bedrock.py` | 基岩版：离线版本目录加载、微软商店文件接口、多线程分块下载、`Add-AppxPackage` 安装、AUMID 解析与启动 / 卸载 |
| `mc_launcher/terrain_java.py` | 内嵌 TerrainGen.java（与 Minecraft 相同的 ImprovedNoise 柏林噪声 + persistence 0.5 / lacunarity 2 多层叠加），自动 `javac` 编译或 Java 11+ 单文件启动，输出高度图与彩色 PNG |
| `mc_launcher/nbt.py` | 最小 NBT 读写（13 种标签 / gzip 自动识别），含保留标签类型的 typed 变体 |
| `mc_launcher/terracotta.py` | 陶瓦联机发行包下载校验、进程管理与本地 HTTP API |
| `mc_launcher/cn_source.py` | MC百科译名查询、节流与 `cn_names.json` 缓存（可选在线词典） |
| `mc_launcher/mod_cn.py` | 本地中文词表、用途分类（`categories_for()`）、标题归一化、`cn_name()` / `translate_query()` |
| `mc_launcher/plugins.py` | 插件加载（`data/plugins/*.py`）与插件 API（页面、实例、搜索、下载、后台线程） |
| `mc_launcher/i18n.py` | 五语言翻译表加载与运行时切换 |
| `mc_launcher/context.py` | `AppContext`（配置 / 源 / 账号 / 内容 / 下载中心）与 `AppBus`（日志、提示、事件） |
| `mc_launcher/version.py` | 版本清单缓存与版本列表筛选 |
| `mc_launcher/ui/*` | 各功能页面、公共控件、主题与图标绘制 |

### 页面一览

| 页面 | 类 | 能力 |
| :--- | :--- | :--- |
| 启动游戏 | `HomePage` | 版本列表、双击 / 多选启动、启动预检、拖拽导入、整合包快速入口 |
| 下载安装 | `DownloadPage` | 原版版本安装、加载器安装、加载器源文件另存为、仅下载客户端 Jar |
| 下载中心 | `DownloadCenterPage` | 任务表格、进度 / 速度 / 状态、暂停 / 恢复 / 取消 / 重试 / 打开目录 |
| 下载加速 | `DownloadAccelPage` | 粘贴任意直链（自动提取 URL）、选择保存目录、单任务线程数（最高 328，与全局共享预算）、提交到下载中心 |
| 内容中心 | `ContentPage` | Modrinth / CurseForge 搜索、用途分类（优化 / 科技 / 魔法等）、详情、安装到实例、另存为、中文译名与材质包分类 |
| 整合包 | `ModpackPage` | 已装整合包列表、导入、导出（CF 格式 / `.mikan`）、删除 |
| 账号管理 | `AccountsPage` | 三种登录方式、账号切换、皮肤管理 |
| 版本设置 | `ControlPage` | 单版本 Java / 内存 / 参数 / 隔离、Mod 管理、资源包、光影、存档、日志 |
| Mod 加载器 | `LoadersPage` | 左侧按 MC 版本浏览，右侧列出该版本可用的加载器版本（最多 12 行），一键安装 |
| 多人联机 | `MultiplayerPage` | 陶瓦联机安装、创建 / 加入房间、房间码复制、联机日志 |
| 内置浏览器 | `BrowserPage` + `webview2.py` | Edge WebView2 内核（可直接播放 B 站视频）、多标签、Cookie 持久化、QtWebEngine 回退 |
| Forbric | `ForbricPage` | 版本兼容拦截、安装器下载与 GUI 启动、结果监控 |
| Java 中心 | `JavaCenterPage` | 12 个 Java 发行版下载与安装（含清华 TUNA、华为云国内镜像），支持选择 JRE（仅运行）/ JDK 与主版本 |
| 依赖补全 | `DependenciesPage` | 不可内置第三方依赖清单（陶瓦 / authlib-injector / Java 运行时 / 加载器 / Forbric）、缺失依赖检查、询问式静默补全、下载中心任务 |
| 教程中心 | `WikiPage` | 内置 8 篇 Markdown 教程（中/英/俄/法/日）、目录浏览、标题与正文搜索、NBT 编辑器入口 |
| 基岩版 | `BedrockPage` | 三类来源（MCAPPX 历史 / 商店正式版 / 商店预览版）分类列表、架构与搜索过滤、内置浏览器（Edge 内核）下载、下载目录监听归档、安装 / 启动 / 卸载、打开下载目录 |
| 皮肤工厂 | `SkinFactoryPage` | 64×64 像素皮肤编辑器：画笔 / 橡皮 / 填充 / 取色 / 加亮 / 加深 / 直线 / 矩形 / 椭圆 / 喷枪、镜像对称、撤销重做（整份图层快照）、缩放与网格、按部位高亮底层与第二层 UV；最多 8 层多层绘画，列表勾选显隐、点击切换活动层，导出 PNG / 保存皮肤库 / 应用账号时自动合并；右侧 3D 模型（等轴测投影 + 第二层半透明叠加）可选中部位后直接作画，支持图层切换、左转 / 右转 / 复位视角按钮、视角滑块、自动旋转、Shift + 拖动旋转，多皮肤库保存 / 载入 / 删除、应用到当前账号 |
| 世界种子 | `SeedTerrainPage` | 输入种子 → 本机 Java 执行内嵌 TerrainGen（与 Minecraft 相同的柏林噪声算法与参数）生成高度图 → 内联 WebGL 把地形渲染为 Minecraft 风格方块（体素柱：平顶 + 阶梯侧面，海平面压平，侧面按朝向压暗），视角 / 缩放 / 平移按钮 + 拖动旋转 / 滚轮缩放 / 右键平移 / 双击复位 / 自动旋转，可调尺寸与起伏、导出高度图 PNG |
| 设置 | `SettingsPage` | 数据目录、下载源、线程数（1–328）、代理、API Key、镜像、界面选项（含启动动画 / 页面切换动画 / 毛玻璃开关）、主题色与背景、插件目录、功能开关、自动检测推荐内存、预加载 JVM（实验性，含预加载 Java 选择） |

> 注意区分两个加载器页：`LoaderPage`（`page_loader.py`）是「下载安装」页里的**表单式**加载器安装区（手动填 MC 版本 + 加载器版本）；`LoadersPage`（`page_loaders.py`）是导航栏独立入口「Mod 加载器」，按 MC 版本**浏览列表**后选择安装。两者共用同一套安装 worker 与 `modloader.install_loader()`。

### 页面开发约定

新增页面只需三步：

1. 在 `mc_launcher/ui/` 下新建 `page_xxx.py`，实现 `QWidget` 子类，构造函数接收 `ctx: AppContext`
2. 在 `main_window.py` 的 `nav_items` 中插入 `(key, "中文名")`，并在页面容器中加入实例
3. 若页面有后台线程或对话框，实现 `shutdown()` 并在 `MainWindow.shutdown()` 中调用

### 数据文件

| 文件 | 内容 |
| :--- | :--- |
| `data/config.json` | 全部设置项、下载源列表、数据目录列表、实例列表、版本设置、服务器列表 |
| `data/accounts.json` | 账号列表与当前选中账号（含刷新令牌） |
| `data/instances/<实例>/instance.json` | 实例元数据（名称、MC 版本、加载器、来源整合包、创建时间） |
| `data/wiki/<语言代码>/*.md` | 内置教程 Markdown（首次运行按当前界面语言自动写入，可自行修改 / 扩充） |
| `mc_launcher/data/bedrock_catalog.json` | 基岩版离线版本目录（随程序分发，只读；含包 ID、架构体积、SHA256 与 mcappx 直链） |

---

## 项目结构

```
MikanCL/
├── run.py                      # 源码启动入口（python run.py）
├── build_exe.py                # 一键打包脚本（python build_exe.py）
├── requirements.txt            # 依赖清单
├── 启动.bat                    # Windows 下便捷启动
├── assets/
│   └── mikan.ico               # 应用图标
├── mc_launcher/                # 启动器主包
│   ├── __init__.py             # 应用名、版本号、User-Agent
│   ├── main.py                 # 应用入口（单实例、日志、退出落盘）
│   ├── config.py               # 配置 / 路径 / 下载源 / 实例
│   ├── net.py                  # HTTP / 下载 / 镜像
│   ├── installer.py            # 原版安装
│   ├── modloader.py            # 加载器安装
│   ├── launcher.py             # 游戏启动
│   ├── auth.py                 # 账号与皮肤
│   ├── content.py              # 内容平台与整合包
│   ├── downloads.py            # 下载中心
│   ├── java.py                  # Java 探测与下载（JRE / JDK）
│   ├── dependencies.py          # 不可内置第三方依赖清单与缺失依赖扫描
│   ├── forbric.py              # Forbric
│   ├── bedrock.py              # 基岩版（目录 / 商店接口 / 下载 / 安装 / 启动）
│   ├── terrain_java.py         # 世界种子地形（内嵌原版同算法柏林噪声 Java 程序）
│   ├── data/                   # 随程序分发的静态数据
│   │   └── bedrock_catalog.json # 基岩版离线版本目录（32 主版本 / 82 发行版）
│   ├── resources/              # 原生依赖
│   │   └── WebView2Loader.dll  # 内置浏览器调用 Edge 内核的加载器
│   ├── nbt.py                  # NBT 读写（level.dat / playerdata）
│   ├── terracotta.py           # 陶瓦联机
│   ├── cn_source.py            # MC百科译名词典（在线 + 缓存）
│   ├── mod_cn.py               # 本地中文词表、用途分类与中文检索
│   ├── plugins.py              # 插件加载与插件 API
│   ├── i18n.py                 # 五语言翻译
│   ├── agreement.py            # 用户协议文案（5 语言）与同意状态
│   ├── context.py              # 应用上下文
│   ├── version.py              # 版本清单
│   └── ui/                     # 界面层
│       ├── main_window.py      # 主窗口 / 导航 / 托盘 / 拖拽
│       ├── theme.py            # 深色主题、图标与头像绘制
│       ├── widgets.py          # 公共控件
│       ├── page_home.py        # 启动游戏
│       ├── page_download.py    # 下载安装
│       ├── page_download_center.py
│       ├── page_download_accel.py # 下载加速（任意直链多线程下载）
│       ├── page_content.py     # 内容中心
│       ├── page_modpack.py     # 整合包
│       ├── page_accounts.py    # 账号与皮肤
│       ├── page_skin_pack.py   # 皮肤包打包 / 导入
│       ├── page_control.py     # 版本设置 / Mod 管理
│       ├── page_multiplayer.py # 多人联机（陶瓦）
│       ├── page_browser.py     # 内置浏览器
│       ├── webview2.py         # Edge WebView2 内核（ctypes 直调 COM）
│       ├── page_forbric.py     # Forbric（+ forbric_worker.py）
│       ├── page_java_center.py # Java 中心（JRE / JDK）
│       ├── page_dependencies.py # 依赖补全（第三方依赖 + 缺失扫描 / 静默补全）
│       ├── page_wiki.py        # 教程中心（内置 Markdown Wiki）
│       ├── page_bedrock.py     # 基岩版（分类列表 / 下载 / 安装 / 启动）
│       ├── dialog_nbt.py       # NBT 编辑器对话框
│       ├── dialog_agreement.py # 用户协议确认 / 查看对话框
│       ├── page_settings.py    # 设置
│       ├── page_loader.py      # 加载器安装（表单式：手动选 MC 版本 + 加载器版本）
│       ├── page_loaders.py     # 加载器安装（按 MC 版本浏览，LoadersPage）
│       ├── dropinstall.py      # 拖拽导入 / 直装包
│       ├── covers.py           # 封面与缓存
│       └── skin_view.py        # 皮肤预览
├── data/                       # 运行时数据（自动生成）
│   ├── config.json             # 设置
│   ├── accounts.json           # 账号
│   ├── cache/                  # 版本清单、下载缓存、Forbric 安装器
│   ├── instances/              # 整合包 / 隔离实例
│   ├── libs/                   # authlib-injector 等运行库
│   ├── logs/                   # launcher.log、install_error.log
│   ├── skins/                  # 皮肤缓存
│   ├── bedrock/                # 基岩版安装包下载目录（.appx）
│   ├── wiki/                   # 内置教程 Markdown（按语言分目录，首次运行自动生成）
│   └── browser/                # QtWebEngine profile（Cookie / 登录态）
└── dist/                       # 打包产物（MikanCL.exe）
```

---

## 技术栈与依赖

### 核心依赖

| 依赖 | 说明 |
| :--- | :--- |
| PySide6 ≥ 6.6 | Qt6 Python 绑定（QtWebEngine 仅作浏览器回退内核） |
| Microsoft Edge WebView2 Runtime | 内置浏览器主内核，Windows 10/11 默认已预装 |

### 标准库

`urllib`（HTTP / Range 下载）、`zipfile` / `tarfile`（整合包与安装器解压）、`concurrent.futures`（多线程下载）、`threading`（暂停 / 取消）、`subprocess` + `ctypes`（安装器与内存检测）、`json`（全部配置持久化）。

> 解压带路径穿越防护：Python 3.12+ 使用 `tarfile.extractall(filter="data")`，3.10 / 3.11 自动降级为普通 `extractall()`（见 `terracotta.py`），因此最低 Python 版本仍为 3.10。

### 运行时依赖

| 依赖 | 说明 |
| :--- | :--- |
| Java 8 / 11 / 17 / 21 | 由版本 JSON 与加载器决定，可在 Java 中心下载 |
| 陶瓦联机（Terracotta） | 房间码 P2P 联机运行时，可在「依赖补全」页下载 |
| authlib-injector | 外置登录 / 皮肤站注入组件，可在「依赖补全」页下载 |
| Mod 加载器 / Forbric | 需按版本调用官方安装器，入口统一收录在「依赖补全」页 |
| Visual C++ Redistributable | 部分加载器安装器与游戏运行需要 |
| CustomSkinLoader（可选 Mod） | 让离线皮肤在游戏内生效 |

> 以上第三方依赖因许可、体积或官方分发渠道限制均不随启动器内置，「依赖补全」页集中展示其安装状态并提供下载或跳转入口。

---

## 运行与打包说明

### 方式一：已打包 exe（推荐）

1. 从 [Releases](https://github.com/luohaocheng171/mikanCL/releases) 下载 `MikanCL.exe` 放到任意目录
2. 双击运行，程序会在 exe 同目录自动创建 `data/` 保存配置与缓存；首次启动需确认《用户协议 v1.4》
3. 首次运行可能触发 SmartScreen 提示，点击「更多信息」→「仍要运行」
4. 如被杀毒软件误报，请将程序所在目录加入白名单

### 方式二：源代码运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python run.py
```

也可以双击 `启动.bat`。

### PyInstaller 打包

```bash
python build_exe.py
```

脚本等价于：

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name MikanCL \
  --icon assets/mikan.ico \
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtCharts \
  --exclude-module PySide6.QtQuick3D --exclude-module PySide6.QtWebEngineQuick \
  run.py
```

脚本会自动收集 PySide6 / QtWebEngine 全部模块、`mc_launcher/translations`、`mc_launcher/data` 与 `mc_launcher/resources`，产物位于 `dist/MikanCL.exe`（约 210.8 MB），单文件、免安装，不依赖本机 Python 环境。

---

## 注意事项

1. **首次使用建议顺序**：设置 → 选择 Java（或用 Java 中心下载）→ 下载安装原版版本 → 按需安装加载器 → 启动
2. **内存设置**：建议不超过物理内存的 70%，启动预检会提示超限；整合包体积较大时请确认磁盘空间 > 2GB
3. **整合包安装耗时**：首次安装需要完整下载对应版本的库文件与 3000+ 资源文件，进度可在下载中心查看；中途取消不会丢失已下载分片，重新导入会续传
4. **Mod 冲突**：同一 Mod 的多个版本同时存在会导致游戏崩溃，版本设置中会红色标记，建议只保留一个
5. **离线皮肤**：需要把 CustomSkinLoader Mod 放入实例的 `mods/`，皮肤文件写入 `CustomSkinLoader/LocalSkin/skins/<玩家名>.png` 后才会在游戏内显示；下载新版本或导入整合包 / 实例完成时会自动写入对应玩家并生成该版本的兜底资源包，无需手动复制。资源包默认不启用，避免替换服务器其他默认皮肤玩家
6. **并发安装**：下载安装页最多同时安装 5 个版本，第 6 个需等待空位；多个版本共享的库文件按目标路径加锁下载，不会互相覆盖
7. **Forbric**：实验性功能，底层构建只支持特定 MC 版本（当前 26.2），不兼容的实例会禁用安装按钮；安装过程需要 Java 21
8. **CurseForge API Key**：内置默认 Key 可能随时失效，可在设置中替换为自己的 Key
9. **下载源**：国内网络建议把 BMCLAPI 镜像优先级调高；CurseForge / Modrinth 也支持自定义镜像地址
10. **单实例限制**：同一时间只能运行一个 MikanCL；如需切换数据目录，请使用侧边栏的数据目录下拉框
11. **杀毒软件**：PyInstaller 打包的 exe 常被误报，加入白名单即可
12. **基岩版下载**：点「在浏览器下载」会切到内置浏览器（优先 Edge 内核）打开该版本的下载页，在页面上点下载按钮即可；下载完成的 `.appx` / `.msix` 会由启动器自动归档到基岩版下载目录，随后点「从本地安装」安装
13. **基岩版启动要求**：手动安装的安装包本身不含授权，启动时需用拥有 Minecraft 的微软账号登录商店（或加入 Game Pass），否则系统会报 `0x803F8001`；启动 20 秒后未检测到进程时会给出该提示
14. **基岩版降级**：安装低版本会替换现有版本（`-ForceUpdateFromAnyVersion`），想回到新版重新下载安装即可
15. **第三方依赖**：陶瓦联机、authlib-injector、Java 运行时、Mod 加载器与 Forbric 均不随启动器内置，统一在「依赖补全」页查看状态并下载或跳转；这些模块由各自作者独立维护，下载 / 使用风险由使用者自行承担，详见《用户协议 v1.4》第十一条
16. **依赖补全**：检查本身只读本地文件、不联网；只有用户确认后才会把补全任务加入下载中心。加载器类依赖需按游戏版本使用官方安装器，页面只提供跳转入口

---

## 开发指南

### 新增下载源

在设置页「下载源」中新增条目，字段含义：

| 字段 | 说明 |
| :--- | :--- |
| `id` | 唯一标识（小写） |
| `name` | 显示名称 |
| `manifest_url` | `version_manifest_v2.json` 地址 |
| `mapping` | `bmclapi`（BMCLAPI 路径改写）/ `direct`（同路径镜像）/ `none`（仅用于清单） |
| `download_base` | 改写后的下载根地址 |
| `api_key` / `api_key_header` | 需要鉴权的源使用 |
| `priority` | 数值越小越优先 |

### 适配新的 Mod 加载器

1. 在 `modloader.py` 的 `list_loader_versions()` 中增加版本查询分支
2. 在 `install_loader()` 中增加安装实现：优先复用 `_install_installer()`（官方安装器）或 `_install_profile()`（直接写入版本 JSON）
3. 在 `java_for_mc()` 中确认所需 Java 主版本
4. 如需在 UI 中单独呈现，可参考 `page_forbric.py` 的 Worker + Page 结构

### 新增下载任务类型

1. 实现 `QThread` 子类，定义 `progress(float, str)`、`log(str)`、`done(...)`、`failed(str)`、`cancelled(str)` 信号
2. 通过 `ctx.downloads.submit(kind, name, factory, cancel=..., pause=...)` 登记任务
3. 在完成 / 失败 / 取消时分别调用 `ctx.downloads.finish()` / `finish_cancelled()`，并确保 `cancelled` 分支不写错误日志

### 主题与图标

`ui/theme.py` 提供全局 `STYLESHEET`、`make_block_icon()`（应用 / 标题栏图标）、`make_nav_icon()`（侧边栏图标）、`make_version_pixmap()`（版本分类图标）、`draw_block_pixel_progress()`（启动动画草方块）、`make_avatar()`（离线像素头像）、`make_skin_avatar()`（皮肤头部头像）与 `resolve_account_avatar()`（按皮肤 / 像素自动回退）。新增导航项时若没有专属图标分支，会自动回退到默认方块图标。

---

## 许可证

MikanCL 以 **GNU General Public License v3.0（GPL-3.0）** 发布。完整许可文本见 [gnu.org/licenses/gpl-3.0](https://www.gnu.org/licenses/gpl-3.0.html)（正式发布时请在仓库内附上 `LICENSE` 文件）。

简单来说：

| 你可以 | 你必须 |
| :--- | :--- |
| 自由运行、复制、分发本程序 | 分发时保留版权声明与许可声明 |
| 阅读、修改源码 | 修改后的版本同样以 GPL-3.0 开源 |
| 基于本程序发布衍生作品 | 不得追加限制他人行使 GPL 权利的条款 |

本程序按「现状」提供，不附带任何明示或暗示的担保（详见许可证第 15、16 条）。

> **许可边界**：GPL-3.0 只覆盖 MikanCL 自身的代码。Minecraft 游戏本体、Mod、整合包、资源包、光影包、材质包、Java 运行时，以及第三方组件（陶瓦联机 Terracotta 与 authlib-injector 均为 AGPL-3.0、Forbric 以作者仓库声明为准、各 Mod 加载器适用各自开源许可）均适用各自的权利与许可，请分别遵守。

**法律声明**：MikanCL 仅提供版本下载、启动与内容管理的客户端功能，不包含任何 Minecraft 游戏本体、Mod 二进制文件或账号凭据。Minecraft 为 Mojang / Microsoft 的商标与版权作品，请通过正版渠道购买与使用；Mod、整合包、资源包、光影包的版权归各自作者所有，请遵守其授权协议。首次使用前程序会要求阅读并同意内置的《用户协议 v1.4》（11 项条款，含非官方声明、第三方模块免责与风险说明），不同意则不会进入主界面。陶瓦联机、authlib-injector、Java 运行时、Mod 加载器与 Forbric 等第三方依赖均不随启动器内置，仅在「依赖补全」页提供下载或跳转入口，其许可与使用风险由使用者自行确认与承担。

---

## 项目地址

- 仓库主页：<https://github.com/luohaocheng171/mikanCL>
- 问题反馈 / 功能建议：<https://github.com/luohaocheng171/mikanCL/issues>
- 版本发布（下载 `MikanCL.exe`）：<https://github.com/luohaocheng171/mikanCL/releases>

---

## 鸣谢

MikanCL 能跑起来，靠的是下面这些人和项目。排名不分先后，如有遗漏请联系补充。

### 参考的启动器

- **PCL2（Plain Craft Launcher 2）** — 界面布局、版本卡片交互、整合包安装顺序的重要参考
- **HMCL（Hello Minecraft! Launcher）** — 实例隔离、Java 匹配、外置登录与下载源的思路来源
- **Prism Launcher / MultiMC** — 「实例 = 独立目录」模型的参考
- **Modrinth App** — 内容中心搜索与一键安装的交互参考

### 框架与工具

- **DeepSeek** — 全程 AI 辅助开发
- **PySide6 / Qt 6** — 界面框架（含 QtWebEngine 内置浏览器）
- **PyInstaller** — 单文件打包

### 数据与服务

- **Mojang / Microsoft** — 版本清单、资源索引与官方下载源
- **BMCLAPI（bangbang93）** — 国内下载镜像加速
- **MC百科（mcmod.cn）** — Mod / 整合包中文译名与中文检索词典
- **Modrinth** — 内容平台 API 与 CDN
- **CurseForge / Overwolf** — 内容平台 API 与 CDN
- **MCAPPX（mcappx.com）** — 基岩版历史版本离线安装包与版本目录
- **rg-adguard（store.rg-adguard.net）** — 微软商店应用文件直链解析
- **Microsoft Store / delivery.mp.microsoft.com** — 基岩版正式版与预览版安装包直链

### Mod 生态

- **Forge / NeoForge / Fabric / Quilt / LiteLoader** — 各加载器及其安装器
- **Forbric（Ray-T-r）** — 实验性三合一加载器
- **authlib-injector（yushijinhun）** — 外置登录 / 皮肤站支持
- **CustomSkinLoader** — 离线皮肤在游戏内生效
- **Terracotta / 陶瓦联机（Burning_TNT，HMCL 团队）** — P2P 房间码联机组件（AGPL-3.0）

### Java 运行时

- **Adoptium（Eclipse Temurin）**、**Microsoft OpenJDK**、**Azul Zulu**、**Amazon Corretto**、**Alibaba Dragonwell**、**Tencent Kona**

### 开源社区

- 所有在 Issue、讨论区反馈问题与提出建议的玩家
- 所有坚持开源 Mod 加载器、工具链与内容平台的作者
