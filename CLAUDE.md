# TallyCraft — notes for Claude

Windows desktop app (Python + Tkinter/ttk) that computes shipping weights for
laser-cut plywood kits from DXF files using a weight-per-area control sample.

## Where things are
- **Design spec (source of truth):** `docs/SPEC.md` — read before changing behavior; update it when a design decision changes.
- **Progress log:** `docs/PROGRESS.md` — update at the end of every work session (done / next / open questions).
- Original prompt from the user: `docs/TallyCraftPrompt.md` (historical; SPEC.md supersedes it).
- Source: `src/tallycraft/` — keep DXF geometry, calculation, preset/settings I/O, and GUI in separate modules. The GUI must not contain geometry or math logic.
- Tests: `tests/` (pytest; DXF fixtures are generated in code with ezdxf, not committed binaries).
- Build: `build.py` (PyInstaller `--onefile` + assembles the `TallyCraft/` distribution folder). Release CI: `.github/workflows/release.yml` (on `v*` tag).

## Conventions
- All user-facing messages are plain, non-technical, and name the affected file/row. Never a silent wrong number; never an unhandled crash.
- Row status levels: `OK` < `Info` (never blocks) < `Warning` (Calculate asks once to confirm) < `Error` (blocks Calculate).
- Internal area unit for math is cm²; raw DXF coordinates are kept untouched so a Units change is a reinterpretation, not a conversion.
- No thickness anywhere (deliberately removed from the design).
- Dependencies stay minimal: `ezdxf`, `Pillow` (icon generation only), `pyinstaller` (build only), `pytest` (dev).
- Run tests: `python -m pytest -q`. Run app from source: `python -m tallycraft` with `src` on the path (see README).
- Git: branch `main`; remote `github.com/jaerxion/TallyCraft` (public). Commit only when asked; releases are cut by pushing a `vX.Y.Z` tag.
