"""Build TallyCraft.exe and assemble the distributable folder.

    python build.py            # -> dist/TallyCraft/ and dist/TallyCraft-<version>-windows.zip

Requires the dev dependencies (pip install -r requirements-dev.txt).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_DIR = DIST / "TallyCraft"
ICON = ROOT / "assets" / "tallycraft.ico"


def version() -> str:
    text = (ROOT / "src" / "tallycraft" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def main() -> None:
    ver = version()
    if not ICON.exists():
        subprocess.check_call([sys.executable, str(ROOT / "tools" / "make_icon.py")])

    import PyInstaller.__main__

    sep = ";" if sys.platform == "win32" else ":"
    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "TallyCraft",
        "--icon", str(ICON),
        "--add-data", f"{ICON}{sep}assets",
        "--paths", str(ROOT / "src"),
        "--distpath", str(DIST / "_exe"),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        # ezdxf's optional front-ends are not needed and would bloat the exe
        "--exclude-module", "matplotlib",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide6",
        str(ROOT / "src" / "tallycraft" / "__main__.py"),
    ])

    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    (APP_DIR / "package_presets").mkdir(parents=True)
    (APP_DIR / "control_presets").mkdir()
    shutil.copy2(DIST / "_exe" / "TallyCraft.exe", APP_DIR / "TallyCraft.exe")
    shutil.copy2(ROOT / "dist_template" / "README.txt", APP_DIR / "README.txt")
    sys.path.insert(0, str(ROOT / "src"))
    from tallycraft.storage import DEFAULT_SETTINGS
    (APP_DIR / "settings.json").write_text(json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8")

    zip_path = DIST / f"TallyCraft-v{ver}-windows.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(APP_DIR.rglob("*")):
            arc = Path("TallyCraft") / path.relative_to(APP_DIR)
            if path.is_dir():
                zf.writestr(str(arc).replace("\\", "/") + "/", "")
            else:
                zf.write(path, arc)
    print(f"\nBuilt {APP_DIR}\nZipped {zip_path}")


if __name__ == "__main__":
    main()
