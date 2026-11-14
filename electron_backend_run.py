"""Electron 独立内核的后端入口（供 PyInstaller 打包成 MikanCL-backend.exe）。"""

from mc_launcher.ui_web.electron_backend import main

if __name__ == "__main__":
    raise SystemExit(main())
