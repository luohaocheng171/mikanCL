# MikanCL

> 正版 / 外置登录 · Mod 生态 · 全能控制台

MikanCL 是一个用 Python + PySide6（Qt 6）编写的 Minecraft 启动器，界面为深色中文风格，目录结构兼容 HMCL / PCL，开源、单文件打包即可分发。

- 版本：2.0.0
- 运行平台：Windows 10 / 11
- 技术栈：Python 3.10+、PySide6 6.6+、QtWebEngine

---

## 功能特性

### 账号
- 微软正版登录（OAuth 2.0 设备码流程，无需输入密码）
- 离线账号（自动生成离线 UUID，支持昵称修改）
- 第三方外置登录（authlib-injector，兼容各类皮肤站）
- 账号令牌本地加密保存，支持刷新登录状态
- 主页头像点击即可切换账号，无需进入账号页

### 版本与加载器
- 原版游戏下载、安装、修复与删除
- 一键安装 **Forge / NeoForge / Fabric / Quilt / LiteLoader**，可选 OptiFine
- 自动检测本机 Java，支持按版本自动下载所需 Java
- 安装失败自动提示，日志可一键复制反馈

### 内容中心（Modrinth + CurseForge）
- 搜索并下载 **Mod、整合包、资源包、光影包**
- 支持按 Minecraft 版本 / 加载器过滤
- 详情页懒加载：先列版本，点击后再加载对应文件，避免大量 Mod 卡顿
- 支持为所有下载渠道配置镜像站与 API 地址（含内置 CurseForge API Key）

### 下载中心
- 所有下载任务统一查看：名称、类型、状态、进度、速度、剩余时间
- 支持 **暂停 / 恢复 / 取消 / 重试 / 打开目录**
- 多线程并发下载（线程数可配置）
- 断点续传（`.part` 文件 + HTTP Range），网络中断后可继续

### 整合包
- 拖拽导入 `.zip`、`.mrpack`、`manifest.json`、`.mikan`
- 安装后自动写入 `instance.json`、选中实例并刷新版本列表
- `.mikan` 为启动器私有备份格式，可完整恢复原实例（加载器版本、内存、窗口标题、JVM 参数）
- 可把当前实例导出为 CurseForge 整合包（分享用）或 `.mikan`（备份用）
- 安装失败：`traceback` 写入 `data/logs/install_error.log`，安装日志自动复制到剪贴板

### 游戏控制台
- Mod / 资源包 / 光影包 / 存档 的启用、禁用、删除、导入
- 资源包加载顺序上移 / 下移（写回 `options.txt`）
- 光影包页读取 Iris / OptiFine 配置，标记当前使用的光影
- Mod 更新检测与一键更新
- 自定义 JVM 参数、游戏参数、内存、分辨率
- 游戏进程优先级、自定义窗口标题、代理设置
- 启动后可选隐藏或关闭启动器

### 皮肤
- 正版账号：搜索并上传皮肤，3D 预览
- 离线账号：选择本地皮肤，写入 `CustomSkinLoader/LocalSkin`
- 支持 Steve / Alex（纤细）两种手臂模型，兼容 64x32 旧皮肤

### 其他
- 多数据目录切换，可添加 / 删除数据目录
- 版本隔离：不隔离 / 仅 Mod / 仅存档 / 全部隔离
- 服务器管理：延迟与在线人数显示（结果缓存 5 分钟）、启动后自动连接
- 无边框自绘标题栏，支持托盘运行
- 单实例保护，避免多开争用配置目录
- 日志落盘：`data/logs/launcher.log`（5MB × 3 轮转）
- 崩溃日志归档：`data/logs/crashes/`
- 所有设置项以 JSON 持久化，高频修改自动合并写盘

---

## 快速开始

### 源码运行

```bash
git clone https://github.com/<your-name>/MikanCL.git
cd MikanCL
pip install -r requirements.txt
python run.py
```

或双击 `启动.bat`。

### 打包为单文件 exe

```bash
python build_exe.py
```

产物为 `dist/MikanCL.exe`（PyInstaller `--onefile --windowed`）。
打包版首次运行会在 exe 同目录自动创建 `data/`，工作目录会自动重定向到 exe 所在目录。

---

## 目录结构

```
MikanCL/
├── run.py                  # 启动入口
├── build_exe.py            # 一键 PyInstaller 打包脚本
├── requirements.txt
├── assets/                 # 图标等静态资源
├── mc_launcher/
│   ├── main.py             # 应用初始化、单实例、日志落盘、退出落盘
│   ├── config.py           # 配置、实例、数据目录、实例清单（instance.json）
│   ├── auth.py             # 离线 / 微软正版 / 外置登录、皮肤
│   ├── net.py              # HTTP、镜像源、多线程下载、断点续传
│   ├── installer.py        # 版本安装与批量下载
│   ├── modloader.py        # Forge / NeoForge / Fabric / Quilt / LiteLoader
│   ├── content.py          # Modrinth / CurseForge 搜索与安装
│   ├── launcher.py         # 启动参数构建与游戏进程管理
│   ├── version.py          # 版本扫描、规则解析
│   ├── java.py             # Java 探测与下载
│   ├── downloads.py        # 下载中心任务模型
│   └── ui/                 # 各页面与主题（深色 QSS）
├── data/                   # 运行时生成：配置、缓存、日志、实例
└── dist/                   # 打包产物
```

---

## 数据与配置

| 路径 | 说明 |
| --- | --- |
| `data/config.json` | 启动器设置、实例、数据目录、服务器列表 |
| `data/accounts.json` | 账号与令牌（本地保存，请勿分享） |
| `data/logs/launcher.log` | 启动器运行日志（轮转） |
| `data/logs/game-*.log` | 游戏输出日志 |
| `data/logs/crashes/` | 异常退出的游戏日志归档 |
| `data/instances/` | 整合包实例 |

> `data/accounts.json` 内含账号令牌，请勿上传或分享。

---

## 常见问题

**Q：离线皮肤进游戏不显示？**
离线皮肤写入的是 `CustomSkinLoader/LocalSkin`，需要该版本安装 **CustomSkinLoader** Mod 才能在游戏内显示；启动器内的 3D 预览不受影响。

**Q：整合包安装失败 / 装完找不到？**
安装失败会弹出提示并把安装日志复制到剪贴板，同时写入 `data/logs/install_error.log`。安装成功后会自动选中新实例，主页版本下拉中带「（整合包）」标记。

**Q：下载中断后要重新下吗？**
不需要。下载使用 `.part` 临时文件 + Range 续传，重新开始会从中断处继续。

**Q：为什么不能同时开两个 MikanCL？**
启动器带单实例保护，避免两个进程同时写 `config.json`、`accounts.json` 与浏览器缓存。

---

## 免责声明

本项目仅供学习与交流使用。请通过官方渠道购买并支持 Minecraft 正版；使用第三方登录、Mod 或整合包产生的风险由使用者自行承担。

Minecraft 是 Mojang Studios 的商标，本项目与 Mojang / Microsoft 无关联。
