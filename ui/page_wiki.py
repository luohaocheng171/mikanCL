"""教程中心：内置多语言 Markdown Wiki，支持搜索与按标题浏览。"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import WIKI_DIR
from ..context import AppContext
from ..i18n import DEFAULT_LANGUAGE
from .widgets import Card, page_header
from .dialog_nbt import NbtEditorDialog

# 内置教程正文：按界面语言分目录写入 WIKI_DIR/<语言>，打包时也不会遗漏
DEFAULT_WIKI: dict[str, dict[str, str]] = {
    "zh_CN": {
        "00_quick_start.md": """# 启动器快速上手：从零到进入游戏

## 一、首次启动
1. 首次打开会弹出《用户协议与免责声明》，完整阅读后点击「同意并继续」。
2. 进入主界面，左侧是磁贴式导航：主页、下载安装、内容中心、版本设置、多人联机、教程中心、设置等。
3. 顶部标题栏可拖动窗口、双击最大化，右上角为最小化 / 最大化 / 关闭。
4. 若启动时检测到无网络，联网功能会置灰并显示「当前无网络」，此时仍可启动已安装的版本。

## 二、准备 Java
1. 打开「设置 → Java 运行时」，启动器会自动扫描常见安装路径、注册表与 PATH。
2. 同一主版本默认只显示一个（优先 64 位、路径更短），右键可切换「查看所有 Java 版本」。
3. 缺少 Java 时，打开「Java 中心」，选择发行版与主版本（如 Temurin 17）后下载。
4. 双击 Java 列表中的一行即可设为默认。

## 三、安装游戏版本
1. 打开「下载安装」页，选择 Minecraft 版本。
2. 需要 Mod 时选择加载器（Forge / NeoForge / Fabric / Quilt）及加载器版本。
3. 点击「安装所选版本」，任务会进入下载中心，可暂停、取消或重试。
4. 安装完成后，在「版本设置」中选择该版本即可启动。

## 四、登录账号
1. 打开「账号」页：支持微软正版登录、外置登录（authlib-injector）与离线账号。
2. 微软登录按提示在浏览器中输入设备码完成授权，令牌只保存在本机。
3. 离线账号仅用于本地测试，请支持正版。

## 五、启动游戏
1. 在主页选择实例与版本，点击「启动游戏」。
2. 启动前会自动检查版本文件、Java 与磁盘空间；缺失文件可一键补全。
3. 若开启「启动前自动备份存档」，会在满足条件时自动打包 saves/ 下的世界。
4. 启动成功后，日志会实时显示在主页 / 日志面板。

## 六、版本设置与实例
1. 「版本设置 → 概览」显示版本、加载器、健康度（绿 / 黄 / 红）。
2. 「游戏设置」可调整内存、Java、窗口大小、JVM 参数、进程优先级与版本隔离。
3. 「模组管理」可启用 / 禁用 / 删除 Mod，并检测重复 modid、缺失前置与版本不匹配。
4. 「存档管理」可列出世界、备份为 Zip、从备份恢复，或打开备份目录。
5. 隔离策略建议：整合包用「版本隔离」，皮肤 / 资源包需要全实例共享时用「全部隔离」。

## 七、内容中心
1. 搜索 Mod / 整合包 / 资源包 / 光影，按游戏版本与加载器筛选。
2. 「检查更新」会同时用 Modrinth（SHA1）与 CurseForge（Murmur2 指纹）识别本地 Mod。
3. 缺失前置可到「依赖补全」页点击「补全缺失前置」，自动搜索并安装最新兼容版本。
4. 整合包支持拖拽导入：直接把 zip / mrpack 拖到窗口即可，安装流程与内容中心一致。

## 八、多人联机与服务器
1. 打开「多人联机」页，添加服务器地址。
2. 列表会通过 Minecraft Server List Ping 显示延迟、在线人数、MOTD、版本与图标。
3. 双击服务器即可启动游戏并进入该服务器。

## 九、存档与备份
1. 版本设置 → 存档管理：勾选世界后可「备份选中」或「备份全部」。
2. 备份文件位于备份目录（默认 data/backups/<版本>/），文件名带时间戳。
3. 存档损坏时点击「恢复备份…」，选择对应 Zip 即可恢复到该版本的 saves/。
4. 自动备份默认开启，同一世界 1 分钟内不会重复备份，最多保留 20 份。

## 十、外观与性能
1. 设置 → 外观：可更换背景图、主题色、界面语言与动画开关。
2. 毛玻璃默认关闭；开启后背景变为全毛玻璃，卡片与按钮为半透明材质（参考 iOS），文字保持清晰。
3. 若切页卡顿，可关闭动画；页面刷新已改为空闲时执行，不会阻塞界面。

## 十一、常见问题
- 启动卡在下载：在设置中启用 BMCLAPI 镜像，或调低下载线程 / 设置限速。
- Mod 冲突：到「模组管理」看红色标记，或在「依赖补全」检查缺失前置。
- 内存不足：把最大内存调到物理内存的 70% 以内，并使用 64 位 Java。
- 找不到版本：确认 versions/<版本ID>/<版本ID>.json 存在，必要时用「修复版本」。
- 需要反馈日志：主页 / 日志面板可复制最近输出，便于排查。
""",
        "01_install_forge.md": """# 安装 Forge

## 前置
- 已安装对应版本的 Minecraft 原版
- 已安装 Java 8 / 17 / 21（按 MC 版本选择）

## 步骤
1. 打开「下载安装」页
2. 选择目标 Minecraft 版本
3. 在"Mod 加载器"里选 Forge
4. 选择 Forge 版本（推荐最新的稳定版）
5. 点击"安装所选版本"

## 常见问题
- 卡在"下载安装器"：网络问题，去设置里启用 BMCLAPI 镜像
- 安装器退出码非 0：通常是 Java 版本不匹配，检查 Java
- 找不到生成的版本：检查 `versions/<版本ID>/<版本ID>.json` 是否存在
""",
        "02_install_fabric.md": """# 安装 Fabric

## 与 Forge 的区别
- Fabric 更轻量，启动更快
- Fabric 的 Mod 生态更偏向"新版本 + 轻改"
- 大部分优化类 Mod（钠、锂）都是 Fabric 优先

## 步骤
1. 打开「下载安装」页
2. 选择 Minecraft 版本
3. 加载器选 Fabric
4. 安装（会自动附带 Fabric API）

## 注意
- Fabric API 是大部分 Fabric Mod 的前置，安装 Fabric 时已自动附带
- Quilt 是 Fabric 的衍生，大部分 Fabric Mod 能在 Quilt 上跑
""",
        "03_install_shader.md": """# 安装光影

## 前置
- 加载器：Fabric 需装 Iris，Forge 需装 Oculus
- 推荐：OptiFine（旧版本）或 Iris + Sodium（新版本）

## 步骤
1. 在「内容中心」搜 "Iris" 或 "Oculus"，安装到实例
2. 把光影包（.zip）放进 `shaderpacks/` 目录
3. 启动游戏，选项 → 视频设置 → 光影 → 选择光影包

## 性能提示
- 光影很吃显卡，集成显卡慎用
- 启动预检会在检测到"核显 + 光影"时给出警告
""",
        "04_memory_issue.md": """# 内存不足

## 症状
- 游戏卡顿、掉帧
- 日志里出现 OutOfMemoryError
- 启动预检提示"分配内存超过物理内存 70%"

## 解决方案
1. 打开「版本设置」→「游戏设置」
2. 把"最大内存"调到合理值：
   - 原版：2-4 GB
   - 轻量 Mod：4-6 GB
   - 大型整合包：6-8 GB
3. 不要超过物理内存的 70%

## 注意
- 内存不是越大越好，过大会拖慢系统
- 32 位 Java 最多只能用 1.5 GB，请确认用 64 位
""",
        "05_mod_conflict.md": """# Mod 冲突

## 症状
- 游戏启动崩溃
- 日志里出现 NoSuchMethodError / ClassNotFoundException
- 启动预检提示"检测到 N 个 Mod 冲突"

## 排查步骤
1. 打开「版本设置」→「模组管理」
2. 看红色标记的 Mod（冲突项）
3. 常见冲突：
   - 同一个 Mod 装了多个版本（重复 modid）
   - 缺少前置（missing dependency）
   - 版本范围不满足（version mismatch）

## 解决方案
- 重复 modid：禁用其中一个
- 缺少前置：去内容中心搜前置名，安装
- 版本不满足：升级或降级对应 Mod
""",
        "06_java_version.md": """# Java 版本选择

## 对照表

| Minecraft 版本 | Java 版本 |
|---|---|
| 1.0 - 1.16.5 | Java 8 |
| 1.17 - 1.20.4 | Java 17 |
| 1.20.5+ | Java 21 |

## 检查当前 Java
- 设置页 → Java 运行时，会列出所有检测到的 Java
- 双击一行可设为默认

## 安装 Java
- 打开「Java 中心」，选发行版和主版本，下载
- 推荐 Adoptium Temurin（社区最广）
""",
        "07_nbt_editor.md": """# NBT 编辑器使用

## 什么是 NBT
NBT（Named Binary Tag）是 Minecraft 的存档数据格式，`level.dat`、`playerdata/*.dat` 都是 NBT。

## 入口
- 教程中心顶部"🔧 打开 NBT 编辑器"
- 版本设置 → 版本管理 → "编辑 level.dat"
- 主页工具区的"NBT 编辑器…"

## 常见用途
- 改世界种子：编辑 `level.dat` 的 `Data.WorldGenSettings.seed`
- 改游戏模式：编辑 `playerdata/<uuid>.dat` 的 `playerGameType`
- 改坐标：编辑 `Pos` 数组

## 操作说明
- 双击"值"列可编辑叶子节点（字符串 / 数字）
- 右键可"添加子标签"或"删除标签"（根节点不可删除）
- 复合类型（TAG_Compound）只能展开，不能直接改值

## 安全提示
- 首次保存会在同目录自动生成 `.bak` 备份
- 不确定的字段不要动
- 改坏了可以从备份恢复
""",
        "08_offline_skin.md": """# 离线皮肤

## 原理
离线账号没有 Mojang 皮肤服务，需要用 CustomSkinLoader Mod + 本地皮肤文件模拟。

## 步骤
1. 在「内容中心」搜 "CustomSkinLoader"，安装到实例
2. 打开「账号管理」→ 选中离线账号 → "使用本地皮肤…"
3. 选一张 64×64 或 64×32 的 PNG，并在弹窗里选择 Steve（经典）或 Alex（纤细）手臂模型
4. 启动游戏，CustomSkinLoader 会自动应用

## 分享给其他玩家
「皮肤包」标签页可以把皮肤、目标玩家名和手臂模型打成一个 `.zip`：对方导入后会写入自己的 `CustomSkinLoader/LocalSkin/skins/<玩家名>.png`，在服务器里只有这名玩家显示该皮肤，不会影响其他人。打包时会按目标版本自动选择 `pack_format` 或 `min_format/max_format`，同时写入新旧两套玩家皮肤纹理路径；导出的 `.zip` 本身就是完整资源包，也可以直接放进 `resourcepacks` 加载。

## 注意
- 皮肤文件会写入 `CustomSkinLoader/LocalSkin/skins/<玩家名>.png`，按玩家名加载
- 只有装了 CustomSkinLoader 才会生效
- 兜底资源包默认不启用，避免把服务器上其他默认皮肤玩家也变成这张皮肤
- 正版账号不需要这个，直接上传皮肤即可
""",
        "09_bedrock.md": """# 基岩版（Bedrock）

## 版本来源
「基岩版」页按三类列出安装包：历史版本、商店正式版、商店预览版。目录来自 MCAPPX 的离线安装包索引，只做展示与匹配，不内置任何安装包。

## 安装
1. 打开「基岩版」，选择需要的版本。
2. 历史版本若无法直接下载（站点有 Cloudflare 校验），点「在浏览器下载」，用内置 Edge 内核打开页面，下载完成的 `.appx` / `.msix` 会被自动归档。
3. 点「安装」后调用系统 `Add-AppxPackage` 部署。机械硬盘上 800MB+ 的包可能需要十几分钟，进度条会一直显示「正在部署」，请勿重复点击。
4. 安装完成后，启动菜单会显示基岩版条目，可直接启动或卸载。

## 注意
- 已安装判断会把包版本号（如 1.8.102.0）归一化后与商店版本匹配，两者版本号写法不同并不代表没装。
- 商店格式的安装包由微软签名，卸载走系统「应用」列表，不会影响 Java 版存档。
""",
        "10_loaders.md": """# 加载器：Forge / NeoForge / Fabric / Quilt / LiteLoader / Forbric

## 一键安装
1. 打开「下载安装」，选择 Minecraft 版本。
2. 在「Mod 加载器」中选择加载器与加载器版本。
3. 点「安装所选版本」：启动器会自动下载对应版本的加载器安装器，并以子进程方式完成安装。
4. 安装进度条单调递增，不会因为重试而回退。

## 各加载器特点
- **Forge**：生态最全，老整合包首选，启动较慢。
- **NeoForge**：Forge 分叉，1.20.2+ 生态主力。
- **Fabric**：轻量、更新快，优化类 Mod（钠、锂）优先支持。
- **Quilt**：Fabric 衍生，多数 Fabric Mod 可通用。
- **LiteLoader**：仅老版本可用，用于小地图等少量 Mod。
- **Forbric**：实验性三合一引导，仅支持指定版本（当前 26.2）。版本不兼容时安装按钮会禁用并给出提示。

## 单独下载加载器安装包
「内容中心 → 加载器源文件」可以直接下载各加载器的安装器 / 库文件，适合离线安装或自行排查。

## 常见问题
- 安装器退出码非 0：多为 Java 主版本不匹配，先在「Java 中心」装对应版本。
- 找不到生成版本：检查 `versions/<版本ID>/<版本ID>.json`；加载器版本判断按专属前缀匹配，避免把原版目录误认成已安装加载器。
""",
        "11_modpack.md": """# 整合包导入、导出与安装

## 导入
- 把 `.zip` / `.mrpack` 拖进窗口，或到「整合包」页选择文件。
- 启动器先下载整合包对应的原版版本，再安装加载器，最后刷入 overrides 与 mods。
- 实例目录使用内容摘要命名，重复导入同一整合包会复用目录并续传，不会重复下载。

## 私有备份格式
「整合包 → 导出」支持两种格式：
- **CurseForge 分享格式**：通用，可发给使用其他启动器的朋友。
- **Mikan 私有备份**：包含实例配置、版本设置与本地附加文件，适合自己迁移或备份。

## 安装失败怎么办
1. 失败时 traceback 会写入 `data/logs/install_error.log`，安装日志也会自动复制到剪贴板。
2. 先检查磁盘空间（预检要求 >2GB）与网络；镜像站点可在「设置 → 下载源」切换。
3. 下载失败会自动重试；仍失败可在「下载中心」取消后重新导入，已完成的文件会保留。

## 安装成功后
实例会自动写入 `instance.json`、自动选中并刷新主页版本列表；如需隔离，可在「版本设置」中选择 mod 隔离 / 存档隔离 / 全部隔离。
""",
        "12_download_center.md": """# 下载中心、加速与任务管理

## 下载中心
所有下载（游戏版本、加载器、Mod、整合包、Java、基岩版安装包）都会进入「下载中心」，按阶段展示：
- 需要下载哪些文件、保存到哪里；
- 当前速度、剩余大小与进度；
- 排队 / 下载中 / 校验中 / 安装中 / 完成 / 失败。

任务可暂停、继续、取消与重试；未完成的任务会保留 `.part` 临时文件，下次按 Range 断点续传。

## 下载加速
- 「下载加速」页可切换镜像源（官方 / BMCLAPI 等），并对同一文件的多个源测速。
- 线程数在「设置 → 下载」中调整；所有下载均使用多线程。
- 可设置全局限速，避免占满带宽。

## 右下角悬浮按钮
有下载任务时，窗口右下角会出现圆形悬浮按钮：单击跳转下载中心，右键返回上一页；没有任务时自动隐藏。

## 说明
版本并发安装上限为 5 个；同一目标文件有写入锁，多个任务不会互相覆盖 `.part`。
""",
        "13_java_deps.md": """# Java 中心与依赖补全

## Java 中心
1. 聚合 Temurin、Microsoft、Azul、Corretto、Dragonwell、Kona 等发行版，并接入国内镜像。
2. 支持只装轻量 JRE 或完整 JDK，可自动匹配当前 MC 版本所需的 Java 主版本。
3. 两种安装方式：
   - **ZIP 便携版**：解压到 `data/runtime`，并自动写入用户 PATH、广播环境变量变更；
   - **官方安装程序**（EXE / MSI）：走发行版自己的安装向导。
4. 大文件自动多线程分段下载，可在下载中心暂停或取消。

## 依赖补全
「依赖补全」页统一列出无法内置的第三方依赖：陶瓦联机、authlib-injector、Java 运行时、各类加载器等，并提供缺失扫描：
- 扫描 Java、客户端、依赖库、资源文件与日志是否缺失；
- 询问式静默补全：只补你确认的项，不会静默改动系统。

## 建议
- 1.12.2 及更早用 Java 8；1.17–1.20.4 用 Java 17；1.20.5+ 用 Java 21。
- 内存不要超过物理内存的 70%，32 位 Java 不支持大内存。
""",
        "14_instances.md": """# 版本目录、实例与导入其他启动器

## 版本目录分区
「设置 → 数据目录」可以添加多个版本目录，并在顶部下拉栏快速切换。常见用法：一个目录放原版，一个放整合包，一个放测试版本。

## 实例
- 主页实例列表双击即可启动；可多选多个版本后批量顺序启动。
- 「版本设置」按实例保存内存、Java、窗口大小、JVM 参数、隔离策略与进程优先级。
- 「版本设置 → 启动脚本」可以在启动前后执行自定义命令（如同步配置、启动辅助程序）。

## 从 PCL / HMCL 导入
1. 「设置 → 从其他启动器导入」点「扫描并导入…」，选择 PCL2 / HMCL 的启动器目录（含 `.minecraft` 的那一层）。
2. 勾选要导入的版本，可选择是否一并导入该版本的隔离、内存与 JVM 参数。
3. 导入只登记版本，不复制或移动原目录文件；本启动器已有的版本会自动跳过。

## 注意
- 切换版本目录后，主页与下载中心会按新目录刷新。
- 实例重复判断基于实际实例列表，导入或新建不会产生重复实例。
""",
        "15_skin_factory.md": """# 皮肤工厂：像素编辑与 3D 绘画

## 编辑方式
1. 「皮肤工厂」打开 64×64 皮肤画布（含第二层遮罩），提供画笔、橡皮、填充、取色、镜像与按部位分区。
2. 切换到「3D 绘画」后，可在模型上选中头部、身体、手臂、腿等部位直接作画，底层与第二层都可编辑。
3. 3D 预览支持 360° 双轴旋转（水平 + 垂直）、缩放与平移；画笔与鼠标操作模式通过独立按钮切换。
4. 画布可滚动并带缩放按钮，矮窗口或高倍率下也能看到脚部。

## 保存与应用
- 保存为 PNG，存放在本机 `data/skins`，不会上传。
- 可直接应用到离线账号或外置登录账号；离线皮肤需搭配 CustomSkinLoader。
- 导入过的皮肤会进入最近皮肤库，点击侧栏头像即可一键切换。

## 皮肤包
「皮肤包」页把皮肤、玩家名、手臂模型（Steve / Alex）、披风与鞘翅打成一个资源包：
- 自动按目标 MC 版本选择 `pack_format` 或 `min_format / max_format`（从材质包时代到最新版都适配）；
- 同时写入新旧两套玩家皮肤纹理路径；
- 一键覆盖到游戏目录时会先清理旧皮肤包再写入；
- 新版本安装完成后会自动导入离线皮肤包并生效。
""",
        "16_seed_terrain.md": """# 世界种子与 3D 地形预览

## 使用
1. 打开「种子 / 地形」，输入种子（数字或文本均可）。
2. 在「游戏版本」中选择一个已下载的版本：1.18+ 使用新版气候噪声 + Xoroshiro128++，1.7–1.17 使用经典 ImprovedNoise。
3. 点「生成」，启动器调用本机 Java 运行内置高度图程序，渲染出生点附近的 3D 地形。

## 与原版一致的部分
- 置换表为 256 项并用同一随机源洗牌，梯度表为原版 16 方向；
- 多 octave 叠加的 persistence 0.5、lacunarity 2 均为原版固定值；
- 1.18+ 的噪声随机源、频率与振幅与原版气候噪声一致。

## 与原版的差别
不包含生物群系、地形样条与密度函数，因此高度起伏接近但不等于游戏内实景。预览只用于筛种子，实际地形以 Minecraft 本体为准。
""",
        "17_extensions_themes.md": """# 扩展（插件）、主题与皮肤 API

## 扩展
- 支持 `.zip` / `.mikan-ext` 格式导入：拖进窗口或在「设置 → 扩展」中安装。
- 启用的扩展会出现在侧边栏；扩展运行在沙箱 iframe 中，只能通过 `postMessage` 与后端通信，不直接访问本机文件。
- 可随时禁用或删除；禁用后仍保留数据，便于再次启用。

## 主题
- 内置森林绿、海蓝、暮紫、赤红、琥珀、青碧、樱花粉、极夜蓝等主题，支持浅色 / 深色。
- 「设置 → 外观」可导入/导出 `data/themes/*.json`，也可调用主题 API 注册自定义皮肤。
- 导入过的皮肤与主题会自动记录并优先展示。

## 界面
- 侧边栏为竖排磁贴布局，磁贴与卡片使用毛玻璃；毛玻璃强度与模糊可在设置中连续调节。
- 窗口支持拖拽缩放（最小 960×600）与双击标题栏最大化，四角为圆角。
- 动态壁纸支持 MP4 / WebM / GIF / WebP，窗口切到后台自动暂停。
""",
        "18_browser_tools.md": """# 内置浏览器、联机与实用工具

## 内置浏览器
- 使用 Edge WebView2 内核，可直接播放 B 站等站点视频，不要求跳转到外部浏览器。
- 系统缺少 WebView2 时会自动回退并给出安装提示；也可把固定版本运行时解包到安装目录的 `webview2` 文件夹。

## 多人联机
1. 「多人联机」添加服务器地址，列表通过 Server List Ping 显示延迟、人数、MOTD 与图标。
2. 双击服务器即启动游戏并进入；陶瓦（Terracotta）联机可在「依赖补全」中安装后按房间码组网。

## 截图图库
按实例读取 `screenshots/`，支持预览、打包为 Zip、打开目录与删除，全程不联网。

## 崩溃报告
读取 `data/logs/crashes`，可查看摘要、复制文本与删除；整合包安装失败时也会把 traceback 写入 `data/logs/install_error.log`。

## NBT 编辑器
以类型树方式浏览存档与结构文件，可修改叶子节点；保存前会自动生成 `.bak` 备份。

## Mod 关系图
「内容中心 → Mod 关系图」展示实例内 Mod 的前置依赖与冲突关系，红色标记需要处理的项。

## 半透明毛玻璃 UI 材质包
1. 打开「皮肤包」页，最下方「半透明毛玻璃 UI 材质包」会自动列出本机已安装版本。
2. 选择版本后点「生成并安装到本机」：从该版本客户端 jar 取出按钮、输入框、滑块、
   背包/箱子面板、快捷栏与菜单背景贴图，原位改造成半透明冷色磨砂，
   写入 resourcepacks/ 并在 options.txt 中自动启用。
3. 「为全部已安装版本生成」会按每个版本各自的资源包格式（pack_format / min_format）分别打包。
4. 1.0–1.5.2 生成 texturepacks 纹理包，需要在游戏内「材质包」里手动选中；1.6.1+ 自动启用。
5. 安装位置遵循版本隔离设置；「导出 UI 包…」可得到可分享的 zip，其他启动器也能直接导入。
6. 若提示找不到客户端 jar，只会生成玻璃背景层，请先在「下载」页完整安装一次该版本。
""",
    },
    "en_US": {
        "01_install_forge.md": """# Installing Forge

## Prerequisites
- The matching vanilla Minecraft version is already installed
- Java 8 / 17 / 21 installed (choose according to the MC version)

## Steps
1. Open the "Downloads" page
2. Select the target Minecraft version
3. Choose Forge under "Mod Loaders"
4. Pick a Forge version (the latest stable one is recommended)
5. Click "Install Selected Version"

## Common issues
- Stuck at "downloading installer": network problem — enable the BMCLAPI mirror in Settings
- Installer exits with a non-zero code: usually a Java version mismatch, check your Java
- Generated version missing: check whether `versions/<version ID>/<version ID>.json` exists
""",
        "02_install_fabric.md": """# Installing Fabric

## How it differs from Forge
- Fabric is lighter and starts faster
- Fabric's mod ecosystem leans towards "new versions + small tweaks"
- Most optimisation mods (Sodium, Lithium) target Fabric first

## Steps
1. Open the "Downloads" page
2. Select a Minecraft version
3. Choose Fabric as the loader
4. Install (Fabric API is bundled automatically)

## Notes
- Fabric API is a dependency for most Fabric mods and is installed together with Fabric
- Quilt is a fork of Fabric; most Fabric mods run on Quilt
""",
        "03_install_shader.md": """# Installing shaders

## Prerequisites
- Loader: Iris for Fabric, Oculus for Forge
- Recommended: OptiFine (old versions) or Iris + Sodium (new versions)

## Steps
1. Search for "Iris" or "Oculus" in the Content Center and install it into the instance
2. Put the shader pack (.zip) into the `shaderpacks/` folder
3. Launch the game, then Options → Video Settings → Shaders → pick a pack

## Performance tips
- Shaders are GPU heavy — avoid them on integrated graphics
- The launch pre-check warns you when it detects "integrated GPU + shaders"
""",
        "04_memory_issue.md": """# Out of memory

## Symptoms
- Stuttering and frame drops
- OutOfMemoryError in the log
- The launch pre-check warns "allocated memory exceeds 70% of physical RAM"

## How to fix
1. Open "Version Settings" → "Game Settings"
2. Set "Max memory" to a sensible value:
   - Vanilla: 2-4 GB
   - Light modpacks: 4-6 GB
   - Large modpacks: 6-8 GB
3. Never exceed 70% of your physical RAM

## Notes
- More memory is not always better; too much slows the whole system down
- 32-bit Java can only use 1.5 GB — make sure you run 64-bit
""",
        "05_mod_conflict.md": """# Mod conflicts

## Symptoms
- The game crashes while starting
- NoSuchMethodError / ClassNotFoundException in the log
- The launch pre-check reports "N mod conflicts detected"

## Diagnosis
1. Open "Version Settings" → "Mods"
2. Look at the mods marked in red (the conflicting ones)
3. Typical conflicts:
   - The same mod installed in several versions (duplicate modid)
   - Missing dependency
   - Version mismatch

## Solutions
- Duplicate modid: disable one of them
- Missing dependency: search the dependency name in the Content Center and install it
- Version mismatch: upgrade or downgrade the affected mod
""",
        "06_java_version.md": """# Choosing a Java version

## Matching table

| Minecraft version | Java version |
|---|---|
| 1.0 - 1.16.5 | Java 8 |
| 1.17 - 1.20.4 | Java 17 |
| 1.20.5+ | Java 21 |

## Checking your Java
- Settings → Java runtimes lists every detected Java
- Double-click a row to make it the default

## Installing Java
- Open the "Java Center", choose a distribution and major version, then download
- Adoptium Temurin is recommended (widest community support)
""",
        "07_nbt_editor.md": """# Using the NBT editor

## What is NBT
NBT (Named Binary Tag) is Minecraft's save-data format; `level.dat` and `playerdata/*.dat` are both NBT.

## Where to open it
- "🔧 Open NBT editor" at the top of the Guide Center
- Version Settings → Version Management → "Edit level.dat"
- The "NBT editor…" button in the home page tool area

## Typical uses
- Change the world seed: edit `Data.WorldGenSettings.seed` in `level.dat`
- Change the game mode: edit `playerGameType` in `playerdata/<uuid>.dat`
- Change coordinates: edit the `Pos` array

## How to edit
- Double-click the "Value" column to edit leaf tags (strings / numbers)
- Right-click to add a child tag or delete a tag (the root cannot be deleted)
- Compound tags (TAG_Compound) can only be expanded, not edited directly

## Safety
- The first save creates a `.bak` backup in the same folder
- Do not touch fields you are unsure about
- Restore from the backup if something breaks
""",
        "08_offline_skin.md": """# Offline skins

## How it works
Offline accounts have no Mojang skin service, so the CustomSkinLoader mod plus a local skin file is used instead.

## Steps
1. Search for "CustomSkinLoader" in the Content Center and install it into the instance
2. Open "Accounts" → select the offline account → "Use local skin…"
3. Pick a 64×64 or 64×32 PNG and choose the Steve (classic) or Alex (slim) arm model in the dialog
4. Launch the game; CustomSkinLoader applies it automatically

## Sharing with other players
The "Skin Pack" tab bundles the skin, target player name and arm model into a `.zip`. When someone imports it, the skin is written to `CustomSkinLoader/LocalSkin/skins/<player name>.png`; only that player shows the skin on servers. The pack format is chosen automatically for the target version (`pack_format`, or `min_format`/`max_format` for 1.21.9+ / 26.x), with both the old and new player texture paths included; the exported `.zip` is itself a complete resource pack and can be dropped directly into `resourcepacks`.

## Notes
- The skin is written to `CustomSkinLoader/LocalSkin/skins/<player name>.png` and loaded per player name
- It only works when CustomSkinLoader is installed
- The fallback resource pack is not enabled by default, so other default-skin players on a server keep their own skins
- Official accounts do not need this — just upload the skin
""",
        "09_bedrock.md": """# Bedrock Edition

## Where packages come from
The Bedrock page lists packages in three groups: historical builds, Store release and Store preview. The catalog comes from the MCAPPX offline package index; nothing is bundled with the launcher.

## Installing
1. Open "Bedrock" and pick a version.
2. Some historical builds cannot be fetched programmatically; use "Download in browser" and the built-in Edge engine to open the page. Finished `.appx` / `.msix` files are archived automatically.
3. "Install" deploys the package with `Add-AppxPackage`. An 800 MB+ package on a hard disk can take many minutes; the progress bar shows "Deploying" — do not click again.
4. After installation a Bedrock entry appears in the launch menu for launching or uninstalling.

## Notes
- Installed-state detection normalizes the package version (e.g. 1.8.102.0) before matching the Store version; different numbering does not mean it is missing.
- Store packages are signed by Microsoft; uninstall through Windows "Apps" and your Java saves stay untouched.
""",
        "10_loaders.md": """# Loaders: Forge / NeoForge / Fabric / Quilt / LiteLoader / Forbric

## One-click install
1. Open "Download" and choose a Minecraft version.
2. Pick the loader and loader version under "Mod loader".
3. Click "Install selected version": the launcher downloads the matching installer and runs it as a child process.
4. The progress bar only moves forward, even when retries happen.

## Which one to pick
- **Forge** — biggest ecosystem, best for older modpacks, slower start.
- **NeoForge** — Forge fork and the main target for 1.20.2+.
- **Fabric** — lightweight and fast to update, best for Sodium/Lithium style mods.
- **Quilt** — Fabric derivative; most Fabric mods work.
- **LiteLoader** — old versions only, for a handful of mods such as minimaps.
- **Forbric** — experimental three-in-one bootstrap, only supported on specific versions (currently 26.2). The install button is disabled with a clear warning on unsupported versions.

## Standalone installers
"Content Center → Loader sources" downloads the raw installer / libraries, useful for offline installs and troubleshooting.

## Troubleshooting
- Installer exits non-zero: usually a Java major-version mismatch — install the right one from "Java Center".
- No generated version: check `versions/<version id>/<version id>.json`; loader detection matches loader-specific version prefixes so a vanilla folder is never mistaken for an installed loader.
""",
        "11_modpack.md": """# Importing, exporting and installing modpacks

## Importing
- Drop a `.zip` / `.mrpack` onto the window, or pick a file on the "Modpacks" page.
- The launcher downloads the matching vanilla version, installs the loader, then applies overrides and mods.
- Instance folders are named from a content digest, so importing the same pack again resumes instead of re-downloading.

## Backup formats
"Modpacks → Export" offers two formats:
- **CurseForge share format** — universal, works with other launchers.
- **Mikan private backup** — includes instance config, per-version settings and local extra files, ideal for migration or backup.

## If installation fails
1. The traceback is written to `data/logs/install_error.log` and the install log is copied to the clipboard.
2. Check free disk space (preflight requires >2 GB) and your network; switch mirrors under "Settings → Download sources".
3. Failed downloads retry automatically; if it still fails, cancel in the Download Center and re-import — completed files are kept.

## After success
`instance.json` is written, the instance is selected and the home list refreshes; choose mod / saves / full isolation under "Version settings".
""",
        "12_download_center.md": """# Download Center, acceleration and tasks

## Download Center
Every download (game versions, loaders, mods, modpacks, Java, Bedrock packages) shows up in the Download Center with:
- which files are needed and where they are saved;
- current speed, remaining size and progress;
- queued / downloading / verifying / installing / done / failed.

Tasks can be paused, resumed, cancelled and retried. Unfinished files keep their `.part` file and resume with HTTP Range requests.

## Acceleration
- The "Download acceleration" page switches mirrors (official / BMCLAPI etc.) and measures each source for the same file.
- Thread count lives in "Settings → Download"; every download is multi-threaded.
- A global speed limit keeps your connection usable.

## Floating button
While tasks are running a round floating button appears in the bottom-right corner: click to open the Download Center, right-click to go back. It hides when idle.

## Notes
Up to five versions install concurrently, and each target file is locked so tasks never overwrite each other's `.part` file.
""",
        "13_java_deps.md": """# Java Center and dependency completion

## Java Center
1. Aggregates Temurin, Microsoft, Azul, Corretto, Dragonwell and Kona, with mirrors.
2. Installs a small JRE or a full JDK and matches the Java major version your MC version needs.
3. Two install modes:
   - **ZIP portable** — extracted to `data/runtime`, added to the user PATH and environment change broadcast;
   - **Official installer** (EXE / MSI) — runs the vendor's own wizard.
4. Large files download in multi-threaded chunks and can be paused or cancelled in the Download Center.

## Dependency completion
The "Dependencies" page lists third-party pieces that cannot be bundled — Terracotta, authlib-injector, Java runtimes, loaders — and scans for missing pieces:
- scans Java, the client, libraries, assets and logs;
- asks before completing anything; nothing is changed silently.

## Rules of thumb
- Java 8 for 1.12.2 and older, Java 17 for 1.17–1.20.4, Java 21 for 1.20.5+.
- Keep memory below 70% of physical RAM; 32-bit Java cannot use large heaps.
""",
        "14_instances.md": """# Version folders, instances and importing from other launchers

## Multiple version folders
"Settings → Data folder" lets you register several version folders and switch with the top dropdown — e.g. vanilla, modpacks and snapshots in separate folders.

## Instances
- Double-click an instance on the home page to launch; select several to launch them one after another.
- "Version settings" stores memory, Java, window size, JVM args, isolation mode and process priority per instance.
- "Version settings → Launch script" runs custom commands before and after launch.

## Importing from PCL / HMCL
1. "Settings → Import from other launchers" → "Scan and import…", then pick the PCL2 / HMCL launcher folder (the one containing `.minecraft`).
2. Tick the versions to import and optionally bring their isolation, memory and JVM settings.
3. Import only registers versions; files are never copied or moved, and versions you already have are skipped.

## Notes
- Switching the version folder refreshes the home page and Download Center.
- Duplicate detection uses the real instance list, so imports never create duplicates.
""",
        "15_skin_factory.md": """# Skin Factory: pixel editing and 3D painting

## Editing
1. The 64×64 canvas includes the second layer and offers brush, eraser, fill, picker, mirror and per-part selection.
2. Switch to "3D painting" to paint directly on the model's head, body, arms or legs — both layers are editable.
3. The 3D preview rotates on both axes (yaw + pitch), zooms and pans; brush and mouse modes have separate buttons.
4. The canvas scrolls and has zoom buttons so the feet stay reachable in short windows.

## Saving and applying
- Saved as PNG under `data/skins`; nothing is uploaded.
- Apply to offline or third-party accounts directly; offline skins need CustomSkinLoader.
- Previously used skins go to a recent list, switchable from the sidebar avatar.

## Skin packs
The "Skin pack" page bundles the skin, player name, arm model (Steve / Alex), cape and elytra into a resource pack:
- picks `pack_format` or `min_format / max_format` for the target MC version (everything from the texture-pack era to the latest release);
- writes both the old and new player texture paths;
- clears old packs in the game folder before writing;
- newly installed versions import the offline skin pack automatically.
""",
        "16_seed_terrain.md": """# World seeds and 3D terrain preview

## Usage
1. Open "Seed / Terrain" and type a seed (numeric or text).
2. Choose an installed version under "Game version": 1.18+ uses the new climate noise with Xoroshiro128++, 1.7–1.17 uses the classic ImprovedNoise.
3. Click "Generate": the launcher runs a bundled heightmap program with your local Java and renders a 3D view around spawn.

## What matches vanilla
- The 256-entry permutation table is shuffled from the same random source and the gradient table is vanilla's 16 directions.
- Octave layering uses vanilla's fixed persistence 0.5 and lacunarity 2.
- The 1.18+ random source, frequencies and amplitudes match vanilla climate noise.

## What differs
Biomes, terrain splines and density functions are not included, so the shape is close but not identical to the in-game world. Use it to filter seeds; the game remains the source of truth.
""",
        "17_extensions_themes.md": """# Extensions, themes and the skin API

## Extensions
- Import `.zip` / `.mikan-ext` by dropping it on the window or via "Settings → Extensions".
- Enabled extensions appear in the sidebar and run inside a sandboxed iframe; they talk to the backend through `postMessage` and have no direct file access.
- Disable or remove at any time; data is kept so re-enabling is lossless.

## Themes
- Built-in themes include forest green, ocean blue, dusk purple, crimson, amber, teal, sakura pink and polar night, in light and dark variants.
- "Settings → Appearance" imports/exports `data/themes/*.json`, and a theme API registers custom skins.
- Imported skins and themes are remembered and shown first.

## Interface
- The sidebar uses a vertical tile layout with frosted-glass tiles and cards; glass strength and blur are continuously adjustable.
- The window resizes by dragging (min 960×600), maximizes on title-bar double-click and has rounded corners.
- Animated wallpapers support MP4 / WebM / GIF / WebP and pause when the window goes to the background.
""",
        "18_browser_tools.md": """# Built-in browser, multiplayer and utilities

## Built-in browser
- Uses the Edge WebView2 engine and plays Bilibili and other video sites natively — no need to jump to an external browser.
- If WebView2 is missing it falls back with an install prompt; you can also unpack a fixed runtime into the `webview2` folder next to the executable.

## Multiplayer
1. Add servers on the "Multiplayer" page; Server List Ping shows latency, player count, MOTD and icon.
2. Double-click a server to launch and join; install Terracotta from "Dependencies" to host or join rooms by code.

## Screenshot gallery
Reads `screenshots/` per instance: preview, zip, open folder and delete, entirely offline.

## Crash reports
Reads `data/logs/crashes` with summary, copy and delete; failed modpack installs also write a traceback to `data/logs/install_error.log`.

## NBT editor
Browses save and structure files as a typed tree, edits leaf tags, and writes a `.bak` before saving.

## Mod graph
"Content Center → Mod graph" shows required dependencies and conflicts inside an instance, with actionable items in red.

## Frosted-glass UI resource pack
1. Open the "Skin pack" page; the "Frosted-glass UI pack" card lists installed versions automatically.
2. Pick a version and press "Generate and install": button, text field, slider, inventory/chest panels,
   hotbar and menu background textures are taken from that version's client jar, converted into translucent
   frosted styling in place, written to resourcepacks/ and enabled in options.txt.
3. "Generate for all installed versions" packs each version with its own format (pack_format / min_format).
4. 1.0–1.5.2 produce texturepacks and must be selected under in-game "Texture Packs"; 1.6.1+ are auto-enabled.
5. The install folder follows your version isolation setting; "Export UI pack…" produces a shareable zip.
6. If the client jar is missing only the glass background layer is generated — install that version first.
""",
    },
    "ru_RU": {
        "01_install_forge.md": """# Установка Forge

## Что нужно
- Установлена соответствующая версия ванильного Minecraft
- Установлена Java 8 / 17 / 21 (в зависимости от версии MC)

## Шаги
1. Откройте страницу «Загрузки»
2. Выберите нужную версию Minecraft
3. В разделе «Загрузчики модов» выберите Forge
4. Выберите версию Forge (рекомендуется последняя стабильная)
5. Нажмите «Установить выбранную версию»

## Частые проблемы
- Застряло на «загрузка установщика»: проблема с сетью — включите зеркало BMCLAPI в настройках
- Установщик завершился с ненулевым кодом: обычно несовпадение версии Java, проверьте Java
- Созданная версия не найдена: проверьте, существует ли `versions/<ID версии>/<ID версии>.json`
""",
        "02_install_fabric.md": """# Установка Fabric

## Отличия от Forge
- Fabric легче и запускается быстрее
- Экосистема модов Fabric ориентирована на «новые версии + небольшие изменения»
- Большинство оптимизационных модов (Sodium, Lithium) сначала выходят для Fabric

## Шаги
1. Откройте страницу «Загрузки»
2. Выберите версию Minecraft
3. В качестве загрузчика выберите Fabric
4. Установите (Fabric API добавляется автоматически)

## Примечания
- Fabric API нужен большинству модов Fabric и устанавливается вместе с Fabric
- Quilt — форк Fabric, большинство модов Fabric работают и на Quilt
""",
        "03_install_shader.md": """# Установка шейдеров

## Что нужно
- Загрузчик: Iris для Fabric, Oculus для Forge
- Рекомендуется: OptiFine (старые версии) или Iris + Sodium (новые версии)

## Шаги
1. Найдите «Iris» или «Oculus» в Центре контента и установите в экземпляр
2. Положите набор шейдеров (.zip) в папку `shaderpacks/`
3. Запустите игру: Настройки → Графика → Шейдеры → выберите набор

## Производительность
- Шейдеры сильно нагружают видеокарту — на встроенной графике лучше не включать
- Предстартовая проверка предупредит о связке «встроенная графика + шейдеры»
""",
        "04_memory_issue.md": """# Нехватка памяти

## Симптомы
- Подтормаживания и просадки FPS
- В логе появляется OutOfMemoryError
- Предстартовая проверка сообщает «выделенная память превышает 70% физической»

## Решение
1. Откройте «Настройки версии» → «Настройки игры»
2. Задайте разумное значение «Максимум памяти»:
   - Ванилла: 2-4 ГБ
   - Лёгкие сборки: 4-6 ГБ
   - Крупные сборки: 6-8 ГБ
3. Не превышайте 70% физической памяти

## Примечания
- Больше памяти — не всегда лучше: избыток замедляет систему
- 32-битная Java может использовать только 1.5 ГБ — используйте 64-битную
""",
        "05_mod_conflict.md": """# Конфликты модов

## Симптомы
- Игра падает при запуске
- В логе NoSuchMethodError / ClassNotFoundException
- Предстартовая проверка сообщает «обнаружено N конфликтов модов»

## Диагностика
1. Откройте «Настройки версии» → «Моды»
2. Посмотрите на моды, помеченные красным (конфликтующие)
3. Типичные конфликты:
   - Один мод установлен в нескольких версиях (дублирующийся modid)
   - Отсутствует зависимость
   - Не подходит диапазон версий

## Решение
- Дублирующийся modid: отключите один из них
- Нет зависимости: найдите её в Центре контента и установите
- Несовпадение версий: обновите или откатите соответствующий мод
""",
        "06_java_version.md": """# Выбор версии Java

## Таблица соответствия

| Версия Minecraft | Версия Java |
|---|---|
| 1.0 - 1.16.5 | Java 8 |
| 1.17 - 1.20.4 | Java 17 |
| 1.20.5+ | Java 21 |

## Проверка текущей Java
- Настройки → Среда Java: список всех найденных Java
- Двойной клик по строке делает её версией по умолчанию

## Установка Java
- Откройте «Центр Java», выберите дистрибутив и основную версию, скачайте
- Рекомендуется Adoptium Temurin (самое большое сообщество)
""",
        "07_nbt_editor.md": """# Работа с редактором NBT

## Что такое NBT
NBT (Named Binary Tag) — формат данных сохранений Minecraft; `level.dat` и `playerdata/*.dat` — это NBT.

## Где открыть
- «🔧 Открыть редактор NBT» вверху Центра руководств
- Настройки версии → Управление версиями → «Редактировать level.dat»
- Кнопка «Редактор NBT…» в панели инструментов главной страницы

## Типичные задачи
- Сменить сид мира: измените `Data.WorldGenSettings.seed` в `level.dat`
- Сменить режим игры: измените `playerGameType` в `playerdata/<uuid>.dat`
- Сменить координаты: измените массив `Pos`

## Как редактировать
- Двойной клик по столбцу «Значение» редактирует листовые теги (строки / числа)
- Правый клик — «Добавить дочерний тег» или «Удалить тег» (корень удалить нельзя)
- Составные теги (TAG_Compound) можно только раскрывать, значение не меняется

## Безопасность
- При первом сохранении рядом создаётся резервная копия `.bak`
- Не трогайте поля, в которых не уверены
- При поломке восстановите из копии
""",
        "08_offline_skin.md": """# Скины для офлайн-аккаунтов

## Принцип
У офлайн-аккаунтов нет сервиса скинов Mojang, поэтому используется мод CustomSkinLoader и локальный файл скина.

## Шаги
1. Найдите «CustomSkinLoader» в Центре контента и установите в экземпляр
2. Откройте «Аккаунты» → выберите офлайн-аккаунт → «Использовать локальный скин…»
3. Выберите PNG 64×64 или 64×32
4. Запустите игру — CustomSkinLoader применит скин автоматически

## Примечания
- Скин записывается в `CustomSkinLoader/LocalSkin/skins/<имя игрока>.png`
- Работает только при установленном CustomSkinLoader
- Лицензионным аккаунтам это не нужно — просто загрузите скин
""",
    },
    "fr_FR": {
        "01_install_forge.md": """# Installer Forge

## Prérequis
- La version vanilla correspondante de Minecraft est déjà installée
- Java 8 / 17 / 21 est installé (à choisir selon la version de MC)

## Étapes
1. Ouvrez la page « Téléchargements »
2. Sélectionnez la version de Minecraft souhaitée
3. Choisissez Forge dans la section « Chargeurs de mods »
4. Sélectionnez une version de Forge (la dernière stable est recommandée)
5. Cliquez sur « Installer la version sélectionnée »

## Problèmes fréquents
- Bloqué sur « téléchargement de l'installateur » : problème réseau, activez le miroir BMCLAPI dans les paramètres
- Code de sortie non nul de l'installateur : souvent une version de Java incompatible, vérifiez Java
- Version générée introuvable : vérifiez que `versions/<ID de version>/<ID de version>.json` existe
""",
        "02_install_fabric.md": """# Installer Fabric

## Différences avec Forge
- Fabric est plus léger et démarre plus vite
- L'écosystème de mods Fabric privilégie « versions récentes + petites modifications »
- La plupart des mods d'optimisation (Sodium, Lithium) sortent d'abord sur Fabric

## Étapes
1. Ouvrez la page « Téléchargements »
2. Sélectionnez une version de Minecraft
3. Choisissez Fabric comme chargeur
4. Installez (Fabric API est ajouté automatiquement)

## Remarques
- Fabric API est requis par la plupart des mods Fabric et est installé avec Fabric
- Quilt est un fork de Fabric ; la plupart des mods Fabric fonctionnent sur Quilt
""",
        "03_install_shader.md": """# Installer des shaders

## Prérequis
- Chargeur : Iris pour Fabric, Oculus pour Forge
- Recommandé : OptiFine (anciennes versions) ou Iris + Sodium (versions récentes)

## Étapes
1. Recherchez « Iris » ou « Oculus » dans le Centre de contenu et installez-le dans l'instance
2. Placez le pack de shaders (.zip) dans le dossier `shaderpacks/`
3. Lancez le jeu, puis Options → Graphismes → Shaders → choisissez un pack

## Performances
- Les shaders sollicitent beaucoup le GPU — à éviter sur un chipset graphique intégré
- La vérification avant lancement avertit en cas de « GPU intégré + shaders »
""",
        "04_memory_issue.md": """# Manque de mémoire

## Symptômes
- Saccades et chutes de FPS
- OutOfMemoryError dans le journal
- La vérification avant lancement signale « mémoire allouée supérieure à 70 % de la RAM physique »

## Solution
1. Ouvrez « Paramètres de version » → « Paramètres du jeu »
2. Réglez « Mémoire maximale » à une valeur raisonnable :
   - Vanilla : 2-4 Go
   - Modpacks légers : 4-6 Go
   - Gros modpacks : 6-8 Go
3. Ne dépassez pas 70 % de la RAM physique

## Remarques
- Plus de mémoire n'est pas toujours mieux : un excès ralentit tout le système
- Java 32 bits ne peut utiliser que 1,5 Go — utilisez une version 64 bits
""",
        "05_mod_conflict.md": """# Conflits de mods

## Symptômes
- Le jeu plante au démarrage
- NoSuchMethodError / ClassNotFoundException dans le journal
- La vérification avant lancement signale « N conflits de mods détectés »

## Diagnostic
1. Ouvrez « Paramètres de version » → « Mods »
2. Repérez les mods marqués en rouge (les conflits)
3. Conflits courants :
   - Un même mod installé en plusieurs versions (modid en double)
   - Dépendance manquante
   - Version incompatible

## Solutions
- Modid en double : désactivez l'un des deux
- Dépendance manquante : recherchez-la dans le Centre de contenu et installez-la
- Version incompatible : mettez à jour ou rétrogradez le mod concerné
""",
        "06_java_version.md": """# Choisir une version de Java

## Tableau de correspondance

| Version de Minecraft | Version de Java |
|---|---|
| 1.0 - 1.16.5 | Java 8 |
| 1.17 - 1.20.4 | Java 17 |
| 1.20.5+ | Java 21 |

## Vérifier votre Java
- Paramètres → Runtimes Java liste tous les Java détectés
- Double-cliquez sur une ligne pour la définir par défaut

## Installer Java
- Ouvrez le « Centre Java », choisissez une distribution et une version majeure, puis téléchargez
- Adoptium Temurin est recommandé (communauté la plus large)
""",
        "07_nbt_editor.md": """# Utiliser l'éditeur NBT

## Qu'est-ce que le NBT
Le NBT (Named Binary Tag) est le format des sauvegardes de Minecraft ; `level.dat` et `playerdata/*.dat` sont du NBT.

## Où l'ouvrir
- « 🔧 Ouvrir l'éditeur NBT » en haut du Centre de guides
- Paramètres de version → Gestion des versions → « Modifier level.dat »
- Le bouton « Éditeur NBT… » dans la zone d'outils de l'accueil

## Usages courants
- Changer la graine du monde : modifiez `Data.WorldGenSettings.seed` dans `level.dat`
- Changer le mode de jeu : modifiez `playerGameType` dans `playerdata/<uuid>.dat`
- Changer les coordonnées : modifiez le tableau `Pos`

## Utilisation
- Double-cliquez sur la colonne « Valeur » pour éditer un tag feuille (chaîne / nombre)
- Clic droit pour ajouter un tag enfant ou supprimer un tag (la racine n'est pas supprimable)
- Les tags composés (TAG_Compound) ne peuvent qu'être dépliés, pas édités directement

## Sécurité
- La première sauvegarde crée automatiquement une copie `.bak`
- Ne touchez pas aux champs dont vous n'êtes pas sûr
- Restaurez depuis la copie en cas de problème
""",
        "08_offline_skin.md": """# Skins hors ligne

## Principe
Les comptes hors ligne n'ont pas de service de skins Mojang ; on utilise donc le mod CustomSkinLoader avec un fichier de skin local.

## Étapes
1. Recherchez « CustomSkinLoader » dans le Centre de contenu et installez-le dans l'instance
2. Ouvrez « Comptes » → sélectionnez le compte hors ligne → « Utiliser un skin local… »
3. Choisissez un PNG 64×64 ou 64×32
4. Lancez le jeu, CustomSkinLoader l'applique automatiquement

## Remarques
- Le skin est écrit dans `CustomSkinLoader/LocalSkin/skins/<nom du joueur>.png`
- Cela ne fonctionne qu'avec CustomSkinLoader installé
- Les comptes officiels n'en ont pas besoin : téléversez simplement le skin
""",
    },
    "ja_JP": {
        "01_install_forge.md": """# Forge のインストール

## 前提
- 対応するバージョンのバニラ Minecraft がインストール済み
- Java 8 / 17 / 21 のいずれかがインストール済み（MC のバージョンに合わせる）

## 手順
1. 「ダウンロード」ページを開く
2. 対象の Minecraft バージョンを選ぶ
3. 「Mod ローダー」で Forge を選ぶ
4. Forge のバージョンを選ぶ（最新の安定版を推奨）
5. 「選択したバージョンをインストール」をクリック

## よくある問題
- 「インストーラーのダウンロード」で止まる：ネットワークの問題です。設定で BMCLAPI ミラーを有効にしてください
- インストーラーの終了コードが 0 以外：多くの場合 Java バージョンの不一致です。Java を確認してください
- 生成されたバージョンが見つからない：`versions/<バージョンID>/<バージョンID>.json` の有無を確認してください
""",
        "02_install_fabric.md": """# Fabric のインストール

## Forge との違い
- Fabric はより軽量で起動が速い
- Fabric の Mod エコシステムは「新バージョン＋小さな改変」寄り
- 最適化系 Mod（Sodium、Lithium）の多くは Fabric が先行

## 手順
1. 「ダウンロード」ページを開く
2. Minecraft バージョンを選ぶ
3. ローダーで Fabric を選ぶ
4. インストール（Fabric API も自動で入ります）

## 注意
- Fabric API は多くの Fabric Mod の前提で、Fabric と一緒にインストールされます
- Quilt は Fabric の派生で、多くの Fabric Mod が Quilt でも動作します
""",
        "03_install_shader.md": """# シェーダーのインストール

## 前提
- ローダー：Fabric なら Iris、Forge なら Oculus
- 推奨：OptiFine（旧バージョン）または Iris + Sodium（新バージョン）

## 手順
1. 「コンテンツセンター」で「Iris」または「Oculus」を検索し、インスタンスにインストール
2. シェーダーパック（.zip）を `shaderpacks/` フォルダに入れる
3. ゲームを起動し、オプション → ビデオ設定 → シェーダー → パックを選択

## パフォーマンス
- シェーダーは GPU 負荷が高いため、内蔵 GPU では控えめに
- 起動前チェックで「内蔵 GPU ＋ シェーダー」を検出すると警告が出ます
""",
        "04_memory_issue.md": """# メモリ不足

## 症状
- カクつきやフレーム落ち
- ログに OutOfMemoryError が出る
- 起動前チェックで「割り当てメモリが物理メモリの 70% を超えています」と表示

## 対処
1. 「バージョン設定」→「ゲーム設定」を開く
2. 「最大メモリ」を適切な値にする：
   - バニラ：2-4 GB
   - 軽量 Mod：4-6 GB
   - 大型 Mod パック：6-8 GB
3. 物理メモリの 70% を超えないこと

## 注意
- メモリは多いほど良いわけではなく、過剰だとシステム全体が遅くなります
- 32 ビット Java は最大 1.5 GB しか使えません。64 ビットを使用してください
""",
        "05_mod_conflict.md": """# Mod の競合

## 症状
- 起動時にクラッシュする
- ログに NoSuchMethodError / ClassNotFoundException が出る
- 起動前チェックで「N 件の Mod 競合を検出」と表示

## 切り分け
1. 「バージョン設定」→「Mod 管理」を開く
2. 赤く表示された Mod（競合項目）を確認
3. よくある競合：
   - 同じ Mod が複数バージョン入っている（modid の重複）
   - 前提 Mod の不足
   - バージョン範囲の不一致

## 対処
- modid の重複：どちらかを無効化
- 前提 Mod の不足：コンテンツセンターで前提名を検索してインストール
- バージョン不一致：該当 Mod を更新またはダウングレード
""",
        "06_java_version.md": """# Java バージョンの選び方

## 対応表

| Minecraft バージョン | Java バージョン |
|---|---|
| 1.0 - 1.16.5 | Java 8 |
| 1.17 - 1.20.4 | Java 17 |
| 1.20.5+ | Java 21 |

## 現在の Java を確認
- 設定 → Java ランタイムに検出された Java が一覧表示されます
- 行をダブルクリックすると既定に設定されます

## Java のインストール
- 「Java センター」でディストリビューションとメジャーバージョンを選んでダウンロード
- Adoptium Temurin を推奨（コミュニティが最も大きい）
""",
        "07_nbt_editor.md": """# NBT エディターの使い方

## NBT とは
NBT（Named Binary Tag）は Minecraft のセーブデータ形式で、`level.dat` や `playerdata/*.dat` が NBT です。

## 開き方
- チュートリアル上部の「🔧 NBT エディターを開く」
- バージョン設定 → バージョン管理 → 「level.dat を編集」
- ホームのツール欄にある「NBT エディター…」

## よくある用途
- ワールドシードの変更：`level.dat` の `Data.WorldGenSettings.seed` を編集
- ゲームモードの変更：`playerdata/<uuid>.dat` の `playerGameType` を編集
- 座標の変更：`Pos` 配列を編集

## 操作方法
- 「値」列をダブルクリックするとリーフタグ（文字列 / 数値）を編集できます
- 右クリックで子タグの追加やタグの削除ができます（ルートは削除不可）
- 複合タグ（TAG_Compound）は展開のみで、値の直接編集はできません

## 安全上の注意
- 初回保存時に同じフォルダへ `.bak` バックアップが自動作成されます
- 不確かなフィールドは触らないでください
- 壊れた場合はバックアップから復元できます
""",
        "08_offline_skin.md": """# オフラインスキン

## 仕組み
オフラインアカウントには Mojang のスキンサービスがないため、CustomSkinLoader Mod とローカルのスキンファイルで再現します。

## 手順
1. 「コンテンツセンター」で「CustomSkinLoader」を検索し、インスタンスにインストール
2. 「アカウント」→ オフラインアカウントを選択 → 「ローカルスキンを使用…」
3. 64×64 または 64×32 の PNG を選ぶ
4. ゲームを起動すると CustomSkinLoader が自動で適用します

## 注意
- スキンは `CustomSkinLoader/LocalSkin/skins/<プレイヤー名>.png` に書き込まれます
- CustomSkinLoader を入れている場合のみ有効になります
- 正規アカウントには不要です。そのままスキンをアップロードしてください
""",
    },
}

# 目录里没有对应语言时回退到默认语言
FALLBACK_LANGUAGE = DEFAULT_LANGUAGE


def _language_docs(lang: str) -> tuple[str, dict[str, str]]:
    """返回 (实际使用的语言目录, 该语言的默认教程)。"""
    if lang in DEFAULT_WIKI:
        return lang, DEFAULT_WIKI[lang]
    return FALLBACK_LANGUAGE, DEFAULT_WIKI[FALLBACK_LANGUAGE]


def _migrate_legacy_docs() -> None:
    """旧版把中文教程直接放在 data/wiki 下，这里迁移到 zh_CN 子目录。"""
    try:
        legacy = [path for path in WIKI_DIR.glob("*.md") if path.is_file()]
    except OSError:
        return
    if not legacy:
        return
    target_dir = WIKI_DIR / FALLBACK_LANGUAGE
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for path in legacy:
        target = target_dir / path.name
        if target.exists():
            continue
        try:
            path.rename(target)
        except OSError:
            continue


def ensure_default_wiki(lang: str = DEFAULT_LANGUAGE) -> str:
    """补齐该语言的内置教程（不覆盖用户自定义文件），返回实际使用的语言目录名。"""
    _migrate_legacy_docs()
    code, docs = _language_docs(lang)
    target_dir = WIKI_DIR / code
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return code
    for name, content in docs.items():
        target = target_dir / name
        if target.exists():
            continue
        try:
            target.write_text(content, encoding="utf-8")
        except OSError:
            continue
    return code


def _titles_from_file(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text.startswith("#"):
                return text.lstrip("#").strip()
    except OSError:
        pass
    return path.stem


# 文件名非法字符（Windows 保留字符 + 路径分隔符）
_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')


def _sanitize_title(title: str) -> str:
    """把教程标题清洗成安全文件名片段（非法字符转下划线，最长 40 字符）。"""
    name = _INVALID_FILENAME_CHARS.sub("_", title or "")
    name = " ".join(name.split()).strip(" .")
    return name[:40]


def _open_local_file(path: Path) -> None:
    """用系统默认程序打开本地文件（Windows 优先 os.startfile）。"""
    startfile = getattr(os, "startfile", None)
    if sys.platform.startswith("win") and callable(startfile):
        try:
            startfile(str(path))
            return
        except OSError:
            pass
    try:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    except Exception:  # noqa: BLE001 - 打开失败不影响新建结果
        pass


class WikiPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._entries: list[tuple[Path, str, str]] = []
        self._lang = ""
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)

        header, header_layout = page_header(
            self.tr("教程中心"), self.tr("内置攻略 Wiki：安装、排错与 NBT 编辑说明")
        )
        nbt_button = QPushButton(self.tr("🔧 打开 NBT 编辑器"))
        nbt_button.setObjectName("Chip")
        nbt_button.clicked.connect(self._open_nbt_editor)
        header_layout.addWidget(nbt_button)
        self.new_button = QPushButton(self.tr("✚ 新建教程"))
        self.new_button.setObjectName("Chip")
        self.new_button.clicked.connect(self._new_doc)
        header_layout.addWidget(self.new_button)
        outer.addWidget(header)

        card = Card(margins=14, spacing=10)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("搜索教程标题或内容…"))
        self.search_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search_edit, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Tiny")
        search_row.addWidget(self.count_label)
        card.body.addLayout(search_row)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.catalog = QListWidget()
        self.catalog.setFixedWidth(240)
        self.catalog.currentItemChanged.connect(self._on_item_changed)
        body.addWidget(self.catalog)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_anchor_clicked)
        body.addWidget(self.browser, 1)
        card.body.addLayout(body, 1)

        outer.addWidget(card, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """按当前界面语言重新加载教程目录（语言切换需重启启动器）。"""
        lang = str(getattr(self.ctx.config, "language", "") or DEFAULT_LANGUAGE)
        self._lang = ensure_default_wiki(lang)
        folder = WIKI_DIR / self._lang
        entries: list[tuple[Path, str, str]] = []
        try:
            files = sorted(folder.glob("*.md"))
        except OSError:
            files = []
        for path in files:
            title = _titles_from_file(path)
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                content = ""
            entries.append((path, title, content))
        self._entries = entries
        self._rebuild_catalog()

    def _rebuild_catalog(self) -> None:
        keep = self.catalog.currentRow()
        self.catalog.blockSignals(True)
        self.catalog.clear()
        for index, (_path, title, _content) in enumerate(self._entries):
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, index)
            self.catalog.addItem(item)
        self.catalog.blockSignals(False)
        self._apply_filter(self.search_edit.text())
        if self._entries:
            row = keep if 0 <= keep < self.catalog.count() else 0
            self.catalog.setCurrentRow(row)

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        visible = 0
        for index in range(self.catalog.count()):
            item = self.catalog.item(index)
            data_index = item.data(Qt.UserRole)
            _path, title, content = self._entries[data_index]
            match = (
                not needle
                or needle in title.lower()
                or needle in content.lower()
            )
            item.setHidden(not match)
            if match:
                visible += 1
        self.count_label.setText(
            self.tr("{0} / {1} 篇").format(visible, len(self._entries))
        )
        if visible == 0:
            self.browser.setHtml(
                f"<p style='color:#8aa192'>{self.tr('没有匹配的教程')}</p>"
            )

    def _on_item_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            return
        data_index = current.data(Qt.UserRole)
        if not isinstance(data_index, int) or not (0 <= data_index < len(self._entries)):
            return
        _path, _title, content = self._entries[data_index]
        self.browser.setMarkdown(content)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return
        fragment = url.fragment()
        if fragment:
            self.browser.scrollToAnchor(fragment)
            return
        target = url.toString()
        if target:
            QDesktopServices.openUrl(QUrl(target))

    def _open_nbt_editor(self) -> None:
        dialog = NbtEditorDialog(self.ctx, self)
        dialog.exec()

    # ------------------------------------------------------------------
    def _current_lang(self) -> str:
        lang = str(getattr(self.ctx.config, "language", "") or DEFAULT_LANGUAGE)
        return ensure_default_wiki(lang)

    def _create_doc(self, title: str) -> Path:
        """按标题在当前语言目录新建 Markdown 教程，返回文件路径。"""
        lang = self._lang or self._current_lang()
        folder = WIKI_DIR / lang
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_sanitize_title(title)}"
        path = folder / f"{stem}.md"
        index = 1
        while path.exists():
            path = folder / f"{stem}_{index}.md"
            index += 1
        path.write_text(f"# {title.strip()}\n\n", encoding="utf-8")
        return path

    def _new_doc(self) -> None:
        title, ok = QInputDialog.getText(self, self.tr("新建教程"), self.tr("教程标题："))
        if not ok:
            return
        title = (title or "").strip()
        if not title:
            QMessageBox.warning(
                self, self.tr("标题不能为空"), self.tr("请输入教程标题后再创建。")
            )
            return
        try:
            path = self._create_doc(title)
        except OSError as exc:
            QMessageBox.warning(
                self, self.tr("新建教程失败"), self.tr("写入文件失败：{0}").format(exc)
            )
            return
        _open_local_file(path)
        self.refresh()
        self._select_path(path)

    def _select_path(self, path: Path) -> None:
        self.search_edit.clear()
        for index, (entry_path, _title, _content) in enumerate(self._entries):
            if entry_path == path:
                self.catalog.setCurrentRow(index)
                return

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """教程页没有后台任务，保留接口供 MainWindow 统一调用。"""
