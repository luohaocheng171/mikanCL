"""教程中心：内置多语言 Markdown Wiki，支持搜索与按标题浏览。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
3. 选一张 64×64 或 64×32 的 PNG
4. 启动游戏，CustomSkinLoader 会自动应用

## 注意
- 皮肤文件会写入 `CustomSkinLoader/LocalSkin/skins/<玩家名>.png`
- 只有装了 CustomSkinLoader 才会生效
- 正版账号不需要这个，直接上传皮肤即可
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
3. Pick a 64×64 or 64×32 PNG
4. Launch the game; CustomSkinLoader applies it automatically

## Notes
- The skin is written to `CustomSkinLoader/LocalSkin/skins/<player name>.png`
- It only works when CustomSkinLoader is installed
- Official accounts do not need this — just upload the skin
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
    def shutdown(self) -> None:
        """教程页没有后台任务，保留接口供 MainWindow 统一调用。"""
