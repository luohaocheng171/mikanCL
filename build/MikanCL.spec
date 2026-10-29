# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/admin/Documents/Trae-CN/temp_20261025_01/run.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/admin/Documents/Trae-CN/temp_20261025_01/mc_launcher/translations', 'mc_launcher/translations')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs', 'PySide6.QtOpenGLWidgets', 'PySide6.QtQuick3D', 'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtTest', 'PySide6.QtWebEngineQuick'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MikanCL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/admin/Documents/Trae-CN/temp_20261025_01/assets/mikan.ico'],
)
