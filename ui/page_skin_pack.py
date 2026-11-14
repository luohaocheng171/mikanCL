"""皮肤包页：按目标玩家生成 / 分享 / 安装皮肤包。

只有安装 CustomSkinLoader 时才能做到「只让某个玩家拥有这张皮肤」；
资源包仅作为兜底，且默认不启用，避免服务器上其他默认皮肤玩家一起变形。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import DATA_DIR
from ..context import AppContext
from ..i18n import t
from ..skinpack import (
    MODEL_LABELS,
    SkinPackError,
    export_skin_pack,
    install_skin_pack,
    pack_info,
    purge_old_packs,
    read_skin_pack,
)
from ..version import scan_installed_versions
from ..ui_pack import (
    UiPackError,
    apply_ui_pack,
    export_ui_pack,
    ui_pack_filename,
    ui_pack_info,
)
from .widgets import Card, ask_skin_model, card_title_row, page_header

# 没有安装版本时也给出常见版本，便于替其他玩家打包
SAMPLE_VERSIONS = (
    "1.5.2", "1.8.9", "1.12.2", "1.16.5", "1.20.1", "1.20.4",
    "1.21.8", "1.21.9", "1.21.11", "26.1", "26.3", "26.4",
)


class SkinPackPage(QWidget):
    """独立标签页：生成可分享皮肤包、把皮肤包安装到本机。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._skin_path = ""
        self._cape_path = ""
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(16)
        header, _ = page_header(
            t("SkinPack", "皮肤包 / UI 材质包"),
            t(
                "SkinPack",
                "上方「一键安装并替换旧包」可直接生成半透明毛玻璃 UI 材质包（自动识别版本）；"
                "下方按目标玩家 + 手臂模型 + 游戏版本打包皮肤，需要 CustomSkinLoader 才能只对指定玩家生效",
            ),
        )
        outer.addWidget(header)

        ui_card = Card()
        ui_card.body.addWidget(
            card_title_row(
                t("SkinPack", "半透明毛玻璃 UI 材质包"),
                t("SkinPack", "一键安装并替换旧包 · 自动识别版本，按钮 / 面板 / 快捷栏统一磨砂半透明"),
            )
        )
        ui_row = QHBoxLayout()
        ui_row.setSpacing(8)
        ui_row.addWidget(QLabel(t("SkinPack", "适配版本")))
        self.ui_version_combo = QComboBox()
        self.ui_version_combo.setEditable(True)
        self.ui_version_combo.setMinimumWidth(160)
        self.ui_version_combo.currentTextChanged.connect(self._update_ui_hint)
        ui_row.addWidget(self.ui_version_combo, 1)
        self.ui_format_label = QLabel("")
        self.ui_format_label.setObjectName("Tiny")
        ui_row.addWidget(self.ui_format_label, 1)
        ui_card.body.addLayout(ui_row)

        self.ui_enable_check = QCheckBox(
            t("SkinPack", "安装后自动在游戏内启用（1.6.1+ 资源包）")
        )
        self.ui_enable_check.setChecked(True)
        ui_card.body.addWidget(self.ui_enable_check)

        ui_action_row = QHBoxLayout()
        ui_action_row.setSpacing(8)
        ui_install_btn = QPushButton(t("SkinPack", "一键安装并替换旧包"))
        ui_install_btn.setObjectName("Primary")
        ui_install_btn.setMinimumHeight(34)
        ui_install_btn.clicked.connect(self._install_ui_pack)
        ui_action_row.addWidget(ui_install_btn)
        ui_all_btn = QPushButton(t("SkinPack", "全部版本一键替换"))
        ui_all_btn.clicked.connect(self._install_ui_pack_all)
        ui_action_row.addWidget(ui_all_btn)
        ui_export_btn = QPushButton(t("SkinPack", "导出 UI 包…"))
        ui_export_btn.clicked.connect(self._export_ui_pack)
        ui_action_row.addWidget(ui_export_btn)
        ui_action_row.addStretch(1)
        ui_card.body.addLayout(ui_action_row)

        self.ui_status = QLabel("")
        self.ui_status.setObjectName("Tiny")
        self.ui_status.setWordWrap(True)
        ui_card.body.addWidget(self.ui_status)

        ui_hint = QLabel(
            t(
                "SkinPack",
                "材质取自对应版本的客户端 jar 并原位改造：按钮、输入框、滑块、背包/箱子面板与"
                "快捷栏保留原版尺寸与九宫格切图，统一换成半透明冷色磨砂（菜单按钮最透，"
                "背包面板稍保守以保证看清物品）；菜单平铺背景换成程序生成的无缝玻璃瓦片。"
                "重复安装会自动替换旧 UI 包，不会越装越多。"
                "1.0–1.5.2 生成 texturepacks 纹理包，需要在游戏「材质包」里手动选中；"
                "1.6.1+ 生成资源包并自动启用。找不到客户端 jar 时只生成玻璃背景层。",
            )
        )
        ui_hint.setObjectName("Tiny")
        ui_hint.setWordWrap(True)
        ui_card.body.addWidget(ui_hint)
        outer.addWidget(ui_card)

        make_card = Card()
        make_card.body.addWidget(
            card_title_row(
                t("SkinPack", "生成皮肤包"),
                t("SkinPack", "导出给其他玩家，或直接安装到本机游戏目录"),
            )
        )

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_row.addWidget(QLabel(t("SkinPack", "皮肤来源")))
        self.source_combo = QComboBox()
        self.source_combo.addItem(t("SkinPack", "当前账号皮肤"), "account")
        self.source_combo.addItem(t("SkinPack", "皮肤库 / 本地 PNG"), "file")
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        source_row.addWidget(self.source_combo, 1)
        pick_btn = QPushButton(t("SkinPack", "选择 PNG…"))
        pick_btn.setObjectName("Ghost")
        pick_btn.clicked.connect(self._pick_png)
        source_row.addWidget(pick_btn)
        make_card.body.addLayout(source_row)
        self.source_label = QLabel("")
        self.source_label.setObjectName("Tiny")
        self.source_label.setWordWrap(True)
        make_card.body.addWidget(self.source_label)

        player_row = QHBoxLayout()
        player_row.setSpacing(8)
        player_row.addWidget(QLabel(t("SkinPack", "目标玩家")))
        self.player_edit = QLineEdit()
        self.player_edit.setPlaceholderText(t("SkinPack", "服务器上要显示这张皮肤的玩家名"))
        self.player_edit.setMaxLength(16)
        player_row.addWidget(self.player_edit, 1)
        player_row.addWidget(QLabel(t("SkinPack", "手臂模型")))
        self.model_combo = QComboBox()
        self.model_combo.addItem(t("SkinPack", "Steve（经典）"), "classic")
        self.model_combo.addItem(t("SkinPack", "Alex（纤细）"), "slim")
        player_row.addWidget(self.model_combo)
        make_card.body.addLayout(player_row)

        cape_row = QHBoxLayout()
        cape_row.setSpacing(8)
        cape_row.addWidget(QLabel(t("SkinPack", "披风（可选）")))
        self.cape_edit = QLineEdit()
        self.cape_edit.setPlaceholderText(t("SkinPack", "64×32 披风 PNG，留空则不写入披风"))
        self.cape_edit.setReadOnly(True)
        cape_row.addWidget(self.cape_edit, 1)
        cape_btn = QPushButton(t("SkinPack", "选择披风…"))
        cape_btn.setObjectName("Ghost")
        cape_btn.clicked.connect(self._pick_cape)
        cape_row.addWidget(cape_btn)
        cape_clear = QPushButton(t("SkinPack", "清除"))
        cape_clear.setObjectName("Ghost")
        cape_clear.clicked.connect(self._clear_cape)
        cape_row.addWidget(cape_clear)
        make_card.body.addLayout(cape_row)
        self.elytra_check = QCheckBox(
            t("SkinPack", "把披风同时作为鞘翅纹理写入 LocalSkin/elytra")
        )
        self.elytra_check.setChecked(False)
        make_card.body.addWidget(self.elytra_check)

        version_row = QHBoxLayout()
        version_row.setSpacing(8)
        version_row.addWidget(QLabel(t("SkinPack", "适配版本")))
        self.version_combo = QComboBox()
        self.version_combo.setEditable(True)
        self.version_combo.setMinimumWidth(160)
        self.version_combo.currentTextChanged.connect(self._update_format_hint)
        version_row.addWidget(self.version_combo, 1)
        self.format_label = QLabel("")
        self.format_label.setObjectName("Tiny")
        version_row.addWidget(self.format_label, 1)
        make_card.body.addLayout(version_row)

        self.enable_check = QCheckBox(
            t("SkinPack", "同时启用兜底资源包（未装 CustomSkinLoader 时也能看到，但会替换服务器其他默认皮肤）")
        )
        self.enable_check.setChecked(False)
        make_card.body.addWidget(self.enable_check)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        export_btn = QPushButton(t("SkinPack", "导出皮肤包…"))
        export_btn.setObjectName("Primary")
        export_btn.clicked.connect(self._export)
        action_row.addWidget(export_btn)
        install_btn = QPushButton(t("SkinPack", "生成并安装到本机"))
        install_btn.clicked.connect(self._install_local)
        action_row.addWidget(install_btn)
        overwrite_btn = QPushButton(t("SkinPack", "一键添加并覆盖旧皮肤包"))
        overwrite_btn.clicked.connect(self._overwrite_local)
        action_row.addWidget(overwrite_btn)
        action_row.addStretch(1)
        make_card.body.addLayout(action_row)

        hint = QLabel(
            t(
                "SkinPack",
                "1.0–1.5.2 会生成 texturepacks 纹理包；1.6.1–1.21.8 使用 pack_format + "
                "supported_formats 1–99；1.21.9+ / 26.x 使用 min_format + max_format。"
                "资源包同时写入新旧两套玩家皮肤路径，导出的文件可直接放进 resourcepacks 加载。"
                "目标玩家皮肤写入 CustomSkinLoader/LocalSkin/skins/<玩家名>.png。"
                "「一键添加并覆盖旧皮肤包」会先清理旧的 MikanCL 包再写入，"
                "避免旧包残留导致误以为新皮肤已生效。",
            )
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        make_card.body.addWidget(hint)
        outer.addWidget(make_card)

        import_card = Card()
        import_card.body.addWidget(
            card_title_row(
                t("SkinPack", "导入皮肤包"),
                t("SkinPack", "支持 MikanCL 皮肤包（.zip）或单张 PNG，导入时会询问手臂模型"),
            )
        )
        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        import_btn = QPushButton(t("SkinPack", "选择皮肤包…"))
        import_btn.clicked.connect(self._import_pack)
        import_row.addWidget(import_btn)
        self.import_status = QLabel("")
        self.import_status.setObjectName("Tiny")
        self.import_status.setWordWrap(True)
        import_row.addWidget(self.import_status, 1)
        import_card.body.addLayout(import_row)

        share_hint = QLabel(
            t(
                "SkinPack",
                "分享给其他玩家时，对方安装本皮肤包并启用 CustomSkinLoader 后，"
                "在服务器里就能按玩家名看到这张皮肤，不会影响其他人的外观。",
            )
        )
        share_hint.setObjectName("Tiny")
        share_hint.setWordWrap(True)
        import_card.body.addWidget(share_hint)
        outer.addWidget(import_card)
        outer.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        account = self.ctx.current_account()
        if account is not None and not self.player_edit.text().strip():
            self.player_edit.setText(account.name)
        if not self._skin_path and account is not None and account.skin_path:
            self._skin_path = account.skin_path
            self.source_combo.setCurrentIndex(0)
        self._reload_versions()
        self._update_source_label()
        self._update_format_hint()
        self._update_ui_hint()

    def _reload_versions(self) -> None:
        current = self.version_combo.currentText().strip()
        ui_current = ""
        if hasattr(self, "ui_version_combo"):
            ui_current = self.ui_version_combo.currentText().strip()
        versions: list[str] = []
        installed_ids: list[str] = []
        try:
            installed = scan_installed_versions(Path(self.ctx.config.game_path))
            installed_ids = [item.id for item in installed]
            versions = list(installed_ids)
        except OSError:
            versions = []
        for sample in SAMPLE_VERSIONS:
            if sample not in versions:
                versions.append(sample)
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        for item in versions:
            self.version_combo.addItem(item)
        if current:
            self.version_combo.setEditText(current)
        elif versions:
            preferred = self.version_combo.findText("1.21.8")
            self.version_combo.setCurrentIndex(preferred if preferred >= 0 else 0)
        self.version_combo.blockSignals(False)
        # UI 材质包只针对本机真实安装的版本，没装过时退回常见版本列表
        if hasattr(self, "ui_version_combo"):
            self.ui_version_combo.blockSignals(True)
            self.ui_version_combo.clear()
            for item in installed_ids or versions:
                self.ui_version_combo.addItem(item)
            if ui_current:
                self.ui_version_combo.setEditText(ui_current)
            elif installed_ids:
                preferred = self.ui_version_combo.findText(
                    str(self.ctx.config.default_version_id or "")
                )
                self.ui_version_combo.setCurrentIndex(preferred if preferred >= 0 else 0)
            self.ui_version_combo.blockSignals(False)

    def _on_source_changed(self) -> None:
        if str(self.source_combo.currentData()) == "account":
            account = self.ctx.current_account()
            if account is not None and account.skin_path:
                self._skin_path = account.skin_path
                if not self.player_edit.text().strip():
                    self.player_edit.setText(account.name)
                if str(self.model_combo.currentData()) == "classic" and account.skin_model:
                    self._set_model(account.skin_model)
        self._update_source_label()

    def _update_source_label(self) -> None:
        if self._skin_path and Path(self._skin_path).is_file():
            self.source_label.setText(
                t("SkinPack", "当前皮肤：{0}", self._skin_path)
            )
        else:
            self.source_label.setText(
                t("SkinPack", "尚未选择皮肤，请先选择 PNG 或切换到一个有本地皮肤的账号。")
            )

    def _set_model(self, model: str) -> None:
        index = self.model_combo.findData("slim" if model == "slim" else "classic")
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

    def _update_format_hint(self) -> None:
        version = self.version_combo.currentText().strip()
        info = pack_info(version)
        self.format_label.setText(
            t("SkinPack", "格式：{0}", info["label"])
        )

    def _pick_png(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, t("SkinPack", "选择皮肤 PNG"), str(Path.home()), "PNG 图片 (*.png)"
        )
        if not path:
            return
        self._skin_path = path
        self.source_combo.setCurrentIndex(1)
        self._update_source_label()

    def _pick_cape(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, t("SkinPack", "选择披风 PNG（64×32）"), str(Path.home()), "PNG 图片 (*.png)"
        )
        if not path:
            return
        self._cape_path = path
        self.cape_edit.setText(path)
        self.cape_edit.setToolTip(path)

    def _clear_cape(self) -> None:
        self._cape_path = ""
        self.cape_edit.clear()
        self.cape_edit.setToolTip("")

    def _cape_bytes(self) -> bytes:
        path = getattr(self, "_cape_path", "")
        if not path or not Path(path).is_file():
            return b""
        try:
            return Path(path).read_bytes()
        except OSError:
            return b""

    def _current_version(self) -> str:
        return self.version_combo.currentText().strip() or "1.21.8"

    def _validate_input(self) -> tuple[str, str, str] | None:
        if not self._skin_path or not Path(self._skin_path).is_file():
            QMessageBox.information(
                self, APP_NAME, t("SkinPack", "请先选择皮肤来源。")
            )
            return None
        player = self.player_edit.text().strip()
        if not player:
            QMessageBox.information(
                self, APP_NAME, t("SkinPack", "请填写目标玩家名。")
            )
            return None
        model = str(self.model_combo.currentData() or "classic")
        return self._skin_path, player, model

    def _export(self) -> None:
        data = self._validate_input()
        if data is None:
            return
        skin_path, player, model = data
        version = self._current_version()
        # 导入 / 打包前确认手臂模型
        chosen = ask_skin_model(self, model)
        if chosen is None:
            return
        model = chosen
        self._set_model(model)
        target, _ = QFileDialog.getSaveFileName(
            self,
            t("SkinPack", "保存皮肤包"),
            str(Path.home() / f"MikanCL-{player}-皮肤包.zip"),
            "MikanCL 皮肤包 (*.zip)",
        )
        if not target:
            return
        try:
            path = export_skin_pack(
                target, skin_path, player, model, version, self._cape_path or None
            )
        except SkinPackError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.ctx.bus.log.emit(f"[皮肤包] 已导出 {path}（{version} · {MODEL_LABELS[model]}）")
        QMessageBox.information(
            self,
            APP_NAME,
            t(
                "SkinPack",
                "皮肤包已导出：\n{0}\n目标玩家：{1}\n手臂模型：{2}\n适配版本：{3}",
                str(path),
                player,
                MODEL_LABELS.get(model, model),
                version,
            ),
        )

    def _install_local(self) -> None:
        data = self._validate_input()
        if data is None:
            return
        skin_path, player, model = data
        chosen = ask_skin_model(self, model)
        if chosen is None:
            return
        model = chosen
        self._set_model(model)
        version = self._current_version()
        try:
            results = self._install_to_game_dirs(
                lambda game_dir: self._apply_skin(
                    Path(skin_path).read_bytes(), player, model, game_dir, version
                )
            )
        except SkinPackError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"读取皮肤文件失败：{exc}")
            return
        QMessageBox.information(
            self,
            APP_NAME,
            t(
                "SkinPack",
                "已写入 {0} 个游戏目录：\n{1}\n需要 CustomSkinLoader 才能在游戏内只对 {2} 生效。",
                str(len(results)),
                "\n".join(results),
                player,
            ),
        )

    def _apply_skin(self, image: bytes, player: str, model: str, game_dir: Path, version: str) -> str:
        from ..skinpack import apply_player_skin_bytes

        cape = self._cape_bytes()
        result = apply_player_skin_bytes(
            image,
            player,
            model,
            game_dir,
            version,
            install_pack=True,
            enable_pack=self.enable_check.isChecked(),
            cape=cape or None,
            elytra=cape if cape and self.elytra_check.isChecked() else None,
        )
        self.ctx.bus.log.emit(
            f"[皮肤包] 已写入 {result['skin']}（{version} · {MODEL_LABELS.get(model, model)}）"
        )
        return result["skin"]

    def _game_dirs(self, version: str = "") -> list[Path]:
        """主目录；全部隔离时再加隔离目录（皮肤需要写两份）。"""
        config = self.ctx.config
        version = version or self._current_version()
        return config.resolve_game_dirs(version).skin_targets()

    def _install_to_game_dirs(self, apply, version: str = "") -> list[str]:
        results: list[str] = []
        for game_dir in self._game_dirs(version):
            game_dir.mkdir(parents=True, exist_ok=True)
            results.append(apply(game_dir))
        return results

    def _overwrite_local(self) -> None:
        """一键添加并覆盖旧皮肤包：先清理全部旧 MikanCL 包，再写入当前皮肤。"""
        data = self._validate_input()
        if data is None:
            return
        skin_path, player, model = data
        chosen = ask_skin_model(self, model)
        if chosen is None:
            return
        model = chosen
        self._set_model(model)
        version = self._current_version()
        removed: list[str] = []
        results: list[str] = []
        try:
            for game_dir in self._game_dirs(version):
                game_dir.mkdir(parents=True, exist_ok=True)
                removed.extend(purge_old_packs(game_dir))
                results.append(
                    self._apply_skin(Path(skin_path).read_bytes(), player, model, game_dir, version)
                )
        except SkinPackError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"读取皮肤文件失败：{exc}")
            return
        self.ctx.bus.log.emit(
            f"[皮肤包] 已覆盖旧包 {len(removed)} 个，写入 {len(results)} 个游戏目录（{version} · {player}）"
        )
        QMessageBox.information(
            self,
            APP_NAME,
            t(
                "SkinPack",
                "已清理 {0} 个旧皮肤包，并重新写入 {1} 个游戏目录：\n{2}\n目标玩家：{3}\n适配版本：{4}",
                str(len(removed)),
                str(len(results)),
                "\n".join(results),
                player,
                version,
            ),
        )

    def _import_pack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("SkinPack", "选择皮肤包"),
            str(DATA_DIR),
            "皮肤包 (*.zip *.png)",
        )
        if not path:
            return
        try:
            data = read_skin_pack(path)
        except SkinPackError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        model = data.get("model") or str(self.model_combo.currentData() or "classic")
        chosen = ask_skin_model(self, model)
        if chosen is None:
            return
        model = chosen
        player = data.get("player") or self.player_edit.text().strip()
        if not player:
            player, ok = QInputDialog.getText(
                self,
                t("SkinPack", "目标玩家"),
                t("SkinPack", "皮肤包里没有玩家名，请输入要应用到的玩家名："),
            )
            if not ok or not player.strip():
                return
        player = player.strip()
        # 用本机选择的版本重新生成兜底资源包，而不是沿用分享者的版本
        version = self._current_version()
        self.player_edit.setText(player)
        self._set_model(model)
        try:
            results = self._install_to_game_dirs(
                lambda game_dir: install_skin_pack(
                    path,
                    game_dir,
                    player=player,
                    model=model,
                    version_id=version,
                    enable_pack=self.enable_check.isChecked(),
                )["skin"],
                version,
            )
        except SkinPackError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.import_status.setText(
            t(
                "SkinPack",
                "已导入 {0}：{1}（{2}，{3}）",
                Path(path).name,
                player,
                MODEL_LABELS.get(model, model),
                pack_info(version)["label"],
            )
        )
        self.ctx.bus.log.emit(f"[皮肤包] 已导入 {path} → {', '.join(results)}")
        self.ctx.bus.toast.emit(
            t("SkinPack", "皮肤包已导入：{0}", player)
        )

    def _ui_version(self) -> str:
        return self.ui_version_combo.currentText().strip() or "1.21.8"

    def _update_ui_hint(self) -> None:
        if not hasattr(self, "ui_format_label"):
            return
        info = ui_pack_info(self._ui_version())
        self.ui_format_label.setText(t("SkinPack", "格式：{0}", info["hint"]))

    def _install_ui_pack(self) -> None:
        version = self._ui_version()
        try:
            result = apply_ui_pack(
                self.ctx.config, version, enable=self.ui_enable_check.isChecked()
            )
        except UiPackError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"写入 UI 材质包失败：{exc}")
            return
        note = ""
        if not result["has_jar"]:
            note = t("SkinPack", "\n未找到该版本的客户端 jar，本次只生成了玻璃背景层。")
        lines = "\n".join(result["paths"])
        self.ui_status.setText(
            t("SkinPack", "已安装到 {0} 个目录：{1}{2}", str(len(result["paths"])), lines, note)
        )
        self.ctx.bus.log.emit(f"[UI材质包] {version} → {', '.join(result['paths'])}")
        QMessageBox.information(
            self,
            APP_NAME,
            t(
                "SkinPack",
                "UI 材质包已生成：\n{0}\n版本：{1}（{2}）{3}",
                lines,
                version,
                result["label"],
                note,
            ),
        )

    def _install_ui_pack_all(self) -> None:
        try:
            versions = [
                item.id
                for item in scan_installed_versions(Path(self.ctx.config.game_path))
            ]
        except OSError:
            versions = []
        if not versions:
            QMessageBox.information(
                self, APP_NAME, t("SkinPack", "没有检测到已安装的游戏版本。")
            )
            return
        enable = self.ui_enable_check.isChecked()
        done = 0
        failed: list[str] = []
        for version in versions:
            try:
                apply_ui_pack(self.ctx.config, version, enable=enable)
                done += 1
            except (UiPackError, OSError):
                failed.append(version)
        summary = t(
            "SkinPack", "已为 {0} 个版本生成 UI 材质包。", str(done)
        )
        if failed:
            summary += t("SkinPack", " 失败：{0}", "、".join(failed))
        self.ui_status.setText(summary)
        self.ctx.bus.log.emit(f"[UI材质包] 批量生成完成：{done} 个版本，失败 {len(failed)} 个")
        QMessageBox.information(self, APP_NAME, summary)

    def _export_ui_pack(self) -> None:
        version = self._ui_version()
        target, _ = QFileDialog.getSaveFileName(
            self,
            t("SkinPack", "保存 UI 材质包"),
            str(Path.home() / ui_pack_filename(version)),
            "UI 材质包 (*.zip)",
        )
        if not target:
            return
        try:
            path = export_ui_pack(target, version, game_root=self.ctx.config.game_path)
        except UiPackError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.ctx.bus.log.emit(f"[UI材质包] 已导出 {path}（{version}）")
        QMessageBox.information(
            self,
            APP_NAME,
            t("SkinPack", "UI 材质包已导出：\n{0}\n适配版本：{1}", str(path), version),
        )

    def shutdown(self) -> None:
        pass


__all__ = ["SkinPackPage"]
