# PyInstaller build specification for Attendance Manager.
# Build with:  pyinstaller packaging/attendance_manager.spec --noconfirm --clean
# (scripts/build.ps1 does this for you and then creates the installer.)
# ruff: noqa

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
PKG = SRC / "attendance_manager"

init = (PKG / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__ = "([^"]+)"', init).group(1)
APP_NAME = re.search(r'APP_NAME = "([^"]+)"', init).group(1)
parts = [int(p) for p in re.findall(r"\d+", VERSION)[:4]]
parts += [0] * (4 - len(parts))

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=tuple(parts), prodvers=tuple(parts)),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("CompanyName", APP_NAME),
                StringStruct("FileDescription", APP_NAME),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "AttendanceManager"),
                StringStruct("LegalCopyright", "Copyright (c) Attendance Manager"),
                StringStruct("OriginalFilename", "AttendanceManager.exe"),
                StringStruct("ProductName", APP_NAME),
                StringStruct("ProductVersion", VERSION),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

# Qt modules the app never uses — excluded to keep the install small.
EXCLUDES = [
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL", "IPython", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtBluetooth", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtNfc",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtHttpServer",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    datas=[
        (str(PKG / "ui" / "assets"), "attendance_manager/ui/assets"),
        (str(PKG / "locales"), "attendance_manager/locales"),
    ],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtCharts", "openpyxl", "xlrd"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AttendanceManager",
    icon=str(ROOT / "packaging" / "assets" / "app_icon.ico"),
    version=version_info,
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AttendanceManager",
)
