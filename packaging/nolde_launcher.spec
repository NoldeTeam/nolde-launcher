# PyInstaller spec for Nolde Launcher (Windows 10/11, 64-bit).
# Build from the project root:  pyinstaller packaging/nolde_launcher.spec
# Not yet verified on Windows in this development environment.
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    datas=[
        (str(root / "nolde_launcher" / "localization" / "en.json"), "nolde_launcher/localization"),
        (str(root / "nolde_launcher" / "ui" / "assets" / "fonts"), "nolde_launcher/ui/assets/fonts"),
        (str(root / "nolde_launcher" / "ui" / "assets" / "images"), "nolde_launcher/ui/assets/images"),
    ],
    hiddenimports=[],
    excludes=["tkinter", "unittest", "pydoc"],  # keep the bundle small
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="NoldeLauncher",
    console=False,
    upx=False,
    icon=str(root / "nolde_launcher" / "ui" / "assets" / "images" / "nolde.ico"),
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="NoldeLauncher")
