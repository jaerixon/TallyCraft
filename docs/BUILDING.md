# Building & releasing TallyCraft

## One-time setup

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
```

## Rebuild the .exe after making changes

```powershell
.venv\Scripts\python -m pytest          # make sure nothing broke
.venv\Scripts\python build.py
```

The build produces:

- `dist\TallyCraft\`: the complete app folder (exe, empty preset folders, default
  `settings.json`, `README.txt`), ready to copy anywhere
- `dist\TallyCraft-v<version>-windows.zip`: the same folder, zipped for sharing

`build.py` runs PyInstaller (`--onefile --windowed`, with the icon embedded) and
then assembles the folder. It regenerates the icon only if `assets\tallycraft.ico`
is missing. To change the icon, edit `tools\make_icon.py` and run it.

### Checking a built exe

The exe has a hidden self-test mode. It parses DXF files without opening a window
and writes a JSON report:

```powershell
dist\TallyCraft\TallyCraft.exe --selftest report.json path\to\piece.dxf
```

## Publishing a release (automatic)

1. Bump `__version__` in `src\tallycraft\__init__.py` (for example `0.2.0`) and commit.
2. Tag and push:
   ```powershell
   git tag v0.2.0
   git push origin main v0.2.0
   ```
3. GitHub Actions (`.github/workflows/release.yml`) then runs the tests, builds the exe
   on Windows, runs the self-test on the built exe, and creates a GitHub Release with
   `TallyCraft-v0.2.0-windows.zip` attached. The build fails if the tag and
   `__version__` don't match.

## Publishing a release (manual fallback)

Run `build.py`, then create a release by hand:

```powershell
gh release create v0.2.0 dist\TallyCraft-v0.2.0-windows.zip --title "TallyCraft v0.2.0" --notes "What changed…"
```
