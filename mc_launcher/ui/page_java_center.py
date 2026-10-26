"""Java 中心：主流发行版一键下载安装，任务统一登记到下载中心（kind="Java"）。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR
from ..context import AppContext, wait_thread
from ..java import adoptium_asset, detect_java_installed, download_java, find_java_in
from ..net import Cancelled, DownloadError, Http
from .widgets import Card, Badge, page_header

# 与设置页的 Java 下载目录保持一致
JAVA_ROOT = DATA_DIR / "runtime"


@dataclass
class JavaOffer:
    vendor: str
    version: int
    arch: str = "x64"
    source: str = ""
    resolver: str = ""


def _offers() -> list[JavaOffer]:
    specs = [
        ("Adoptium Temurin", (17, 21), "Adoptium 官方 API", "adoptium"),
        ("Microsoft OpenJDK", (17, 21), "Microsoft 官方 / aka.ms", "microsoft"),
        ("Azul Zulu", (8, 17, 21), "Azul 元数据 API", "azul"),
        ("Amazon Corretto", (8, 17, 21), "GitHub Releases", "corretto"),
        ("Alibaba Dragonwell", (11, 17), "GitHub Releases", "dragonwell"),
        ("Tencent Kona", (8, 17), "GitHub Releases", "kona"),
    ]
    result: list[JavaOffer] = []
    for vendor, versions, source, key in specs:
        for version in versions:
            result.append(
                JavaOffer(vendor=vendor, version=version, source=source, resolver=key)
            )
    return result


# ---------------------------------------------------------------------------
# 下载地址解析（每个厂商独立实现；失败时由页面提示并禁用该行，不阻塞整体）
# ---------------------------------------------------------------------------
def _resolve_adoptium(offer: JavaOffer) -> dict:
    asset = adoptium_asset(offer.version)
    return {"url": asset["url"], "size": asset.get("size") or 0, "name": asset["name"]}


def _scan_ms_rows(data, major: int) -> str:
    rows = data if isinstance(data, list) else (
        (data.get("data") or data.get("downloads") or []) if isinstance(data, dict) else []
    )
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or row.get("download_url") or "")
        version = str(row.get("version") or "")
        os_name = str(row.get("os") or "")
        arch = str(row.get("arch") or "")
        if url.startswith("http") and ".zip" in url:
            if version.startswith(f"{major}.") or (
                "windows" in url.lower() or os_name.lower() == "windows"
            ) and (arch in ("x64", "") or f"-{major}-" in url):
                return url
    return ""


def _resolve_microsoft(offer: JavaOffer) -> dict:
    http = Http(timeout=30)
    template = f"https://aka.ms/download-jdk/microsoft-jdk-{offer.version}-windows-x64.zip"
    try:
        http.request(template, "HEAD", timeout=20)
        return {
            "url": template,
            "size": 0,
            "name": f"microsoft-jdk-{offer.version}-windows-x64.zip",
        }
    except DownloadError:
        pass
    # 兜底：尝试解析下载列表 JSON（结构变化时提示不可用）
    try:
        data = http.get_json_url("https://api.microsoft.com/software/openjdk", timeout=20)
    except DownloadError:
        data = None
    if data is not None:
        url = _scan_ms_rows(data, offer.version)
        if url:
            return {"url": url, "size": 0, "name": url.rsplit("/", 1)[-1] or "openjdk.zip"}
    raise DownloadError(
        f"未能获取 Microsoft OpenJDK {offer.version} 的下载地址（服务不可用）。"
    )


def _resolve_azul(offer: JavaOffer) -> dict:
    url = (
        "https://api.azul.com/metadata/v1/zulu/packages/"
        f"?java_version={offer.version}&os=windows&arch=x64&archive_type=zip"
        "&java_package_type=jre&latest=true&release_status=ga&availability_types=CA"
    )
    data = Http(timeout=30).get_json_url(url)
    if not isinstance(data, list) or not data:
        raise DownloadError(f"Azul 未返回 Java {offer.version} 的 Windows JRE 包")
    for row in data:
        if isinstance(row, dict) and row.get("download_url"):
            return {
                "url": str(row["download_url"]),
                "size": int(row.get("size") or 0),
                "name": str(row.get("name") or ""),
            }
    raise DownloadError(f"Azul 返回的 Java {offer.version} 下载地址为空")


def _resolve_github(offer: JavaOffer, repo: str, keywords: tuple[str, ...]) -> dict:
    data = Http(timeout=30).get_json_url(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json"},
    )
    assets = data.get("assets") if isinstance(data, dict) else []
    if not isinstance(assets, list):
        raise DownloadError(f"{repo} 发布信息格式异常")
    zips = [
        item
        for item in assets
        if isinstance(item, dict)
        and str(item.get("browser_download_url") or "").lower().endswith(".zip")
        and all(key in str(item.get("name") or "").lower() for key in keywords)
    ]
    if not zips:
        raise DownloadError(f"{repo} 未找到 Windows x64 的 zip 安装包")
    first = zips[0]
    return {
        "url": str(first["browser_download_url"]),
        "size": int(first.get("size") or 0),
        "name": str(first.get("name") or ""),
    }


def _resolve_corretto(offer: JavaOffer) -> dict:
    return _resolve_github(offer, f"corretto/corretto-{offer.version}", ("windows", "x64"))


def _resolve_dragonwell(offer: JavaOffer) -> dict:
    return _resolve_github(
        offer, f"alibaba/dragonwell{offer.version}", ("windows", "x64")
    )


def _resolve_kona(offer: JavaOffer) -> dict:
    return _resolve_github(
        offer, f"Tencent/TencentKona-{offer.version}", ("windows", "x64")
    )


def resolve_offer(offer: JavaOffer) -> dict:
    """解析某个发行版的下载地址，返回 {"url","size","name"}；失败抛 DownloadError。"""
    if offer.resolver == "adoptium":
        return _resolve_adoptium(offer)
    if offer.resolver == "microsoft":
        return _resolve_microsoft(offer)
    if offer.resolver == "azul":
        return _resolve_azul(offer)
    if offer.resolver == "corretto":
        return _resolve_corretto(offer)
    if offer.resolver == "dragonwell":
        return _resolve_dragonwell(offer)
    if offer.resolver == "kona":
        return _resolve_kona(offer)
    raise DownloadError(f"未知的发行版解析器：{offer.resolver}")


# ---------------------------------------------------------------------------
class ResolveWorker(QThread):
    done = Signal(int, dict)  # (row, {url,size,name})
    failed = Signal(int, str)  # (row, message)

    def __init__(self, offer: JavaOffer, row: int, parent=None):
        super().__init__(parent)
        self.offer = offer
        self.row = row

    def run(self) -> None:
        try:
            result = resolve_offer(self.offer)
            self.done.emit(self.row, result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self.row, str(exc))


class JavaCenterInstallWorker(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, float)  # 0~1 进度, 字节/秒

    def __init__(
        self,
        major: int,
        dest_root: Path,
        task_id: str = "",
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        url: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.major = int(major)
        self.dest_root = Path(dest_root)
        self.task_id = task_id
        self.cancel_event = cancel_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.url = url

    def run(self) -> None:
        state = {"total": 0, "bytes": 0, "last_t": time.time(), "last_b": 0}

        def on_total(total: int) -> None:
            state["total"] = int(total)

        def on_bytes(n: int) -> None:
            state["bytes"] += n
            now = time.time()
            if now - state["last_t"] < 0.25:
                return
            dt = now - state["last_t"]
            speed = (state["bytes"] - state["last_b"]) / dt if dt > 0 else 0.0
            state["last_t"], state["last_b"] = now, state["bytes"]
            total = state["total"]
            percent = min(1.0, state["bytes"] / total) if total else 0.0
            self.progress.emit(percent, speed)

        try:
            info = download_java(
                self.major,
                self.dest_root,
                log=lambda text: None,
                on_bytes=on_bytes,
                cancel=self.cancel_event,
                pause=self.pause_event,
                on_total=on_total,
                url=self.url,
            )
            self.done.emit(info)
        except Cancelled:
            pass  # 已由下载中心标记为取消
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
class JavaCenterPage(QWidget):
    """Java 中心页：表格式列出主流发行版，支持检查可用与一键安装。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._offers = _offers()
        self._resolved: dict[int, dict] = {}
        self._failed: dict[int, str] = {}
        self._busy_rows: set[int] = set()
        self._check_buttons: dict[int, QPushButton] = {}
        self._install_buttons: dict[int, QPushButton] = {}
        self._status_items: dict[int, QTableWidgetItem] = {}
        self._workers: list[QThread] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(14)
        header, _ = page_header("Java 中心", "常用发行版一键下载安装到本地运行时目录（data/runtime）")
        outer.addWidget(header)

        card = Card(margins=14, spacing=10)
        tip = QLabel(
            "点击“检查可用”联网解析下载地址；解析失败的行会禁用安装按钮，不影响其他行。"
            "安装任务统一登记到下载中心，可暂停 / 取消 / 重试。"
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        card.body.addWidget(tip)

        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["发行版 / 版本", "架构", "来源", "状态", "操作"])
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.setColumnWidth(1, 64)
        table.setColumnWidth(3, 130)
        table.setColumnWidth(4, 210)
        table.verticalHeader().setDefaultSectionSize(38)
        card.body.addWidget(table, 1)
        self._table = table
        outer.addWidget(card, 1)

        for row, offer in enumerate(self._offers):
            table.insertRow(row)
            name_item = QTableWidgetItem(f"{offer.vendor} · Java {offer.version}")
            table.setItem(row, 0, name_item)
            arch_badge = Badge(offer.arch, "blue")
            arch_wrap = QWidget()
            arch_layout = QHBoxLayout(arch_wrap)
            arch_layout.setContentsMargins(0, 0, 0, 0)
            arch_layout.addWidget(arch_badge, 0, Qt.AlignCenter)
            table.setCellWidget(row, 1, arch_wrap)
            table.setItem(row, 2, QTableWidgetItem(offer.source))
            status_item = QTableWidgetItem("待检查")
            status_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 3, status_item)
            self._status_items[row] = status_item

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(6, 2, 6, 2)
            action_layout.setSpacing(6)
            check_btn = QPushButton("检查可用")
            check_btn.setObjectName("Ghost")
            check_btn.setFixedHeight(26)
            check_btn.clicked.connect(lambda _checked=False, r=row: self._check_available(r))
            action_layout.addWidget(check_btn)
            install_btn = QPushButton("安装")
            install_btn.setObjectName("Primary")
            install_btn.setFixedHeight(26)
            install_btn.clicked.connect(lambda _checked=False, r=row: self._install_offer(r))
            action_layout.addWidget(install_btn)
            action_layout.addStretch(1)
            self._check_buttons[row] = check_btn
            self._install_buttons[row] = install_btn
            table.setCellWidget(row, 4, actions)

    def refresh(self) -> None:
        """刷新各行状态：已安装 / 已解析 / 可直接安装 / 待检查。"""
        for row, offer in enumerate(self._offers):
            if row in self._busy_rows:
                continue
            status = self._status_items[row]
            installed = bool(find_java_in(JAVA_ROOT / f"jre-{offer.version}"))
            if installed:
                status.setText("已安装 ✓")
                status.setForeground(Qt.GlobalColor.green)
                self._install_buttons[row].setEnabled(True)
            elif row in self._resolved:
                status.setText("已解析，可安装")
                status.setForeground(Qt.GlobalColor.cyan)
                self._install_buttons[row].setEnabled(True)
            elif row in self._failed:
                status.setText("不可用")
                status.setForeground(Qt.GlobalColor.red)
                status.setToolTip(self._failed[row])
                self._install_buttons[row].setEnabled(False)
            elif offer.resolver == "adoptium":
                # Adoptium 走内置 API，无需预先解析
                status.setText("可直接安装")
                status.setForeground(Qt.GlobalColor.green)
                self._install_buttons[row].setEnabled(True)
            else:
                status.setText("待检查")
                status.setForeground(Qt.GlobalColor.gray)
                status.setToolTip("")
                self._install_buttons[row].setEnabled(False)

    def shutdown(self) -> None:
        """关闭页面：取消并等待仍在运行的解析 / 下载 worker。"""
        for worker in list(self._workers):
            cancel_event = getattr(worker, "cancel_event", None)
            if cancel_event is not None:
                try:
                    cancel_event.set()
                except Exception:  # noqa: BLE001
                    pass
            try:
                worker.requestInterruption()
            except Exception:  # noqa: BLE001
                pass
        for worker in list(self._workers):
            wait_thread(worker, 2000)
        self._workers.clear()

    # ------------------------------------------------------------------
    def _discard_worker(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def _check_available(self, row: int) -> None:
        if row in self._busy_rows:
            return
        offer = self._offers[row]
        self._busy_rows.add(row)
        self._check_buttons[row].setEnabled(False)
        status = self._status_items[row]
        status.setText("解析中…")
        status.setForeground(Qt.GlobalColor.yellow)
        status.setToolTip("")
        worker = ResolveWorker(offer, row, self)
        worker.done.connect(self._on_resolve_done)
        worker.failed.connect(self._on_resolve_failed)
        worker.finished.connect(lambda w=worker: self._discard_worker(w))
        self._workers.append(worker)
        worker.start()

    def _on_resolve_done(self, row: int, result: dict) -> None:
        self._busy_rows.discard(row)
        self._resolved[row] = result
        self._failed.pop(row, None)
        self._check_buttons[row].setEnabled(True)
        self._install_buttons[row].setEnabled(True)
        status = self._status_items[row]
        status.setText("已解析，可安装")
        status.setForeground(Qt.GlobalColor.cyan)
        status.setToolTip(result.get("name") or result.get("url") or "")
        self.ctx.bus.toast.emit(
            f"{self._offers[row].vendor} Java {self._offers[row].version}：已获取下载地址。"
        )

    def _on_resolve_failed(self, row: int, message: str) -> None:
        self._busy_rows.discard(row)
        self._failed[row] = message
        self._check_buttons[row].setEnabled(True)
        self._install_buttons[row].setEnabled(False)
        status = self._status_items[row]
        status.setText("不可用")
        status.setForeground(Qt.GlobalColor.red)
        status.setToolTip(message)
        self.ctx.bus.log.emit(
            f"[Java 中心] {self._offers[row].vendor} Java {self._offers[row].version} 解析失败：{message}"
        )

    def _install_offer(self, row: int) -> None:
        offer = self._offers[row]
        resolved = self._resolved.get(row) or {}
        url = str(resolved.get("url") or "")  # Adoptium 留空时由 download_java 自动解析
        cancel_event = threading.Event()
        pause_event = threading.Event()

        def factory(_task) -> QThread:
            worker = JavaCenterInstallWorker(
                offer.version, JAVA_ROOT, _task.id, cancel_event, pause_event, url, self
            )
            worker.progress.connect(
                lambda p, s, tid=_task.id: self.ctx.downloads.update(
                    tid, percent=p, speed=s
                )
            )
            worker.done.connect(lambda info, r=row: self._on_installed(r, info))
            worker.failed.connect(
                lambda msg, tid=_task.id, r=row: self._on_install_failed(r, tid, msg)
            )
            worker.finished.connect(lambda w=worker: self._discard_worker(w))
            self._workers.append(worker)
            return worker

        self.ctx.downloads.submit(
            kind="Java",
            name=f"{offer.vendor} Java {offer.version}",
            factory=factory,
            cancel=cancel_event.set,
            pause=pause_event,
            rebuild=factory,
            target_dir=str(JAVA_ROOT),
            detail=f"{offer.vendor} · Java {offer.version}",
        )
        self.ctx.bus.toast.emit(f"已加入下载中心：{offer.vendor} Java {offer.version}")

    def _on_installed(self, row: int, info) -> None:
        self.ctx.javas = detect_java_installed()
        if info is not None and all(j.path != info.path for j in self.ctx.javas):
            self.ctx.javas.append(info)
        self.ctx.bus.javas_changed.emit()
        self.ctx.bus.toast.emit(
            f"{self._offers[row].vendor} Java {getattr(info, 'version', '')} 已就绪。"
        )
        self.refresh()

    def _on_install_failed(self, row: int, task_id: str, message: str) -> None:
        self.ctx.downloads.finish(task_id, ok=False, message=message)
        self.ctx.bus.log.emit(
            f"[Java 中心] {self._offers[row].vendor} Java {self._offers[row].version} 安装失败：{message}"
        )
        QMessageBox.warning(self, "Java 安装失败", message)
