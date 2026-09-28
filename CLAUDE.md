# TallyCraft — notes for Claude

Windows desktop app (Python + Tkinter/ttk) that computes shipping weights for
laser-cut plywood kits from DXF files using a weight-per-area control sample.

## Where things are
- **Design spec (source of truth):** `docs/SPEC.md` — read before changing behavior; update it when a design decision changes.
- **Progress log:** `docs/PROGRESS.md` — update at the end of every work session (done / next / open questions).
- Original prompt from the user: `docs/TallyCraftPrompt.md` (historical; SPEC.md supersedes it).
- Source: `src/tallycraft/` — keep DXF geometry, calculation, preset/settings I/O, and GUI in separate modules. The GUI must not contain geometry or math logic. Orders/packages and the merge live in `order.py`, calibration in `calibration.py`, display sorting in `table_sort.py` (all pure, unit-tested).
- Tests: `tests/` (pytest; DXF fixtures are generated in code with ezdxf, not committed binaries). The user's real LightBurn sample lives in the git-ignored `tests/fixtures_private/` (the repo is public — never commit the user's designs).
- Build: `build.py` (PyInstaller `--onefile` + assembles the `TallyCraft/` distribution folder). Release CI: `.github/workflows/release.yml` (on `v*` tag).

## Conventions
- All user-facing messages are plain, non-technical, and name the affected file/row. Never a silent wrong number; never an unhandled crash.
- Row status levels: `OK` < `Info` (never blocks) < `Warning` (Calculate asks once to confirm) < `Error` (blocks Calculate).
- Internal area unit for math is cm²; raw DXF coordinates are kept untouched so a Units change is a reinterpretation, not a conversion.
- No thickness anywhere (deliberately removed from the design).
- Dependencies stay minimal: `ezdxf`, `docxtpl` (packing-list Word templates), `Pillow` (pictures, icon), `pywin32` (Word conversion), `pyinstaller` (build only), `pytest` + `pytest-rerunfailures` + `pyflakes` (dev; the rerun plugin is used only for the Tk startup flake in the GUI tests).
- Run tests: during development use the fast non-GUI tests, `python -m pytest -q -m "not gui"`. Run the full suite (`python -m pytest -q`) once before reporting a step as done. Run app from source: `python -m tallycraft` with `src` on the path (see README).
- Git: branch `main`; remote `github.com/jaerixon/TallyCraft` (public). Commit only when asked; releases are cut by pushing a `vX.Y.Z` tag.

## Hard rules (from the user)
- **Testing must never pop up windows or take keyboard/mouse focus on the user's desktop** (it's their work computer while tests run).
  - `tests/conftest.py` (`no_windows_on_screen`, autouse) keeps every Tk window withdrawn and makes show/raise/force-focus/grab no-ops. It also makes unanswered Tk dialogs and simpledialogs fail, never display, and blocks opening a browser or `os.startfile`. The GUI app fixture fails a test if any window was mapped.
  - Never add `deiconify`, `focus_force`, `lift`, or on-screen geometry to tests. Answer every messagebox/file dialog with a monkeypatch. Drive key bindings with `fire_binding` (runs the widget's own binding script), not real key events.
  - Self-tests, sample renders, and checks must not open visible windows or documents: no screenshots of live windows, no opening PDFs/DOCX in a viewer. Word runs hidden (`Visible = False`), LibreOffice headless.
- **Never change Windows or system settings** (default printer, registry, environment variables, etc.) without asking the user first.
- **Stop and report** with options if something fails the same way three times, or a single problem takes more than about 10 minutes — don't keep trying.
- **Tests must not launch Microsoft Word** (or LibreOffice). Mock the conversion everywhere, except the single opt-in test the user runs manually (`TALLYCRAFT_REAL_CONVERSION=1`).
- **Before finishing**, check for leftover background Word (`WINWORD.EXE /Automation`) or LibreOffice (`soffice`) processes that *you* started, and close only those.
- **Never move, modify, or delete anything in `D:\TallyCraft - Personal Use\`** (the user's personal TallyCraft data). Reading/copying a file out of it when asked is fine.
- `dist\TallyCraft\` is rebuilt by `build.py`, which refuses to delete anything it didn't create; don't work around that.
- **Etsy keys and tokens:** the user types them into the app. Never put them in the repo, tests, logs, or error messages (tests use made-up keys; `etsy_connection.json` is git-ignored). Tests never call Etsy — fake the transport — except the single opt-in live test the user runs (`TALLYCRAFT_ETSY_LIVE=1`). Etsy access stays **read-only** (`transactions_r shops_r`) unless the user asks otherwise.
