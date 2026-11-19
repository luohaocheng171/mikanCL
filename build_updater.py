"""编译内置更新器（Go）：python build_updater.py

启动器自动更新要靠 `mc_launcher/resources/updater/mcu.exe`：
它负责等待启动器退出、备份旧 exe、换上新 exe、重启、清理临时目录并自毁。

这个脚本做三件事：
1. 找一个可用的 Go（环境变量 GOROOT / PATH / 项目内 .tools/go 便携版）；
2. 用离线方式编译 tools/updater（纯标准库，不需要 GOPROXY）；
3. 把产物放到 mc_launcher/resources/updater/mcu.exe。

没有 Go 时可以用 --download 让脚本自己拉一份便携版（默认走阿里云镜像，
国内网络友好；拉过一次后续都复用）。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / ".tools"
GO_DIR = TOOLS / "go"
UPDATER_SRC = ROOT / "tools" / "updater"
OUTPUT = ROOT / "mc_launcher" / "resources" / "updater" / "mcu.exe"
GO_VERSION = "1.23.4"
MIRRORS = (
    f"https://mirrors.aliyun.com/golang/go{GO_VERSION}.windows-amd64.zip",
    f"https://golang.google.cn/dl/go{GO_VERSION}.windows-amd64.zip",
    f"https://go.dev/dl/go{GO_VERSION}.windows-amd64.zip",
)


def find_go() -> Path | None:
    for candidate in (
        GO_DIR / "bin" / "go.exe",
        Path(os.environ.get("GOROOT", "")) / "bin" / "go.exe" if os.environ.get("GOROOT") else None,
    ):
        if candidate and candidate.is_file():
            return candidate
    found = shutil.which("go")
    return Path(found) if found else None


def download_go() -> Path:
    TOOLS.mkdir(parents=True, exist_ok=True)
    archive = TOOLS / f"go{GO_VERSION}.zip"
    last_error: Exception | None = None
    for url in MIRRORS:
        try:
            print(f"下载 Go {GO_VERSION}：{url}")
            with urllib.request.urlopen(url, timeout=120) as response, open(archive, "wb") as handle:
                shutil.copyfileobj(response, handle, 1024 * 256)
            print(f"已下载 {archive.stat().st_size / 1024 / 1024:.1f} MB")
            break
        except Exception as exc:  # noqa: BLE001 - 逐个镜像重试
            last_error = exc
            print(f"  失败：{exc}")
    else:
        raise SystemExit(f"下载 Go 失败：{last_error}")
    print("解压 Go…")
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(TOOLS)
    archive.unlink(missing_ok=True)
    go = GO_DIR / "bin" / "go.exe"
    if not go.is_file():
        raise SystemExit("解压后没找到 go.exe，请手动安装 Go 后重试")
    return go


def build(go: Path) -> int:
    env = dict(os.environ)
    env["GOROOT"] = str(GO_DIR) if (GO_DIR / "bin" / "go.exe") == go else env.get("GOROOT", "")
    env.setdefault("GOPATH", str(TOOLS / "gopath"))
    env["GOFLAGS"] = "-mod=mod"
    env["GOPROXY"] = "off"          # 纯标准库，禁掉联网拉模块
    env["GOTOOLCHAIN"] = "local"    # 不因为 go.mod 里的版本号去下工具链
    env.setdefault("TEMP", os.environ.get("TEMP", str(TOOLS / "tmp")))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(go), "build", "-trimpath",
        "-ldflags", "-s -w -H=windowsgui",
        "-o", str(OUTPUT),
        ".",
    ]
    print("执行：", " ".join(command))
    result = subprocess.call(command, cwd=UPDATER_SRC, env=env)
    if result != 0:
        print("编译失败。")
        return result
    size = OUTPUT.stat().st_size / 1024 / 1024
    print(f"更新器已生成：{OUTPUT}（{size:.1f} MB）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="编译 MikanCL 内置更新器 mcu.exe")
    parser.add_argument("--download", action="store_true", help="没有 Go 时自动下载便携版")
    args = parser.parse_args()

    go = find_go()
    if go is None:
        if not args.download:
            print("没找到 Go。可以：")
            print("  1) 安装 Go 后重试；或")
            print("  2) 运行 python build_updater.py --download 自动下载便携版（约 79 MB）")
            return 2
        go = download_go()
    print("使用 Go：", go)
    if sys.platform != "win32":
        print("提示：更新器是 Windows 程序，非 Windows 上只能交叉编译（编译产物不能在本机运行）。")
    return build(go)


if __name__ == "__main__":
    raise SystemExit(main())
