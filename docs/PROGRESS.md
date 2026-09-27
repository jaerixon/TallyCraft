# TallyCraft — Progress Log

Newest entries at the top. Each session records what was done, what's next, and
any open questions.

---

## 2026-09-27 — Session 1: setup + v0.1.0 implementation

**Decisions made with the user**
- Thickness is dropped completely. The user updated the original prompt to match.
- Warnings don't block Calculate. Calculate shows one confirmation dialog first. Errors do block it.
- Layers: geometry on layers that are off or frozen is skipped, as is geometry on any layer
  named in `settings.json` → `ignored_layer_names` (default CONSTRUCTION, DEFPOINTS). Skipped
  geometry gets an Info note.
- GitHub: `gh` installed via winget. The repo will be the public `jaerxion/TallyCraft`.

**Done**
- Repo skeleton: `.gitignore`, MIT `LICENSE`, root `README.md`, `docs/` (SPEC, PROGRESS,
  BUILDING, original prompt), `CLAUDE.md`.
- `dxf_geometry.py`: LINE/ARC/CIRCLE stitching, LWPOLYLINE/POLYLINE with bulges, INSERT
  expansion, mirrored-arc (OCS) handling, duplicate removal, errors for gaps and junctions with
  locations, unsupported-type errors, multiple-shape warning (even-odd area), sanity checks,
  file-level errors.
- `pieces.py` row model: unit override treated as a reinterpretation of the file's numbers,
  unknown units block Calculate, "modified since preset" warning.
- `calc.py`: cm²-normalized math, lb/oz conversion with carry, control validation.
- `storage.py`: package and control presets, settings, atomic writes, corrupt-file handling.
- `gui.py`: three-section Tkinter UI with in-cell Count/Units editing, status tooltips, a
  details pane, stale-results indicator, Copy Results, and a top-level error handler that
  writes `tallycraft_error.log`.
- Icon generator (`tools/make_icon.py`) and `assets/tallycraft.ico`/`.png`.
- `build.py`: PyInstaller onefile build that assembles `dist/TallyCraft/` and zips it.
  Hidden `--selftest` mode for verifying packaged exes.
- `.github/workflows/release.yml`: on a `v*` tag it runs tests, builds, self-tests the exe, and
  publishes the release with the zip attached.
- Verification: 50 pytest tests pass. A scripted GUI smoke test (import, fix errors, calculate,
  save/load presets, default preset on restart) passed and the numbers were checked by hand.
  The packaged exe self-test passed and the GUI launches from the exe.

**Next**
1. User runs `gh auth login`. Then create the public repo, push, and tag `v0.1.0` to trigger
   the first release.
2. Validate against one of the user's real DXF exports. The original prompt says the algorithm
   was prototyped against a real file; compare that file's area to the prototype's number.
3. Collect real-use feedback on the UI.

**Open questions**
- None pending.
