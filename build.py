"""Build TallyCraft.exe and assemble the distributable folder.

    python build.py            # -> dist/TallyCraft/ and dist/TallyCraft-<version>-windows.zip
    python build.py --exe-only # -> just dist/_exe/TallyCraft.exe (dist/TallyCraft/ is left alone)

Requires the dev dependencies (pip install -r requirements-dev.txt).

dist/TallyCraft/ is rebuilt from scratch each time. Before deleting anything,
the build checks that the old exe isn't running and that the folder holds no
presets, orders, or settings someone saved there, and stops with an
explanation if it does. Keep real data in a copy of the folder elsewhere.
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
TEMPLATE = ROOT / "assets" / "templates" / "packing_list_template.docx"
DATA_DIRS = ("package_presets", "control_presets", "order_presets", "packing_lists")

sys.path.insert(0, str(ROOT / "src"))
from tallycraft.storage import DEFAULT_SETTINGS, TEMPLATE_NAME  # noqa: E402


def version() -> str:
    text = (ROOT / "src" / "tallycraft" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def _files_user_owns() -> list[Path]:
    """Files in dist/TallyCraft that the build didn't produce, or that were changed
    since: presets, orders, packing lists, changed settings, an edited template,
    anything dropped into the folder (e.g. a DXF). Deleting those would lose work."""
    owned = []
    template = APP_DIR / "templates" / TEMPLATE_NAME
    pristine = APP_DIR / "templates" / "_default" / TEMPLATE_NAME
    readme = ROOT / "dist_template" / "README.txt"
    for path in sorted(APP_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(APP_DIR).as_posix()
        if rel == "TallyCraft.exe" or rel == f"templates/_default/{TEMPLATE_NAME}":
            continue  # the build's own files; always replaced
        if rel == "README.txt":
            continue  # replaced by the current README (nobody edits it)
        if rel == "settings.json":
            try:
                if json.loads(path.read_text(encoding="utf-8")) == DEFAULT_SETTINGS:
                    continue
            except (OSError, ValueError):
                pass
        elif rel == f"templates/{TEMPLATE_NAME}":
            if pristine.exists() and path.read_bytes() == pristine.read_bytes():
                continue  # untouched copy of the default
        owned.append(path)
    del template, readme
    return owned


def check_safe_to_replace() -> None:
    """Refuse to wipe dist/TallyCraft if it's in use or holds anything the user made."""
    if not APP_DIR.exists():
        return
    exe = APP_DIR / "TallyCraft.exe"
    if exe.exists():
        try:
            open(exe, "r+b").close()  # a running exe is locked for writing on Windows
        except PermissionError:
            sys.exit(f"TallyCraft is running from {APP_DIR}. Close it, then run build.py again "
                     "(nothing was changed).")
    owned = _files_user_owns()
    if owned:
        listing = "\n".join(f"  {p.relative_to(APP_DIR)}" for p in owned[:15])
        more = f"\n  ...and {len(owned) - 15} more" if len(owned) > 15 else ""
        sys.exit(f"{APP_DIR} contains files the build didn't create (or that were changed):\n{listing}{more}\n\n"
                 "The build would delete them. Move that folder somewhere else (or copy these files out), "
                 "then run build.py again. Use `python build.py --exe-only` to build just the exe. "
                 "Nothing was changed.")


def main() -> None:
    ver = version()
    exe_only = "--exe-only" in sys.argv[1:]
    if not exe_only:
        check_safe_to_replace()
    if not ICON.exists():
        subprocess.check_call([sys.executable, str(ROOT / "tools" / "make_icon.py")])

    import PyInstaller.__main__

    sep = ";" if sys.platform == "win32" else ":"
    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "TallyCraft",
        "--icon", str(ICON),
        "--add-data", f"{ICON}{sep}assets",
        "--add-data", f"{TEMPLATE}{sep}assets/templates",
        "--paths", str(ROOT / "src"),
        "--hidden-import", "win32crypt",  # Etsy connection file encryption (imported lazily)
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

    if exe_only:
        print(f"\nBuilt {DIST / '_exe' / 'TallyCraft.exe'} (dist/TallyCraft/ not touched)")
        return
    check_safe_to_replace()  # again: something may have been started or saved during the build
    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    for d in DATA_DIRS:
        (APP_DIR / d).mkdir(parents=True)
    shutil.copy2(DIST / "_exe" / "TallyCraft.exe", APP_DIR / "TallyCraft.exe")
    shutil.copy2(ROOT / "dist_template" / "README.txt", APP_DIR / "README.txt")
    (APP_DIR / "settings.json").write_text(json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8")
    (APP_DIR / "templates" / "_default").mkdir(parents=True)
    shutil.copy2(TEMPLATE, APP_DIR / "templates" / "_default" / TEMPLATE_NAME)
    shutil.copy2(TEMPLATE, APP_DIR / "templates" / TEMPLATE_NAME)

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
