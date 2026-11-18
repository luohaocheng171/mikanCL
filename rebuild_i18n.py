"""重建 Qt 翻译文件（.ts / .qm）。

源码里使用自定义的 ``t(context, text)`` 与 ``self.tr(text)``，Qt 自带的 lupdate
无法直接识别，因此这里用 AST 精确提取上下文与原文，再从现有 .qm 里取回已有
译文，最后调用 lrelease 重新编译。

用法：python rebuild_i18n.py
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
TRANSLATIONS = ROOT / "mc_launcher" / "translations"
LANGUAGES = ["zh_CN", "en_US", "ja_JP", "ru_RU", "fr_FR"]

# 与美化版 / Electron 前端共用的高频词条译文：任一 context 下缺少译文时，
# 只要原文恰好命中这里就补上，避免经典版大量按钮回退中文。
SHARED_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en_US": {
        "主页": "Home",
        "下载中心": "Downloads",
        "内容中心": "Content",
        "实例管理": "Instances",
        "版本设置": "Version settings",
        "账号与皮肤": "Account & skins",
        "联机": "Multiplayer",
        "教程中心": "Guides",
        "浏览器": "Browser",
        "工具箱": "Toolbox",
        "设置": "Settings",
        "创世神面板": "Save Creator",
        "API 浏览器": "API browser",
        "皮肤工坊": "Skin studio",
        "NBT 工作室": "NBT studio",
        "配方工坊": "Recipe workshop",
        "数值调校": "Value tuning",
        "备份中心": "Backups",
        "Java 中心": "Java Center",
        "远古版本急救": "Legacy rescue",
        "模组管理": "Mod management",
        "崩溃报告": "Crash reports",
        "截图图库": "Screenshots",
        "局域网中控": "LAN hub",
        "全局搜索": "Global search",
        "常规": "General",
        "外观": "Appearance",
        "下载": "Download",
        "扩展": "Extensions",
        "高级": "Advanced",
        "关于": "About",
        "语言": "Language",
        "主题": "Theme",
        "界面框架": "UI framework",
        "下载文件夹": "Downloads folder",
        "Java 运行时": "Java runtime",
        "内存": "Memory",
        "窗口大小": "Window size",
        "开机自启": "Start with Windows",
        "刷新": "Refresh",
        "保存": "Save",
        "删除": "Delete",
        "确定": "OK",
        "取消": "Cancel",
        "打开": "Open",
        "关闭": "Close",
        "返回": "Back",
        "安装": "Install",
        "启动": "Launch",
        "启动游戏": "Launch game",
        "停止": "Stop",
        "应用": "Apply",
        "预览": "Preview",
        "扫描": "Scan",
        "搜索": "Search",
        "添加": "Add",
        "编辑": "Edit",
        "复制": "Copy",
        "导出": "Export",
        "导入": "Import",
        "启用": "Enable",
        "禁用": "Disable",
        "重试": "Retry",
        "继续": "Continue",
        "全部": "All",
        "加载中": "Loading…",
        "完成": "Done",
        "失败": "Failed",
        "成功": "Success",
        "错误": "Error",
        "警告": "Warning",
        "提示": "Notice",
        "更改": "Change",
        "恢复默认": "Reset",
        "清空": "Clear",
        "新建": "New",
        "重命名": "Rename",
        "上传": "Upload",
        "选择": "Select",
        "一键修复": "One-click fix",
        "在线下载": "Download online",
        "打开目录": "Open folder",
        "开启": "Start",
        "写入": "Write",
        "读取": "Read",
        "备份": "Backup",
        "还原": "Restore",
        "测试": "Test",
        "发送": "Send",
        "订阅": "Subscribe",
        "执行": "Execute",
        "确认": "Confirm",
        "详情": "Details",
        "调用": "Call",
        "写入前强制完整备份": "Full backup is forced before writing",
        "已开启": "Enabled",
        "未开启": "Disabled",
        "运行中": "Running",
        "准备中": "Preparing",
        "已完成": "Completed",
        "已取消": "Cancelled",
        "暂无数据": "No data yet",
        "没有匹配的接口": "No matching API",
        "当前无网络": "Offline",
        "未知": "Unknown",
        "版本": "Version",
        "存档": "Save",
        "玩家": "Player",
        "名称": "Name",
        "路径": "Path",
        "大小": "Size",
        "时间": "Time",
        "类型": "Type",
        "说明": "Description",
        "状态": "Status",
        "分组": "Group",
        "参数": "Parameters",
        "结果": "Result",
        "地址": "Address",
        "端口": "Port",
        "密钥": "Secret",
        "事件": "Event",
        "回调地址": "Callback URL",
        "最近事件": "Recent events",
        "需 Mod": "Requires a mod",
        "不支持": "Not supported",
        "可选": "Optional",
        "启动器接口总览": "Launcher API overview",
        "本机 JSON-RPC 服务": "Local JSON-RPC service",
        "接口清单": "API list",
        "在线调用": "Invoke an API",
        "对话式 API": "Conversational API",
        "WebSocket 长连接": "WebSocket channel",
        "命令行与游戏联动": "CLI & game link",
        "打开下载文件夹": "Open downloads folder",
        "手动下载 / 另存为的文件保存到这里": "Manual downloads and “Save as” files go here",
        "只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。": "Only affects “Save as” and download-only files; games, mods and modpacks still go to their version folder.",
        "全部分组": "All groups",
        "公开接口": "Public APIs",
        "搜索接口名或说明": "Search API name or description",
        "调用结果会显示在这里": "Results appear here",
        "点接口清单里的「详情」选中一个方法": "Pick a method via “Details” in the API list",
        "服务只监听 127.0.0.1，需携带 X-Mikan-Token 请求头；关闭启动器后自动停止。": "The service listens on 127.0.0.1 only, requires the X-Mikan-Token header, and stops when the launcher closes.",
        "对话式接口默认只出计划，不执行": "Conversational API returns a plan only; nothing runs by default",
        "Webhook 默认关闭，地址由你自己填写": "Webhooks are off by default; you supply the URL yourself",
        "不读取游戏进程内存": "No game process memory is read",
        "实时操作需要服务端开启 RCON": "Live actions require a server with RCON enabled",
        "生成计划": "Build plan",
        "确认执行": "Confirm execution",
        "事件白名单": "Event filter",
        "保存并测试": "Save & test",
        "查看最近投递": "Recent deliveries"
    },
    "ru_RU": {
        "主页": "Главная",
        "下载中心": "Загрузки",
        "内容中心": "Контент",
        "实例管理": "Экземпляры",
        "版本设置": "Настройки версии",
        "账号与皮肤": "Аккаунт и скины",
        "联机": "Сеть",
        "教程中心": "Руководства",
        "浏览器": "Браузер",
        "工具箱": "Инструменты",
        "设置": "Настройки",
        "创世神面板": "Редактор сохранений",
        "API 浏览器": "Браузер API",
        "皮肤工坊": "Мастерская скинов",
        "NBT 工作室": "Студия NBT",
        "配方工坊": "Мастерская рецептов",
        "数值调校": "Настройка значений",
        "备份中心": "Резервные копии",
        "Java 中心": "Центр Java",
        "远古版本急救": "Спасение старых версий",
        "模组管理": "Управление модами",
        "崩溃报告": "Отчёты о сбоях",
        "截图图库": "Галерея снимков",
        "局域网中控": "Локальный сервер",
        "全局搜索": "Глобальный поиск",
        "常规": "Общие",
        "外观": "Оформление",
        "下载": "Загрузка",
        "扩展": "Расширения",
        "高级": "Дополнительно",
        "关于": "О программе",
        "语言": "Язык",
        "主题": "Тема",
        "界面框架": "Framework интерфейса",
        "下载文件夹": "Папка загрузок",
        "Java 运行时": "Среда Java",
        "内存": "Память",
        "窗口大小": "Размер окна",
        "开机自启": "Автозапуск",
        "刷新": "Обновить",
        "保存": "Сохранить",
        "删除": "Удалить",
        "确定": "ОК",
        "取消": "Отмена",
        "打开": "Открыть",
        "关闭": "Закрыть",
        "返回": "Назад",
        "安装": "Установить",
        "启动": "Запустить",
        "启动游戏": "Запустить игру",
        "停止": "Остановить",
        "应用": "Применить",
        "预览": "Предпросмотр",
        "扫描": "Сканировать",
        "搜索": "Поиск",
        "添加": "Добавить",
        "编辑": "Изменить",
        "复制": "Копировать",
        "导出": "Экспорт",
        "导入": "Импорт",
        "启用": "Включить",
        "禁用": "Отключить",
        "重试": "Повторить",
        "继续": "Продолжить",
        "全部": "Все",
        "加载中": "Загрузка…",
        "完成": "Готово",
        "失败": "Ошибка",
        "成功": "Успешно",
        "错误": "Ошибка",
        "警告": "Предупреждение",
        "提示": "Подсказка",
        "更改": "Изменить",
        "恢复默认": "Сбросить",
        "清空": "Очистить",
        "新建": "Создать",
        "重命名": "Переименовать",
        "上传": "Загрузить",
        "选择": "Выбрать",
        "一键修复": "Исправить одним кликом",
        "在线下载": "Скачать онлайн",
        "打开目录": "Открыть папку",
        "开启": "Включить",
        "写入": "Записать",
        "读取": "Прочитать",
        "备份": "Резервная копия",
        "还原": "Восстановить",
        "测试": "Проверить",
        "发送": "Отправить",
        "订阅": "Подписаться",
        "执行": "Выполнить",
        "确认": "Подтвердить",
        "详情": "Подробнее",
        "调用": "Вызвать",
        "写入前强制完整备份": "Перед записью создаётся полная копия",
        "已开启": "Включено",
        "未开启": "Выключено",
        "运行中": "Работает",
        "准备中": "Подготовка",
        "已完成": "Завершено",
        "已取消": "Отменено",
        "暂无数据": "Данных пока нет",
        "没有匹配的接口": "Совпадений нет",
        "当前无网络": "Нет сети",
        "未知": "Неизвестно",
        "版本": "Версия",
        "存档": "Сохранение",
        "玩家": "Игрок",
        "名称": "Название",
        "路径": "Путь",
        "大小": "Размер",
        "时间": "Время",
        "类型": "Тип",
        "说明": "Описание",
        "状态": "Состояние",
        "分组": "Группа",
        "参数": "Параметры",
        "结果": "Результат",
        "地址": "Адрес",
        "端口": "Порт",
        "密钥": "Секрет",
        "事件": "Событие",
        "回调地址": "URL обратного вызова",
        "最近事件": "Последние события",
        "需 Mod": "Требуется мод",
        "不支持": "Не поддерживается",
        "可选": "Необязательно",
        "启动器接口总览": "Обзор API лаунчера",
        "本机 JSON-RPC 服务": "Локальный сервис JSON-RPC",
        "接口清单": "Список API",
        "在线调用": "Вызов API",
        "对话式 API": "Диалоговый API",
        "WebSocket 长连接": "Канал WebSocket",
        "命令行与游戏联动": "CLI и связь с игрой",
        "打开下载文件夹": "Открыть папку загрузок",
        "手动下载 / 另存为的文件保存到这里": "Сюда сохраняются ручные загрузки и файлы «Сохранить как»",
        "只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。": "Касается только файлов «Сохранить как» и загрузок без установки; игры, моды и сборки по-прежнему пишутся в папку версии.",
        "全部分组": "Все группы",
        "公开接口": "Публичные API",
        "搜索接口名或说明": "Поиск по имени или описанию API",
        "调用结果会显示在这里": "Результаты появятся здесь",
        "点接口清单里的「详情」选中一个方法": "Выберите метод через «Подробнее» в списке API",
        "服务只监听 127.0.0.1，需携带 X-Mikan-Token 请求头；关闭启动器后自动停止。": "Сервис слушает только 127.0.0.1, требует заголовок X-Mikan-Token и останавливается при закрытии лаунчера.",
        "对话式接口默认只出计划，不执行": "Диалоговый API по умолчанию только составляет план",
        "Webhook 默认关闭，地址由你自己填写": "Webhook по умолчанию выключен; адрес задаёте вы",
        "不读取游戏进程内存": "Память игрового процесса не читается",
        "实时操作需要服务端开启 RCON": "Для действий в реальном времени нужен сервер с RCON",
        "生成计划": "Составить план",
        "确认执行": "Подтвердить выполнение",
        "事件白名单": "Фильтр событий",
        "保存并测试": "Сохранить и проверить",
        "查看最近投递": "Последние доставки"
    },
    "fr_FR": {
        "主页": "Accueil",
        "下载中心": "Téléchargements",
        "内容中心": "Contenu",
        "实例管理": "Instances",
        "版本设置": "Réglages de version",
        "账号与皮肤": "Compte et skins",
        "联机": "Multijoueur",
        "教程中心": "Guides",
        "浏览器": "Navigateur",
        "工具箱": "Outils",
        "设置": "Réglages",
        "创世神面板": "Éditeur de sauvegarde",
        "API 浏览器": "Explorateur d'API",
        "皮肤工坊": "Atelier de skins",
        "NBT 工作室": "Atelier NBT",
        "配方工坊": "Atelier de recettes",
        "数值调校": "Réglage des valeurs",
        "备份中心": "Sauvegardes",
        "Java 中心": "Centre Java",
        "远古版本急救": "Secours des anciennes versions",
        "模组管理": "Gestion des mods",
        "崩溃报告": "Rapports de plantage",
        "截图图库": "Galerie de captures",
        "局域网中控": "Panneau LAN",
        "全局搜索": "Recherche globale",
        "常规": "Général",
        "外观": "Apparence",
        "下载": "Téléchargement",
        "扩展": "Extensions",
        "高级": "Avancé",
        "关于": "À propos",
        "语言": "Langue",
        "主题": "Thème",
        "界面框架": "Framework d'interface",
        "下载文件夹": "Dossier de téléchargements",
        "Java 运行时": "Runtime Java",
        "内存": "Mémoire",
        "窗口大小": "Taille de la fenêtre",
        "开机自启": "Démarrer avec Windows",
        "刷新": "Actualiser",
        "保存": "Enregistrer",
        "删除": "Supprimer",
        "确定": "OK",
        "取消": "Annuler",
        "打开": "Ouvrir",
        "关闭": "Fermer",
        "返回": "Retour",
        "安装": "Installer",
        "启动": "Lancer",
        "启动游戏": "Lancer le jeu",
        "停止": "Arrêter",
        "应用": "Appliquer",
        "预览": "Aperçu",
        "扫描": "Analyser",
        "搜索": "Rechercher",
        "添加": "Ajouter",
        "编辑": "Modifier",
        "复制": "Copier",
        "导出": "Exporter",
        "导入": "Importer",
        "启用": "Activer",
        "禁用": "Désactiver",
        "重试": "Réessayer",
        "继续": "Continuer",
        "全部": "Tout",
        "加载中": "Chargement…",
        "完成": "Terminé",
        "失败": "Échec",
        "成功": "Succès",
        "错误": "Erreur",
        "警告": "Avertissement",
        "提示": "Info",
        "更改": "Changer",
        "恢复默认": "Réinitialiser",
        "清空": "Effacer",
        "新建": "Nouveau",
        "重命名": "Renommer",
        "上传": "Téléverser",
        "选择": "Choisir",
        "一键修复": "Réparation en un clic",
        "在线下载": "Télécharger en ligne",
        "打开目录": "Ouvrir le dossier",
        "开启": "Démarrer",
        "写入": "Écrire",
        "读取": "Lire",
        "备份": "Sauvegarde",
        "还原": "Restaurer",
        "测试": "Tester",
        "发送": "Envoyer",
        "订阅": "S'abonner",
        "执行": "Exécuter",
        "确认": "Confirmer",
        "详情": "Détails",
        "调用": "Appeler",
        "写入前强制完整备份": "Une sauvegarde complète est créée avant l'écriture",
        "已开启": "Activé",
        "未开启": "Désactivé",
        "运行中": "En cours",
        "准备中": "Préparation",
        "已完成": "Terminé",
        "已取消": "Annulé",
        "暂无数据": "Aucune donnée",
        "没有匹配的接口": "Aucune API correspondante",
        "当前无网络": "Hors ligne",
        "未知": "Inconnu",
        "版本": "Version",
        "存档": "Sauvegarde",
        "玩家": "Joueur",
        "名称": "Nom",
        "路径": "Chemin",
        "大小": "Taille",
        "时间": "Heure",
        "类型": "Type",
        "说明": "Description",
        "状态": "État",
        "分组": "Groupe",
        "参数": "Paramètres",
        "结果": "Résultat",
        "地址": "Adresse",
        "端口": "Port",
        "密钥": "Secret",
        "事件": "Événement",
        "回调地址": "URL de rappel",
        "最近事件": "Événements récents",
        "需 Mod": "Nécessite un mod",
        "不支持": "Non pris en charge",
        "可选": "Facultatif",
        "启动器接口总览": "Vue d'ensemble des API",
        "本机 JSON-RPC 服务": "Service JSON-RPC local",
        "接口清单": "Liste des API",
        "在线调用": "Appel d'API",
        "对话式 API": "API conversationnelle",
        "WebSocket 长连接": "Canal WebSocket",
        "命令行与游戏联动": "CLI et liaison au jeu",
        "打开下载文件夹": "Ouvrir le dossier de téléchargements",
        "手动下载 / 另存为的文件保存到这里": "Les téléchargements manuels et les fichiers « Enregistrer sous » vont ici",
        "只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。": "Concerne uniquement les fichiers « Enregistrer sous » et les téléchargements sans installation ; jeux, mods et modpacks restent dans le dossier de la version.",
        "全部分组": "Tous les groupes",
        "公开接口": "API publiques",
        "搜索接口名或说明": "Rechercher un nom ou une description d'API",
        "调用结果会显示在这里": "Les résultats s'affichent ici",
        "点接口清单里的「详情」选中一个方法": "Choisissez une méthode via « Détails » dans la liste",
        "服务只监听 127.0.0.1，需携带 X-Mikan-Token 请求头；关闭启动器后自动停止。": "Le service n'écoute que sur 127.0.0.1, exige l'en-tête X-Mikan-Token et s'arrête à la fermeture du lanceur.",
        "对话式接口默认只出计划，不执行": "L'API conversationnelle ne renvoie qu'un plan par défaut",
        "Webhook 默认关闭，地址由你自己填写": "Les webhooks sont désactivés par défaut ; vous fournissez l'URL",
        "不读取游戏进程内存": "La mémoire du processus de jeu n'est pas lue",
        "实时操作需要服务端开启 RCON": "Les actions en temps réel nécessitent un serveur avec RCON",
        "生成计划": "Générer le plan",
        "确认执行": "Confirmer l'exécution",
        "事件白名单": "Filtre d'événements",
        "保存并测试": "Enregistrer et tester",
        "查看最近投递": "Derniers envois"
    },
    "ja_JP": {
        "主页": "ホーム",
        "下载中心": "ダウンロード",
        "内容中心": "コンテンツ",
        "实例管理": "インスタンス",
        "版本设置": "バージョン設定",
        "账号与皮肤": "アカウントとスキン",
        "联机": "マルチプレイ",
        "教程中心": "ガイド",
        "浏览器": "ブラウザ",
        "工具箱": "ツール",
        "设置": "設定",
        "创世神面板": "セーブエディター",
        "API 浏览器": "API ブラウザー",
        "皮肤工坊": "スキン工房",
        "NBT 工作室": "NBT スタジオ",
        "配方工坊": "レシピ工房",
        "数值调校": "数値調整",
        "备份中心": "バックアップ",
        "Java 中心": "Java センター",
        "远古版本急救": "レガシー救急",
        "模组管理": "Mod 管理",
        "崩溃报告": "クラッシュレポート",
        "截图图库": "スクリーンショット",
        "局域网中控": "LAN コントロール",
        "全局搜索": "全体検索",
        "常规": "一般",
        "外观": "外観",
        "下载": "ダウンロード",
        "扩展": "拡張",
        "高级": "詳細",
        "关于": "このアプリについて",
        "语言": "言語",
        "主题": "テーマ",
        "界面框架": "UI フレームワーク",
        "下载文件夹": "ダウンロードフォルダー",
        "Java 运行时": "Java ランタイム",
        "内存": "メモリ",
        "窗口大小": "ウィンドウサイズ",
        "开机自启": "自動起動",
        "刷新": "更新",
        "保存": "保存",
        "删除": "削除",
        "确定": "OK",
        "取消": "キャンセル",
        "打开": "開く",
        "关闭": "閉じる",
        "返回": "戻る",
        "安装": "インストール",
        "启动": "起動",
        "启动游戏": "ゲームを起動",
        "停止": "停止",
        "应用": "適用",
        "预览": "プレビュー",
        "扫描": "スキャン",
        "搜索": "検索",
        "添加": "追加",
        "编辑": "編集",
        "复制": "コピー",
        "导出": "エクスポート",
        "导入": "インポート",
        "启用": "有効化",
        "禁用": "無効化",
        "重试": "再試行",
        "继续": "続行",
        "全部": "すべて",
        "加载中": "読み込み中…",
        "完成": "完了",
        "失败": "失敗",
        "成功": "成功",
        "错误": "エラー",
        "警告": "警告",
        "提示": "ヒント",
        "更改": "変更",
        "恢复默认": "既定に戻す",
        "清空": "クリア",
        "新建": "新規",
        "重命名": "名前を変更",
        "上传": "アップロード",
        "选择": "選択",
        "一键修复": "ワンクリック修復",
        "在线下载": "オンライン取得",
        "打开目录": "フォルダーを開く",
        "开启": "開始",
        "写入": "書き込み",
        "读取": "読み取り",
        "备份": "バックアップ",
        "还原": "復元",
        "测试": "テスト",
        "发送": "送信",
        "订阅": "購読",
        "执行": "実行",
        "确认": "確認",
        "详情": "詳細",
        "调用": "呼び出し",
        "写入前强制完整备份": "書き込み前に完全バックアップを作成",
        "已开启": "有効",
        "未开启": "無効",
        "运行中": "実行中",
        "准备中": "準備中",
        "已完成": "完了",
        "已取消": "キャンセル済み",
        "暂无数据": "データなし",
        "没有匹配的接口": "一致する API なし",
        "当前无网络": "オフライン",
        "未知": "不明",
        "版本": "バージョン",
        "存档": "セーブ",
        "玩家": "プレイヤー",
        "名称": "名前",
        "路径": "パス",
        "大小": "サイズ",
        "时间": "時刻",
        "类型": "種類",
        "说明": "説明",
        "状态": "状態",
        "分组": "グループ",
        "参数": "パラメーター",
        "结果": "結果",
        "地址": "アドレス",
        "端口": "ポート",
        "密钥": "シークレット",
        "事件": "イベント",
        "回调地址": "コールバック URL",
        "最近事件": "最近のイベント",
        "需 Mod": "Mod が必要",
        "不支持": "非対応",
        "可选": "任意",
        "启动器接口总览": "起動器 API 概要",
        "本机 JSON-RPC 服务": "ローカル JSON-RPC",
        "接口清单": "API 一覧",
        "在线调用": "API を呼び出す",
        "对话式 API": "対話式 API",
        "WebSocket 长连接": "WebSocket 接続",
        "命令行与游戏联动": "CLI とゲーム連携",
        "打开下载文件夹": "ダウンロードフォルダーを開く",
        "手动下载 / 另存为的文件保存到这里": "手動ダウンロードと「名前を付けて保存」したファイルの保存先",
        "只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。": "「名前を付けて保存」とダウンロードのみのファイルに適用されます。ゲーム・Mod・整合パックは各バージョンのフォルダーに保存されます。",
        "全部分组": "すべてのグループ",
        "公开接口": "公開 API",
        "搜索接口名或说明": "API 名または説明を検索",
        "调用结果会显示在这里": "結果はここに表示されます",
        "点接口清单里的「详情」选中一个方法": "一覧の「詳細」からメソッドを選択",
        "服务只监听 127.0.0.1，需携带 X-Mikan-Token 请求头；关闭启动器后自动停止。": "127.0.0.1 のみで待ち受け、X-Mikan-Token ヘッダーが必要です。起動器を閉じると自動停止します。",
        "对话式接口默认只出计划，不执行": "対話式 API は既定で計画のみを返し、実行しません",
        "Webhook 默认关闭，地址由你自己填写": "Webhook は既定でオフ、URL はユーザーが指定します",
        "不读取游戏进程内存": "ゲームプロセスのメモリは読みません",
        "实时操作需要服务端开启 RCON": "リアルタイム操作には RCON 対応サーバーが必要",
        "生成计划": "計画を作成",
        "确认执行": "実行を確認",
        "事件白名单": "イベントフィルター",
        "保存并测试": "保存してテスト",
        "查看最近投递": "最近の配信"
    }
}


# 页面里的便捷包装：_c("...") 等价于 t("CreatorPage", "...")，提取时按同一上下文处理
WRAPPER_CONTEXTS: dict[str, str] = {"_c": "CreatorPage"}

# v5.1.0 新增字符串的英文译文（旧 .qm 中没有，按 (context, source) 补入）。
# 其他语言未覆盖的条目回退为原文（中文），与既有策略一致。
EN_SUPPLEMENTS: dict[str, dict[str, str]] = {
    "UiModeDialog": {
        "选择界面运行模式": "Choose UI Mode",
        "两种模式使用同一个 Qt 引擎，无需下载额外组件；之后可在「设置 → 界面效果」随时切换。"
        "低配电脑建议经典模式，想要毛玻璃与更强视觉层次则选视觉增强。": "Both modes run on the same Qt engine with no extra downloads. "
        "You can switch anytime in Settings → UI Effects. Classic is recommended for low-end PCs; choose Visual for acrylic blur and richer depth.",
        "经典模式": "Classic",
        "稳定 · 低占用 · 快速启动": "Stable · low resource · fast start",
        "纯 Qt 自绘，不启用系统毛玻璃合成": "Pure Qt painting, no system acrylic composition",
        "内存与 GPU 占用最低，适合低配机 / 远程桌面": "Lowest memory and GPU usage; ideal for low-end PCs and remote desktop",
        "侧边栏磁贴导航，深色磨砂质感": "Tile navigation with a dark frosted finish",
        "视觉增强": "Visual",
        "毛玻璃 · 磁贴 · 参考 iOS / BakaXL": "Acrylic · tiles · inspired by iOS / BakaXL",
        "调用 Windows 10/11 原生 DWM 亚克力，背景与按钮半透明": "Uses native Windows 10/11 DWM acrylic for translucent background and buttons",
        "保留品牌绿色点缀，卡片层级更接近 iOS 控制中心": "Keeps the brand green accent with iOS Control Center-like depth",
        "支持背景图 + 毛玻璃叠加，可随时关闭": "Supports wallpaper + acrylic overlay, can be disabled anytime",
        "说明：没有改用 Electron / Tauri / Flutter —— 它们的内存占用更高，且无法直接调用"
        " Windows 原生亚克力。当前 Qt + DWM 方案更轻，效果也更接近系统原生。": "Note: Electron / Tauri / Flutter were not adopted: they use more memory and cannot use native Windows acrylic directly. "
        "The current Qt + DWM approach is lighter and closer to the native system look.",
        "返回": "Back",
        "使用此模式": "Use this mode",
    },
    "GalleryPage": {
        "截图图库": "Screenshots",
        "浏览当前实例的 screenshots/，支持预览、打包 zip、打开与删除。": "Browse screenshots/ of the current instance; preview, zip, open and delete.",
        "刷新": "Refresh",
        "打开目录": "Open folder",
        "打包所选": "Zip selected",
        "删除所选": "Delete selected",
        "文件": "File",
        "修改时间": "Modified",
        "大小": "Size",
        "选择一张截图以预览": "Select a screenshot to preview",
        "用默认看图工具打开": "Open with default viewer",
        "还没有可打包的截图。": "No screenshots to zip yet.",
        "导出截图压缩包": "Export screenshots",
        "导出失败": "Export failed",
        "删除截图": "Delete screenshots",
        "确定删除选中的 {0} 个文件？此操作不可撤销。": "Delete the {0} selected file(s)? This cannot be undone.",
        "有 {0} 个文件删除失败。": "{0} file(s) could not be deleted.",
        "无法读取该图片": "Cannot read this image",
        "已导出 {0} 张截图。": "Exported {0} screenshot(s).",
    },
    "CrashReportPage": {
        "崩溃报告": "Crash reports",
        "启动器会把游戏异常退出的日志归档到这里，方便排查或反馈问题。": "Logs from abnormal game exits are archived here for troubleshooting.",
        "刷新": "Refresh",
        "打开目录": "Open folder",
        "复制摘要": "Copy summary",
        "删除所选": "Delete selected",
        "日志文件": "Log file",
        "时间": "Time",
        "大小": "Size",
        "选择一份崩溃日志查看内容…": "Select a crash log to view its contents…",
        "崩溃报告": "Crash reports",
        "删除崩溃报告": "Delete crash reports",
        "确定删除选中的 {0} 份日志？": "Delete the {0} selected log(s)?",
        "有 {0} 个文件删除失败。": "{0} file(s) could not be deleted.",
        "崩溃摘要已复制到剪贴板。": "Crash summary copied to clipboard.",
    },
    "MainWindow": {
        "Minecraft 菜单": "Minecraft menu",
        "单人游戏（存档管理）": "Singleplayer (saves)",
        "多人游戏（服务器列表）": "Multiplayer (servers)",
        "资源包 / 光影包": "Resource / shader packs",
        "截图图库": "Screenshots",
        "崩溃报告": "Crash reports",
        "选项…（设置）": "Options… (Settings)",
        "Java 与运行环境": "Java & runtime",
        "退出启动器": "Quit launcher",
        "截图图库": "Screenshots",
        "崩溃报告": "Crash reports",
        "启动": "Launch",
        "下载": "Download",
        "内容": "Content",
        "联机": "Online",
        "工具": "Tools",
        "设置": "Settings",
        "Mod 关系网": "Mod graph",
        "关系网": "Graph",
    },
    "SettingsPage": {
        "运行模式": "UI mode",
        "经典模式（稳定 · 低占用）": "Classic (stable · low resource)",
        "视觉增强（毛玻璃 · 磁贴）": "Visual (acrylic · tiles)",
        "已切换到视觉增强模式。": "Switched to Visual mode.",
        "已切换到经典模式。": "Switched to Classic mode.",
        "游戏优化": "Game optimization",
        "全部为开关键，改动立即生效，下次启动游戏时应用": "All toggles apply immediately and take effect on the next launch",
        "智能 JVM 参数（自动启用 G1GC 等调优，减少卡顿）": "Smart JVM args (auto G1GC tuning to reduce stutter)",
        "按 Java 版本与内存自动追加 Aikar 风格 G1GC 参数；已自定义 GC 参数时自动跳过。": "Adds Aikar-style G1GC args based on Java version and heap; skipped if you already set GC flags.",
        "大堆预触碰（AlwaysPreTouch，稳定内存占用）": "Pre-touch large heap (AlwaysPreTouch, steadier memory)",
        "仅在分配内存 ≥ 4 GB 时追加，启动稍慢一点，但运行中更少卡顿。": "Applied only when heap ≥ 4 GB; slightly slower startup, fewer in-game hitches.",
        "固定堆大小（-Xms 与 -Xmx 相同）": "Fixed heap (-Xms equals -Xmx)",
        "启动时一次性占满分配内存，避免运行中扩堆；内存紧张的老机器不建议开启。": "Reserves the full heap at startup to avoid runtime growth; not recommended on low-RAM machines.",
        "这些开关只影响启动参数，不改动游戏内的画面设置。\n"
        "老机器建议只开「智能 JVM 参数」，其余按需开启。": "These toggles only affect launch arguments, not in-game video settings.\n"
        "On older PCs, enable only Smart JVM args and turn the rest on as needed.",
        "主题方案": "Theme",
        "导入主题…": "Import theme…",
        "导出模板…": "Export template…",
        "自定义主题是 data/themes/*.json，改完点「导入主题」即可生效；只换主题色时用下方色块。": "Custom themes are data/themes/*.json; import to apply. Use the swatches below to change only the accent color.",
        "界面框架": "UI framework",
        "经典版（Qt，功能完整）": "Classic (Qt, full features)",
        "经典版（Qt，省内存）": "Classic (Qt, low memory)",
        "美化版（pywebview + WebView2）": "Enhanced (pywebview + WebView2)",
        "美化版（pywebview + WebView2，推荐）": "Enhanced (pywebview + WebView2, recommended)",
        "独立版（Electron，自带 Chromium，占用较高）": "Standalone (Electron, bundled Chromium, higher resource use)",
        "经典版 / 美化版 / 独立版可随时切换，三套界面共用同一套启动、下载、账号与联机内核；"
        "修改后重启启动器生效，不会丢失下载进度或设置。"
        "独立版自带 Chromium、不依赖 WebView2，占用更高；单文件版已内置独立版，首次切换会自动释放。": "Classic / Enhanced / Standalone can be switched anytime; all three share the same launch, download, account and multiplayer engine. "
        "Restart the launcher to apply, without losing download progress or settings. "
        "Standalone bundles Chromium and needs no WebView2; the single-file build includes it and extracts on first switch.",
        "未检测到独立版（Electron）。\n"
        "单文件版应已内置独立版，第一次切换会自动释放；"
        "若使用源码运行，请先运行 build_electron.py --all 生成。\n\n"
        "仍要切换吗？": "No standalone (Electron) build was found.\n"
        "The single-file build should include it and extract on first switch.\n"
        "When running from source, run build_electron.py --all first.\n\n"
        "Switch anyway?",
        "美化版用 Edge WebView2（Chromium）渲染玻璃拟态界面。"
        "选定美化版后框架即锁定，不能切回经典版；缺少运行时启动时会引导安装。": "The enhanced UI renders with Edge WebView2 (Chromium) glassmorphism. "
        "Choosing it locks the framework; you cannot switch back to Classic. Missing runtime is handled with an install prompt at startup.",
        "美化版用 Edge WebView2（Chromium）渲染玻璃拟态界面，需重启启动器生效；"
        "选定后框架锁定，不能切回经典版。": "The enhanced UI renders with Edge WebView2 (Chromium); restart to apply. "
        "The framework is locked after choosing; you cannot switch back to Classic.",
        "未检测到 WebView2 Runtime，美化版可能无法启动。\n"
        "选择美化版后会锁定框架、不能切回经典版。仍要切换吗？\n"
        "（启动时会引导安装 WebView2 Runtime）": "WebView2 Runtime was not detected; the enhanced UI may fail to start.\n"
        "Choosing it locks the framework permanently. Switch anyway?\n"
        "(Startup will guide you through installing WebView2 Runtime.)",
        "选择美化版后将锁定界面框架，不能再切回经典版。\n确认继续吗？": "Choosing the enhanced UI locks the framework permanently; you cannot switch back to Classic.\nContinue?",
        "界面框架已保存，重启启动器后生效。": "UI framework saved. Restart the launcher to apply.",
        "毛玻璃强度": "Glass intensity",
    },
    "FrameModeDialog": {
        "选择界面框架": "Choose UI framework",
        "两套界面共用同一套启动、下载、账号与联机内核，功能完全对齐。"
        "只加载所选框架，未选中的模块不会占用内存。"
        "注意：选择美化版后会锁定框架，不能切回经典版。": "Both UIs share the same launch, download, account and multiplayer engine with full feature parity. "
        "Only the selected framework is loaded, so the other does not use memory. "
        "Note: choosing the enhanced UI locks the framework; you cannot switch back to Classic.",
        "经典版 · Qt": "Classic · Qt",
        "稳定 · 省内存 · 功能完整": "Stable · low memory · complete",
        "纯 Qt 绘制，不依赖任何浏览器运行时": "Pure Qt painting with no browser runtime dependency",
        "所有页面（下载、内容、联机、工具、设置）全部可用": "All pages (downloads, content, multiplayer, tools, settings) are available",
        "启动最快，适合 4 代 i5 / 核显等老机器": "Fastest startup; ideal for older PCs",
        "美化版 · pywebview": "Enhanced · pywebview",
        "美化版 · pywebview（推荐）": "Enhanced · pywebview (recommended)",
        "独立版 · Electron": "Standalone · Electron",
        "脱离依赖 · 自带 Chromium · 占用较高": "No runtime dependency · bundled Chromium · higher resource use",
        "自带 Chromium 内核，不依赖 WebView2，装不上运行时的电脑也能用": "Bundles its own Chromium, needs no WebView2, works on PCs where the runtime cannot be installed",
        "界面与美化版完全一致，共用同一套 HTML / CSS / JS": "Identical to the enhanced UI, sharing the same HTML / CSS / JS",
        "缺点：安装包与内存占用都比前两种更高": "Trade-off: larger installer and higher memory use than the other two",
        "独立版已内置，首次切换会自动释放": "Standalone is bundled and extracts on first switch",
        "未检测到独立版（源码运行需先构建，缺失时自动退回）": "No standalone build found (build it when running from source; falls back automatically)",
        "Chromium 渲染 · 玻璃拟态 · 参考主流启动器": "Chromium rendering · glassmorphism · inspired by popular launchers",
        "Edge WebView2（Chromium）渲染，CSS 动画与视觉上限更高": "Rendered by Edge WebView2 (Chromium) with higher CSS/animation ceiling",
        "竖排图标侧栏 + 悬浮玻璃卡片，前端可深度定制主题": "Vertical icon rail + floating glass cards; deeply customizable themes",
        "下载、内容、账号、联机、工具、设置与经典版功能一致": "Downloads, content, accounts, multiplayer, tools and settings match the classic UI",
        "选定后锁定框架，不能切回经典版；缺少运行时按提示安装": "Framework locks after choosing; missing runtime is installed per the prompt",
        "已检测到 WebView2 Runtime": "WebView2 Runtime detected",
        "未检测到 WebView2 Runtime（首次使用会引导安装）": "WebView2 Runtime not found (first use will guide installation)",
        "美化版依赖 WebView2 Runtime。Win10/11 通常随 Edge 预装；缺失时启动器会引导下载并退出，"
        "也可把运行时解包到安装目录 webview2 文件夹使用内置版本。": "The enhanced UI requires WebView2 Runtime. It ships with Edge on most Win10/11 PCs; if missing the launcher guides you to download and then exits. "
        "You can also unpack a runtime into the webview2 folder next to the executable.",
        "默认推荐美化版：Chromium 渲染，视觉与动画更完整；经典版更省内存；"
        "独立版自带 Chromium，完全不依赖系统组件，但占用更高。"
        "三套界面共用同一套启动、下载、账号与联机内核，随时可在设置页切换。": "Enhanced is recommended by default: Chromium rendering with richer visuals and animation. Classic uses less memory. "
        "Standalone bundles Chromium and depends on nothing, at the cost of higher resource use. "
        "All three share the same launch, download, account and multiplayer engine and can be switched in Settings.",
        "美化版依赖 WebView2 Runtime。Win10/11 通常随 Edge 预装；缺失时启动器会引导下载并退出，"
        "也可把运行时解包到安装目录 webview2 文件夹使用内置版本。"
        "独立版不需要 WebView2。单文件版已内置独立版，选中后会释放到 data/electron/app，之后直接复用。": "The enhanced UI requires WebView2 Runtime. It ships with Edge on most Win10/11 PCs; if missing the launcher guides you to download and then exits. "
        "You can also unpack a runtime into the webview2 folder next to the executable. "
        "Standalone needs no WebView2; the single-file build includes it and extracts it to data/electron/app on first use.",
        "使用此框架": "Use this framework",
    },
    "MainWindow": {
        "点击快速切换皮肤": "Click to switch skin",
        "还没有历史皮肤": "No skin history yet",
        "导入新皮肤…": "Import new skin…",
        "打开皮肤库": "Open skin library",
        "选择本地皮肤": "Choose a local skin",
        "已切换到皮肤「{0}」": "Switched to skin {0}",
        "应用皮肤失败：{0}": "Failed to apply skin: {0}",
        "读取皮肤失败：{0}": "Failed to read skin: {0}",
    },
    "CreatorPage": {
        "生命 Health": "Health",
        "吸收生命 AbsorptionAmount": "Absorption",
        "饱和度 foodSaturationLevel": "Saturation",
        "饥饿值 foodLevel": "Food level",
        "疲劳 foodExhaustionLevel": "Exhaustion",
        "经验等级 XpLevel": "XP level",
        "经验进度 XpP": "XP progress",
        "无敌（Invulnerable，免疫绝大多数伤害）": "Invulnerable (immune to most damage)",
        "飞行（Flying / Mayfly，生存模式会持续耗饥饿）": "Flying / Mayfly (consumes hunger in survival)",
        "难度 Difficulty": "Difficulty",
        "极限模式（hardcore，死亡后只能旁观）": "Hardcore (spectate after death)",
        "允许命令（allowCommands，开启后可用 /gamemode 等）": "Allow commands (enables /gamemode and more)",
        "面板上的数值与存档中的实际数据一致，没有检测到改动，存档保持原样。":
            "The panel matches the save data; nothing was changed and the save is untouched.",
    },
}


def _str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract() -> dict[str, list[str]]:
    """返回 {context: [source, ...]}，按源码出现顺序去重。"""
    messages: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()

    def add(context: str, text: str) -> None:
        if not context or not text:
            return
        key = (context, text)
        if key in seen:
            return
        seen.add(key)
        messages.setdefault(context, []).append(text)

    for path in list((ROOT / "mc_launcher").rglob("*.py")) + [ROOT / "run.py"]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        # 每个类节点记录类名，用于 self.tr 的上下文
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        def context_of(node: ast.AST) -> str:
            current = node
            while current is not None:
                if isinstance(current, ast.ClassDef):
                    return current.name
                current = parents.get(current)
            return ""

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "t" and len(node.args) >= 2:
                ctx = _str(node.args[0])
                text = _str(node.args[1])
                if ctx and text:
                    add(ctx, text)
            elif isinstance(func, ast.Name) and func.id in WRAPPER_CONTEXTS and node.args:
                text = _str(node.args[0])
                if text:
                    add(WRAPPER_CONTEXTS[func.id], text)
            elif isinstance(func, ast.Attribute) and func.attr == "tr" and node.args:
                text = _str(node.args[0])
                if text:
                    add(context_of(node), text)
            elif isinstance(func, ast.Attribute) and func.attr == "translate" and len(node.args) >= 2:
                ctx = _str(node.args[0])
                text = _str(node.args[1])
                if ctx and text:
                    add(ctx, text)
    return messages


def build_ts(messages: dict[str, list[str]]) -> dict[str, dict[tuple[str, str], str]]:
    """用现有 .qm 查回译文，返回 {lang: {(context, source): translation}}。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QTranslator

    app = QCoreApplication.instance() or QCoreApplication([])
    recovered: dict[str, dict[tuple[str, str], str]] = {}
    for lang in LANGUAGES:
        qm_file = TRANSLATIONS / f"mikancl_{lang}.qm"
        mapping: dict[tuple[str, str], str] = {}
        translator = QTranslator(app)
        if qm_file.is_file() and translator.load(str(qm_file)):
            app.installTranslator(translator)
            for context, sources in messages.items():
                for source in sources:
                    translated = translator.translate(context, source, None)
                    if translated and translated != source:
                        mapping[(context, source)] = translated
            app.removeTranslator(translator)
        recovered[lang] = mapping
    return recovered


def write_ts(lang: str, messages: dict[str, list[str]], mapping: dict[tuple[str, str], str]) -> Path:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE TS>',
        f'<TS version="2.1" language="{lang}">',
    ]
    for context, sources in messages.items():
        lines.append("    <context>")
        lines.append(f"        <name>{escape(context)}</name>")
        for source in sources:
            lines.append("        <message>")
            lines.append(f"            <source>{escape(source)}</source>")
            text = mapping.get((context, source), source)
            lines.append(f"            <translation>{escape(text)}</translation>")
            lines.append("        </message>")
        lines.append("    </context>")
    lines.append("</TS>")
    target = TRANSLATIONS / f"mikancl_{lang}.ts"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main() -> int:
    messages = extract()
    total = sum(len(items) for items in messages.values())
    print(f"提取到 {total} 条字符串，{len(messages)} 个上下文")
    recovered = build_ts(messages)
    for context, mapping in EN_SUPPLEMENTS.items():
        for source, text in mapping.items():
            recovered["en_US"].setdefault((context, source), text)
    # 共享词典只补空白：精确补充表与旧 .qm 里已有的译文优先级更高
    for lang, table in SHARED_TRANSLATIONS.items():
        if lang not in recovered:
            continue
        for context, sources in messages.items():
            for source in sources:
                key = (context, source)
                if key not in recovered[lang] and source in table:
                    recovered[lang][key] = table[source]
    for lang in LANGUAGES:
        ts_file = write_ts(lang, messages, recovered[lang])
        print(f"写入 {ts_file.name}：{len(recovered[lang])} 条已有译文")

    import shutil

    lrelease = shutil.which("pyside6-lrelease") or str(
        Path(sys.executable).parent / "Scripts" / "pyside6-lrelease.exe"
    )
    if Path(lrelease).is_file():
        subprocess.call(
            [str(lrelease)]
            + [str(TRANSLATIONS / f"mikancl_{lang}.ts") for lang in LANGUAGES]
        )
        print("已重新编译 .qm")
    else:
        print("未找到 pyside6-lrelease，跳过 .qm 编译")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
