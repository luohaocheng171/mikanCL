"""国际化（i18n）：加载 .qm 翻译文件并提供翻译函数。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtWidgets import QApplication

SUPPORTED_LANGUAGES = {
    "zh_CN": "简体中文",
    "en_US": "English",
    "ru_RU": "Русский",
    "fr_FR": "Français",
    "ja_JP": "日本語",
}
DEFAULT_LANGUAGE = "zh_CN"


def translations_dir() -> Path:
    """翻译目录：源码运行时位于 mc_launcher/translations，打包后位于解包目录。"""
    return Path(__file__).resolve().parent / "translations"


def translation_file(lang_code: str) -> Path:
    return translations_dir() / f"mikancl_{lang_code}.qm"


class Translator:
    """管理 QTranslator 的安装与切换；.qm 缺失时保留中文原文。"""

    def __init__(self, app: QApplication):
        self._app = app
        self._translator: QTranslator | None = None
        self._current = DEFAULT_LANGUAGE
        # 挂到 app 上，避免 Translator / QTranslator 被垃圾回收
        app._i18n_translator = self  # type: ignore[attr-defined]

    def load(self, lang_code: str) -> bool:
        # 先移除旧 translator，再加载新的翻译文件
        old = self._translator
        if old is not None:
            self._app.removeTranslator(old)
            self._translator = None

        supported = lang_code in SUPPORTED_LANGUAGES
        code = lang_code if supported else DEFAULT_LANGUAGE
        if not self._install(code):
            # 目标语言缺失时回退中文；中文 .qm 也缺失时保留原文
            if code != DEFAULT_LANGUAGE:
                self._install(DEFAULT_LANGUAGE)
            self._current = DEFAULT_LANGUAGE
            return False

        self._current = code
        return supported

    def _install(self, code: str) -> bool:
        translator = QTranslator(self._app)
        if not translator.load(str(translation_file(code))):
            return False
        self._app.installTranslator(translator)
        self._translator = translator
        return True

    def current(self) -> str:
        return self._current

    def available(self) -> dict[str, str]:
        return dict(SUPPORTED_LANGUAGES)


def t(context: str, text: str, *args) -> str:
    """按 context 翻译 text；找不到翻译时返回原文，args 按 str.format 填充。"""
    translated = QCoreApplication.translate(context, text) or text
    if args:
        try:
            return str(translated).format(*args)
        except (IndexError, KeyError, ValueError):
            return str(translated)
    return str(translated)


__all__ = [
    "SUPPORTED_LANGUAGES",
    "DEFAULT_LANGUAGE",
    "Translator",
    "t",
    "translations_dir",
    "translation_file",
]
