"""Preset and settings files (SPEC §3, §6). Plain JSON on disk, no database."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PACKAGE_DIR = "package_presets"
CONTROL_DIR = "control_presets"
ORDER_DIR = "order_presets"
PACKING_DIR = "packing_lists"
TEMPLATES_DIR = "templates"
TEMPLATE_NAME = "packing_list_template.docx"
DEFAULT_TEMPLATE_SETTING = f"{TEMPLATES_DIR}/{TEMPLATE_NAME}"
DEFAULT_NOTE = "Thank you for your order!"
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "default_control_preset": None,
    "ignored_layer_names": ["CONSTRUCTION", "DEFPOINTS"],
    "last_import_dir": None,
    "text_scale": 1.0,  # View > Larger/Smaller Text
    "calibration_mode": "reference",  # last-used section 2 method: "reference" | "control"
    "main_split": None,  # top/bottom divider position as a fraction of the window height
    "shop_name": "",  # packing list header
    "logo_path": None,  # optional PNG/JPG for the packing list header
    "default_note": DEFAULT_NOTE,  # pre-filled "Note to customer"
    "cut_colors": ["ACI 7", "RGB 0,0,0"],  # colors that mean "cut"; every other color is engrave-only
    "template_path": DEFAULT_TEMPLATE_SETTING,  # packing list Word template (relative to the TallyCraft folder)
    "pdf_engine": "auto",  # Make PDFs with: "auto" (LibreOffice if installed, else Word) / "word" / "libreoffice"
}
MAIN_SPLIT_MIN, MAIN_SPLIT_MAX = 0.15, 0.85
TEXT_SCALE_MIN, TEXT_SCALE_MAX = 0.8, 2.5

_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class PresetError(Exception):
    """A problem with a preset/settings file, phrased for the user."""


def app_root() -> Path:
    """Folder holding presets and settings: next to the exe when packaged,
    or the repo's `portable/` folder when run from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2] / "portable"


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip()).rstrip(" .")
    if not cleaned:
        raise PresetError("Please enter a name for the preset.")
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = "_" + cleaned
    return cleaned[:120]


@dataclass(frozen=True)
class PresetEntry:
    name: str
    path: Path


class Storage:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else app_root()
        self.package_dir = self.root / PACKAGE_DIR
        self.control_dir = self.root / CONTROL_DIR
        self.order_dir = self.root / ORDER_DIR
        self.packing_dir = self.root / PACKING_DIR
        self.templates_dir = self.root / TEMPLATES_DIR
        self.settings_path = self.root / SETTINGS_FILE

    def ensure_folders(self) -> None:
        self.package_dir.mkdir(parents=True, exist_ok=True)
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.order_dir.mkdir(parents=True, exist_ok=True)
        self.packing_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ settings

    def load_settings(self) -> tuple[dict, str | None]:
        """Returns (settings, warning). A damaged file is backed up and replaced
        with defaults rather than stopping the app."""
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        if not self.settings_path.exists():
            return settings, None
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except (OSError, ValueError) as exc:
            backup = self.settings_path.with_suffix(".json.bak")
            try:
                self.settings_path.replace(backup)
            except OSError:
                pass
            return settings, (f"settings.json couldn't be read ({exc}). It was saved as "
                              f"{backup.name} and default settings are being used.")
        settings.update(data)
        if not isinstance(settings.get("ignored_layer_names"), list):
            settings["ignored_layer_names"] = list(DEFAULT_SETTINGS["ignored_layer_names"])
        scale = settings.get("text_scale")
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or scale != scale:
            settings["text_scale"] = 1.0  # hand-edited to something unusable
        else:
            settings["text_scale"] = min(TEXT_SCALE_MAX, max(TEXT_SCALE_MIN, float(scale)))
        if settings.get("calibration_mode") not in ("reference", "control"):
            settings["calibration_mode"] = "reference"
        split = settings.get("main_split")
        if isinstance(split, bool) or not isinstance(split, (int, float)) or split != split:
            settings["main_split"] = None
        else:
            settings["main_split"] = min(MAIN_SPLIT_MAX, max(MAIN_SPLIT_MIN, float(split)))
        for key in ("shop_name", "default_note"):
            if not isinstance(settings.get(key), str):
                settings[key] = DEFAULT_SETTINGS[key]
        if not isinstance(settings.get("logo_path"), str) or not settings["logo_path"].strip():
            settings["logo_path"] = None
        if not isinstance(settings.get("template_path"), str) or not settings["template_path"].strip():
            settings["template_path"] = DEFAULT_TEMPLATE_SETTING
        if settings.get("pdf_engine") not in ("auto", "word", "libreoffice"):
            settings["pdf_engine"] = "auto"
        colors = settings.get("cut_colors")
        if not isinstance(colors, list) or not colors or not all(isinstance(c, str) for c in colors):
            settings["cut_colors"] = list(DEFAULT_SETTINGS["cut_colors"])
        return settings, None

    def save_settings(self, settings: dict) -> None:
        _write_json(self.settings_path, settings)

    # ------------------------------------------------------------ generic presets

    def _list(self, folder: Path, kind: str) -> list[PresetEntry]:
        entries = []
        if not folder.exists():
            return entries
        for f in sorted(folder.glob("*.json"), key=lambda p: p.stem.lower()):
            name = f.stem
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("type") == kind and data.get("name"):
                    name = str(data["name"])
            except (OSError, ValueError):
                pass  # still listed; loading it will report the problem
            entries.append(PresetEntry(name, f))
        return entries

    def _path_for(self, folder: Path, name: str) -> Path:
        return folder / f"{safe_filename(name)}.json"

    def _find(self, folder: Path, kind: str, name: str) -> Path:
        for e in self._list(folder, kind):
            if e.name == name:
                return e.path
        path = self._path_for(folder, name)
        if path.exists():
            return path
        raise PresetError(f"The preset \"{name}\" wasn't found in {folder.name}.")

    def _read(self, path: Path, kind: str) -> dict:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise PresetError(f"The preset file {Path(path).name} no longer exists.") from None
        except (OSError, ValueError) as exc:
            raise PresetError(f"The preset file {Path(path).name} is damaged or unreadable ({exc}).") from None
        if not isinstance(data, dict) or data.get("type") != kind:
            what = "package" if kind == PACKAGE_KIND else "control"
            raise PresetError(f"{Path(path).name} isn't a TallyCraft {what} preset.")
        return data

    # ------------------------------------------------------------ package presets

    def list_packages(self) -> list[PresetEntry]:
        return self._list(self.package_dir, PACKAGE_KIND)

    def package_path(self, name: str) -> Path:
        return self._path_for(self.package_dir, name)

    def save_package(self, name: str, pieces: list[dict]) -> Path:
        """pieces: [{"path", "units", "count", "mtime"}]"""
        path = self.package_path(name)
        _write_json(path, {
            "type": PACKAGE_KIND, "version": 1, "name": name.strip(),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "pieces": pieces,
        })
        return path

    def load_package(self, path_or_name) -> dict:
        path = Path(path_or_name) if isinstance(path_or_name, Path) else self._find(self.package_dir, PACKAGE_KIND, path_or_name)
        data = self._read(path, PACKAGE_KIND)
        pieces = data.get("pieces")
        if not isinstance(pieces, list):
            raise PresetError(f"{path.name} has no list of pieces.")
        return {"name": str(data.get("name") or path.stem), "pieces": _clean_pieces(pieces, path.name)}

    # ------------------------------------------------------------ control presets

    # ------------------------------------------------------------ order presets

    def list_orders(self) -> list[PresetEntry]:
        return self._list(self.order_dir, ORDER_KIND)

    def order_path(self, name: str) -> Path:
        return self._path_for(self.order_dir, name)

    def save_order(self, name: str, packages: list[dict]) -> Path:
        """packages: [{"name", "preset_name", "quantity", "unsaved_changes", "pieces": [...]}].
        Pieces are embedded (same format as a package preset) so unsaved edits are kept."""
        path = self.order_path(name)
        _write_json(path, {
            "type": ORDER_KIND, "version": 1, "name": name.strip(),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "packages": packages,
        })
        return path

    def load_order(self, path_or_name) -> dict:
        path = Path(path_or_name) if isinstance(path_or_name, Path) else self._find(self.order_dir, ORDER_KIND,
                                                                                    path_or_name)
        data = self._read(path, ORDER_KIND)
        packages = data.get("packages")
        if not isinstance(packages, list) or not packages:
            raise PresetError(f"{path.name} doesn't list any packages.")
        clean = []
        for i, pkg in enumerate(packages, 1):
            if not isinstance(pkg, dict) or not isinstance(pkg.get("pieces"), list):
                raise PresetError(f"Package #{i} in {path.name} is missing its list of pieces.")
            try:
                qty = max(1, int(pkg.get("quantity", 1)))
            except (TypeError, ValueError):
                qty = 1
            preset = pkg.get("preset_name")
            clean.append({"name": str(pkg.get("name") or preset or f"Package {i}"),
                          "preset_name": preset if isinstance(preset, str) and preset else None,
                          "quantity": qty,
                          "pieces": _clean_pieces(pkg["pieces"], f"package #{i} in {path.name}")})
        return {"name": str(data.get("name") or path.stem), "packages": clean}

    # ------------------------------------------------------------ packing lists

    def packing_paths(self, base_name: str) -> tuple[Path, Path]:
        """(json, pdf) paths for a new packing list, never overwriting an existing one:
        "<base>", then "<base> (2)", "<base> (3)", ... The .docx sits beside them
        (json_path.with_suffix(".docx"))."""
        base = safe_filename(base_name)
        n = 1
        while True:
            stem = base if n == 1 else f"{base} ({n})"
            paths = [self.packing_dir / f"{stem}{ext}" for ext in (".json", ".pdf", ".docx")]
            if not any(p.exists() for p in paths):
                return paths[0], paths[1]
            n += 1

    def reprint_paths(self, json_path: Path, when: str) -> tuple[Path, Path]:
        """(docx, pdf) for a re-print, beside the record, never replacing the original:
        "<stem> (reprint 2026-09-28 1015)", with " 2", " 3", ... if needed."""
        base = f"{Path(json_path).stem} (reprint {when})"
        n = 1
        while True:
            stem = base if n == 1 else f"{base[:-1]} {n})"
            docx, pdf = self.packing_dir / f"{stem}.docx", self.packing_dir / f"{stem}.pdf"
            if not docx.exists() and not pdf.exists():
                return docx, pdf
            n += 1

    # ------------------------------------------------------------ templates

    def template_path(self, settings: dict) -> Path:
        """The packing list template chosen in Settings (relative paths are inside this folder)."""
        chosen = Path(settings.get("template_path") or DEFAULT_TEMPLATE_SETTING)
        return chosen if chosen.is_absolute() else self.root / chosen

    def ensure_templates(self, bundled: Path) -> None:
        """Keep templates/_default/ (the app's pristine copy) current, and create the
        user's template from it only if it's missing. Never replaces the user's file."""
        default_dir = self.templates_dir / "_default"
        default_dir.mkdir(parents=True, exist_ok=True)
        pristine = default_dir / TEMPLATE_NAME
        data = Path(bundled).read_bytes()
        if not pristine.exists() or pristine.read_bytes() != data:
            tmp = pristine.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, pristine)
        user = self.templates_dir / TEMPLATE_NAME
        if not user.exists():
            user.write_bytes(data)

    def restore_default_template(self) -> Path:
        """A fresh copy of the default template under a new name (never overwrites)."""
        pristine = self.templates_dir / "_default" / TEMPLATE_NAME
        if not pristine.exists():
            raise PresetError("The default template is missing from templates/_default/. Restart TallyCraft to "
                              "restore it.")
        base = self.templates_dir / "packing_list_template (default copy)"
        n = 1
        while True:
            target = Path(f"{base}.docx") if n == 1 else Path(f"{base} {n}.docx")
            if not target.exists():
                target.write_bytes(pristine.read_bytes())
                return target
            n += 1

    def save_packing_record(self, json_path: Path, record: dict) -> None:
        _write_json(json_path, record)

    def list_packing_lists(self) -> list[PresetEntry]:
        """Newest first (names start with the order date)."""
        if not self.packing_dir.exists():
            return []
        files = sorted(self.packing_dir.glob("*.json"), key=lambda p: p.stem.lower(), reverse=True)
        return [PresetEntry(f.stem, f) for f in files]

    def load_packing_record(self, path: Path) -> dict:
        from .packing import RecordError, validate_record
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise PresetError(f"The packing list {Path(path).name} no longer exists.") from None
        except (OSError, ValueError) as exc:
            raise PresetError(f"The packing list {Path(path).name} is damaged or unreadable ({exc}).") from None
        try:
            return validate_record(data)
        except RecordError as exc:
            raise PresetError(f"{Path(path).name}: {exc}") from None

    def list_controls(self) -> list[PresetEntry]:
        return self._list(self.control_dir, CONTROL_KIND)

    def control_path(self, name: str) -> Path:
        return self._path_for(self.control_dir, name)

    def save_control(self, name: str, length: str, width: str, unit: str, weight_g: str) -> Path:
        """Control-sample calibration. Values are stored exactly as typed so no precision is lost."""
        path = self.control_path(name)
        _write_json(path, {
            "type": CONTROL_KIND, "version": 1, "name": name.strip(), "method": "control",
            "length": length.strip(), "width": width.strip(), "unit": unit,
            "weight_g": weight_g.strip(),
        })
        return path

    def save_reference(self, name: str, ref_path: str, ref_name: str, quantity: str, weight_g: str,
                       grams_per_cm2: float, area_cm2: float) -> Path:
        """Reference-piece calibration. The derived g/cm² and the piece's net area are
        stored too, so the preset still works in a package that doesn't contain the file."""
        path = self.control_path(name)
        _write_json(path, {
            "type": CONTROL_KIND, "version": 1, "name": name.strip(), "method": "reference",
            "reference_path": ref_path, "reference_name": ref_name,
            "quantity": quantity.strip(), "weight_g": weight_g.strip(),
            "grams_per_cm2": grams_per_cm2, "reference_area_cm2": area_cm2,
        })
        return path

    def load_control(self, name: str) -> dict:
        """Returns a dict with "method": "control" (length/width/unit/weight_g) or
        "reference" (reference_path/name, quantity, weight_g, grams_per_cm2, area_cm2).
        Presets saved before methods existed have no "method" key and load as control."""
        path = self._find(self.control_dir, CONTROL_KIND, name)
        data = self._read(path, CONTROL_KIND)
        shown = str(data.get("name") or path.stem)
        method = data.get("method", "control")
        if method == "reference":
            ref_path = data.get("reference_path")
            if not isinstance(ref_path, str) or not ref_path:
                raise PresetError(f"The preset \"{name}\" doesn't say which reference piece was weighed.")
            gpc = data.get("grams_per_cm2")
            if isinstance(gpc, bool) or not isinstance(gpc, (int, float)) or not gpc > 0:
                raise PresetError(f"The preset \"{name}\" has no usable saved g/cm² ratio.")
            area = data.get("reference_area_cm2")
            if isinstance(area, bool) or not isinstance(area, (int, float)) or not area > 0:
                area = None
            return {"method": "reference", "name": shown, "reference_path": ref_path,
                    "reference_name": str(data.get("reference_name") or Path(ref_path).name),
                    "quantity": _as_text(data.get("quantity")), "weight_g": _as_text(data.get("weight_g")),
                    "grams_per_cm2": float(gpc), "area_cm2": float(area) if area else None}
        if method != "control":
            raise PresetError(f"The preset \"{name}\" uses an unknown calibration method ({method!r}).")
        unit = data.get("unit")
        if unit not in ("in", "mm"):
            raise PresetError(f"The control preset \"{name}\" has an invalid unit ({unit!r}).")
        return {"method": "control", "name": shown,
                "length": _as_text(data.get("length")), "width": _as_text(data.get("width")),
                "unit": unit, "weight_g": _as_text(data.get("weight_g"))}


ORDER_KIND = "tallycraft.order"
PACKAGE_KIND = "tallycraft.package"
CONTROL_KIND = "tallycraft.control"


def _clean_pieces(pieces: list, where: str) -> list[dict]:
    """Validate a package-preset style "pieces" list (shared by package and order files)."""
    clean = []
    for i, p in enumerate(pieces, 1):
        if not isinstance(p, dict) or not isinstance(p.get("path"), str):
            raise PresetError(f"Piece #{i} in {where} is missing its file path.")
        units = p.get("units") if p.get("units") in ("in", "mm", "unknown") else None
        try:
            count = max(1, int(p.get("count", 1)))
        except (TypeError, ValueError):
            count = 1
        mtime = p.get("mtime")
        clean.append({"path": p["path"], "units": units, "count": count,
                      "mtime": float(mtime) if isinstance(mtime, (int, float)) and not isinstance(mtime, bool)
                      else None})
    return clean


def _as_text(v) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else repr(v)


def _write_json(path: Path, data: dict) -> None:
    """Write atomically so a crash mid-save never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise PresetError(f"Couldn't save {path.name} ({exc.strerror or exc}).") from None
