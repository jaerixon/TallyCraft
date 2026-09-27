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
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "default_control_preset": None,
    "ignored_layer_names": ["CONSTRUCTION", "DEFPOINTS"],
    "last_import_dir": None,
}

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
        self.settings_path = self.root / SETTINGS_FILE

    def ensure_folders(self) -> None:
        self.package_dir.mkdir(parents=True, exist_ok=True)
        self.control_dir.mkdir(parents=True, exist_ok=True)

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
        clean = []
        for i, p in enumerate(pieces, 1):
            if not isinstance(p, dict) or not isinstance(p.get("path"), str):
                raise PresetError(f"Piece #{i} in {path.name} is missing its file path.")
            units = p.get("units") if p.get("units") in ("in", "mm", "unknown") else None
            try:
                count = max(1, int(p.get("count", 1)))
            except (TypeError, ValueError):
                count = 1
            mtime = p.get("mtime")
            clean.append({"path": p["path"], "units": units, "count": count,
                          "mtime": float(mtime) if isinstance(mtime, (int, float)) else None})
        return {"name": str(data.get("name") or path.stem), "pieces": clean}

    # ------------------------------------------------------------ control presets

    def list_controls(self) -> list[PresetEntry]:
        return self._list(self.control_dir, CONTROL_KIND)

    def control_path(self, name: str) -> Path:
        return self._path_for(self.control_dir, name)

    def save_control(self, name: str, length: str, width: str, unit: str, weight_g: str) -> Path:
        """Values are stored exactly as typed so no precision is lost."""
        path = self.control_path(name)
        _write_json(path, {
            "type": CONTROL_KIND, "version": 1, "name": name.strip(),
            "length": length.strip(), "width": width.strip(), "unit": unit,
            "weight_g": weight_g.strip(),
        })
        return path

    def load_control(self, name: str) -> dict:
        path = self._find(self.control_dir, CONTROL_KIND, name)
        data = self._read(path, CONTROL_KIND)
        unit = data.get("unit")
        if unit not in ("in", "mm"):
            raise PresetError(f"The control preset \"{name}\" has an invalid unit ({unit!r}).")
        return {"name": str(data.get("name") or path.stem),
                "length": _as_text(data.get("length")), "width": _as_text(data.get("width")),
                "unit": unit, "weight_g": _as_text(data.get("weight_g"))}


PACKAGE_KIND = "tallycraft.package"
CONTROL_KIND = "tallycraft.control"


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
