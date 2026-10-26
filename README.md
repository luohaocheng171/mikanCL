# MikanCL v4.0.1 官方文档

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-Qt6-brightgreen.svg)](https://www.qt.io/)
[![License](https://img.shields.io/badge/License-待定-lightgrey.svg)](#许可证)

**MikanCL** — 正版登录 + 外置登录 + 5 大加载器一键安装 + Modrinth/CurseForge 内容中心 + 整合包管理 + Java 中心 + 启动预检

*AI 辅助开发工具：DeepSeek*

</div>

---

## 项目概述

MikanCL 是一款面向 Windows 的 Minecraft 启动器，采用 **PySide6（Qt6）** 构建深色主题界面，目录结构兼容 HMCL / PCL 的常见习惯。项目以**单文件可执行程序**为目标，可通过 PyInstaller 打包为 `MikanCL.exe`，双击即用，无需 Python 环境。

启动器按**实例（Instance）**组织游戏：每个实例绑定一个 Minecraft 版本与一个可选加载器，可独立配置 Java、内存、JVM 参数、隔离策略与 Mod 列表；整合包导入后自动成为独立实例，互不干扰。

### 版本信息

- **当前版本**：v4.0.1
- **框架**：PySide6（Qt6，Fusion 深色主题 + 自绘标题栏）
- **Python 要求**：3.10+
- **运行平台**：Windows 10 / 11（x64）
- **Mod 加载器**：5 款主流加载器 + 1 款实验性加载器（Forbric）
- **账号体系**：微软正版 / 外置登录（authlib-injector）/ 离线账号
- **内容平台**：Modrinth、CurseForge（内置默认 API Key，可替换）
- **下载源**：Mojang 官方源、BMCLAPI 镜像、自定义源（可增删、可排序）
- **许可证**：待定（见[许可证](#许可证)章节）

---

## 核心功能特性

### 基础功能

- **版本管理**：原版版本下载与安装、版本列表双击启动、多版本同时安装、版本重命名/删除
- **下载中心**：独立任务页，统一管理原版安装、加载器安装、整合包、内容下载、Java 下载、纯文件下载等任务，支持暂停 / 恢复 / 取消 / 重试 / 打开目录
- **版本隔离**：不隔离、仅隔离模组、仅隔离存档、全部隔离（独立游戏目录）四种模式，可按版本单独覆盖
- **数据目录**：支持添加多个 `.minecraft` 目录，通过侧边栏下拉框快速切换
- **多线程下载**：线程数可配置（默认 64），所有任务共用同一套并发与调度策略
- **日志与诊断**：界面日志同步落盘 `data/logs/launcher.log`（5MB × 3 轮转）；安装失败时额外写入 `data/logs/install_error.log` 并自动复制日志到剪贴板
- **单实例保护**：基于 QSharedMemory，避免两个进程同时读写配置与浏览器缓存

### 启动与运行

- **启动预检（Preflight）**：启动前检查 Java 版本是否匹配所需主版本、分配内存是否 ≤ 物理内存 70%、`mods/` 是否存在冲突、磁盘剩余空间是否 > 2GB、集成显卡 + 光影包组合是否警告；关键项失败可弹窗确认后仍强制启动
- **多选启动**：在主页勾选多个版本后按顺序依次启动，支持中途停止队列
- **进程优先级**：启动游戏时可设置进程优先级（低 / 正常 / 高 / 实时）
- **启动后行为**：隐藏启动器、关闭启动器、保持打开等可选；可配置游戏退出后是否保留启动器
- **自动连接服务器**：启动时自动进入配置好的服务器地址
- **代理支持**：HTTP 代理可同时应用于下载与游戏 JVM 参数
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
- **实例注册**：安装成功后写入 `instance.json`、自动选中实例、刷新主页版本列表

### 账号与皮肤

- **微软正版登录**：设备码（Device Code）OAuth 流程，自动刷新令牌
- **外置登录**：基于 authlib-injector，支持任意皮肤站 / 外置登录服务器；自动下载并注入 `authlib-injector.jar`
- **离线账号**：自定义玩家名，生成离线 UUID
- **皮肤管理**：正版皮肤查询、按用户名查找皮肤、上传皮肤；离线皮肤支持 Steve / Alex 手臂模型，写入 `CustomSkinLoader/LocalSkin/skins`，游戏内显示需搭配 CustomSkinLoader Mod

### 扩展与实验性功能

- **内置浏览器**：QtWebEngine 内置页面，便于查看 MC 百科、Mod 页面、皮肤站
- **Java 中心**：Adoptium Temurin、Microsoft OpenJDK、Azul Zulu、Amazon Corretto、Alibaba Dragonwell、Tencent Kona 六大发行版，按主版本（8 / 11 / 17 / 21）下载安装，自动解压到 `data/` 并在设置中选中
- **Forbric 引导式安装**：实验性 Fabric/Forge/NeoForge 三合一加载器，通过 GitHub Releases 自动获取最新安装器与 `Forbric-Installer.bat`，用 Java 21 拉起官方 GUI，后台轮询 `versions/26.2-forbric/26.2-forbric.json`，生成后自动注册实例

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

- **扫描**：注册表 + 常见安装路径（`Program Files\Java`、`Program Files\Eclipse Adoptium`、`%LOCALAPPDATA%\Programs` 等）+ 启动器自管目录
- **匹配**：`pick_java()` 优先完全匹配所需主版本，其次取高于需求的最近版本，最后回退任意可用 Java
- **下载**：`download_java()` 支持 `on_bytes` 进度回调、取消与暂停，解压后返回可执行路径；Java 中心统一登记到下载中心，可暂停 / 取消 / 重试

### 8. 单实例、落盘与退出

- `QSharedMemory` 实现单实例；重复启动时提示已运行
- 配置采用防抖写盘，退出时通过 `QApplication.aboutToQuit` 绑定 `final_save()` 强制落盘 `config.json` 与 `accounts.json`，避免数据丢失
- 打包版启动时将工作目录重定向到 exe 所在目录，`data/` 在同目录自动生成
- 退出阶段跳过 Qt/Python 析构，避免后台线程尚未收尾时崩溃

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
| `mc_launcher/auth.py` | 账号存储、微软设备码登录、外置登录、皮肤查询 / 上传 / 本地皮肤 |
| `mc_launcher/content.py` | Modrinth / CurseForge 客户端、整合包解析与安装、Mod 元数据扫描与冲突检测 |
| `mc_launcher/downloads.py` | 下载中心任务模型与调度（并发上限、暂停 / 恢复 / 取消 / 重试） |
| `mc_launcher/java.py` | Java 探测、版本匹配、Java 下载与解压 |
| `mc_launcher/forbric.py` | Forbric 安装器获取 / 下载 / 启动、版本结果轮询 |
| `mc_launcher/context.py` | `AppContext`（配置 / 源 / 账号 / 内容 / 下载中心）与 `AppBus`（日志、提示、事件） |
| `mc_launcher/version.py` | 版本清单缓存与版本列表筛选 |
| `mc_launcher/ui/*` | 各功能页面、公共控件、主题与图标绘制 |

### 页面一览

| 页面 | 类 | 能力 |
| :--- | :--- | :--- |
| 启动游戏 | `HomePage` | 版本列表、双击 / 多选启动、启动预检、拖拽导入、整合包快速入口 |
| 下载安装 | `DownloadPage` | 原版版本安装、加载器安装、加载器源文件另存为、仅下载客户端 Jar |
| 下载中心 | `DownloadCenterPage` | 任务表格、进度 / 速度 / 状态、暂停 / 恢复 / 取消 / 重试 / 打开目录 |
| 内容中心 | `ContentPage` | Modrinth / CurseForge 搜索、详情、安装到实例、另存为 |
| 整合包 | `ModpackPage` | 已装整合包列表、导入、导出（CF 格式 / `.mikan`）、删除 |
| 账号管理 | `AccountsPage` | 三种登录方式、账号切换、皮肤管理 |
| 版本设置 | `ControlPage` | 单版本 Java / 内存 / 参数 / 隔离、Mod 管理、资源包、光影、存档、日志 |
| 内置浏览器 | `BrowserPage` | QtWebEngine 浏览页 |
| Forbric | `ForbricPage` | 版本兼容拦截、安装器下载与 GUI 启动、结果监控 |
| Java 中心 | `JavaCenterPage` | 六大 Java 发行版下载与安装 |
| 设置 | `SettingsPage` | 数据目录、下载源、线程数、代理、API Key、镜像、界面选项 |

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
│   ├── java.py                  # Java 探测与下载
│   ├── forbric.py              # Forbric
│   ├── context.py              # 应用上下文
│   ├── version.py              # 版本清单
│   └── ui/                     # 界面层
│       ├── main_window.py      # 主窗口 / 导航 / 托盘 / 拖拽
│       ├── theme.py            # 深色主题、图标与头像绘制
│       ├── widgets.py          # 公共控件
│       ├── page_home.py        # 启动游戏
│       ├── page_download.py    # 下载安装
│       ├── page_download_center.py
│       ├── page_content.py     # 内容中心
│       ├── page_modpack.py     # 整合包
│       ├── page_accounts.py    # 账号与皮肤
│       ├── page_control.py     # 版本设置 / Mod 管理
│       ├── page_browser.py     # 内置浏览器
│       ├── page_forbric.py     # Forbric（+ forbric_worker.py）
│       ├── page_java_center.py # Java 中心
│       ├── page_settings.py    # 设置
│       ├── page_loader.py      # 页面懒加载
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
│   └── browser/                # QtWebEngine profile
└── dist/                       # 打包产物（MikanCL.exe）
```

---

## 技术栈与依赖

### 核心依赖

| 依赖 | 说明 |
| :--- | :--- |
| PySide6 ≥ 6.6 | Qt6 Python 绑定（含 QtWebEngine 内置浏览器） |

### 标准库

`urllib`（HTTP / Range 下载）、`zipfile` / `tarfile`（整合包与安装器解压）、`concurrent.futures`（多线程下载）、`threading`（暂停 / 取消）、`subprocess` + `ctypes`（安装器与内存检测）、`json`（全部配置持久化）。

### 运行时依赖

| 依赖 | 说明 |
| :--- | :--- |
| Java 8 / 11 / 17 / 21 | 由版本 JSON 与加载器决定，可在 Java 中心下载 |
| Visual C++ Redistributable | 部分加载器安装器与游戏运行需要 |
| CustomSkinLoader（可选 Mod） | 让离线皮肤在游戏内生效 |

---

## 运行与打包说明

### 方式一：已打包 exe（推荐）

1. 下载 `MikanCL.exe` 放到任意目录
2. 双击运行，程序会在 exe 同目录自动创建 `data/` 保存配置与缓存
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

产物位于 `dist/MikanCL.exe`，单文件、免安装。

---

## 注意事项

1. **首次使用建议顺序**：设置 → 选择 Java（或用 Java 中心下载）→ 下载安装原版版本 → 按需安装加载器 → 启动
2. **内存设置**：建议不超过物理内存的 70%，启动预检会提示超限；整合包体积较大时请确认磁盘空间 > 2GB
3. **整合包安装耗时**：首次安装需要完整下载对应版本的库文件与 3000+ 资源文件，进度可在下载中心查看；中途取消不会丢失已下载分片，重新导入会续传
4. **Mod 冲突**：同一 Mod 的多个版本同时存在会导致游戏崩溃，版本设置中会红色标记，建议只保留一个
5. **离线皮肤**：需要把 CustomSkinLoader Mod 放入实例的 `mods/`，皮肤文件写入 `CustomSkinLoader/LocalSkin/skins` 后才会在游戏内显示
6. **Forbric**：实验性功能，底层构建只支持特定 MC 版本（当前 26.2），不兼容的实例会禁用安装按钮；安装过程需要 Java 21
7. **CurseForge API Key**：内置默认 Key 可能随时失效，可在设置中替换为自己的 Key
8. **下载源**：国内网络建议把 BMCLAPI 镜像优先级调高；CurseForge / Modrinth 也支持自定义镜像地址
9. **单实例限制**：同一时间只能运行一个 MikanCL；如需切换数据目录，请使用侧边栏的数据目录下拉框
10. **杀毒软件**：PyInstaller 打包的 exe 常被误报，加入白名单即可

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

`ui/theme.py` 提供全局 `STYLESHEET`、`make_block_icon()`（应用 / 标题栏图标）、`make_nav_icon()`（侧边栏图标）、`make_avatar()`（离线头像）。新增导航项时若没有专属图标分支，会自动回退到默认方块图标。

---

## 许可证

本项目尚未指定开源许可证。如需开源发布，请自行添加 `LICENSE` 文件（例如 GPL-3.0 或 MIT）并更新本章节与顶部徽章。

**法律声明**：MikanCL 仅提供版本下载、启动与内容管理的客户端功能，不包含任何 Minecraft 游戏本体、Mod 二进制文件或账号凭据。Minecraft 为 Mojang / Microsoft 的商标与版权作品，请通过正版渠道购买与使用；Mod、整合包、资源包、光影包的版权归各自作者所有，请遵守其授权协议。

---

## 项目地址

`https://github.com/<your-name>/MikanCL`（请替换为实际仓库地址）

---

## 致谢

- **DeepSeek** — AI 辅助开发工具
- **PySide6 / Qt6** — 跨平台 GUI 框架
- **Mojang / Microsoft** — Minecraft 版本清单与官方下载源
- **BMCLAPI** — 国内下载镜像加速
- **HMCL / PCL2** — 功能设计与交互参考
- **Modrinth / CurseForge** — 内容平台与整合包生态
- **Forge / NeoForge / Fabric / Quilt / LiteLoader** — Mod 加载器
- **Forbric** — 实验性三合一加载器
- **Adoptium / Microsoft / Azul / Amazon / Alibaba / Tencent** — Java 运行时发行版
- **CustomSkinLoader** — 离线皮肤加载
- **authlib-injector** — 外置登录
