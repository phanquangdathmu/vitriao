# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec - đóng gói "Vị trí ảo iPhone" thành 1 file chạy (onefile).
Dùng chung cho Windows (ra .exe) và macOS (ra .app).

Build:
    pyinstaller build/vitriao.spec --noconfirm
"""
import sys
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
# pymobiledevice3 có rất nhiều import động + file dữ liệu -> gom hết
for pkg in ("pymobiledevice3", "webview", "cryptography"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

hiddenimports += ["plistlib", "winreg"] if sys.platform == "win32" else []

# Windows: kèm wintun.dll (driver tunnel cho iOS 17+). Workflow tải sẵn vào build/wintun.dll.
if sys.platform == "win32":
    import os
    _wt = os.path.join(SPECPATH, "wintun.dll")
    if os.path.exists(_wt):
        binaries += [(_wt, ".")]

block_cipher = None

a = Analysis(
    ["../app/vitriao.py"],
    pathex=["../app"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="VitriAo",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # không hiện cửa sổ đen
    disable_windowed_traceback=False,
    icon=None,              # thay đường dẫn .ico / .icns nếu có icon
)

# macOS: bọc thành .app để kéo thả
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Vị trí ảo iPhone.app",
        icon=None,
        bundle_identifier="vn.vitriao.app",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
