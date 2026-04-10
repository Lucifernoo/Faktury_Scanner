from __future__ import annotations

import json
import os
import re
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "my_edrpou_list": [],
    "my_names_list": [],
    "export_columns": [
        "Дата сканування",
        "Контрагент (Назва)",
        "ЄДРПОУ Контрагента",
        "IBAN",
        "Сума до сплати",
    ],
}


def _settings_path() -> str:
    """``%USERPROFILE%/Documents/FakturyScanner/settings.json`` (каталог створюється при збереженні / першому ``load``)."""
    home = os.path.expanduser("~")
    return os.path.join(home, "Documents", "FakturyScanner", "settings.json")


def _ensure_settings_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _normalize_text_line(s: str) -> str:
    """Прибирає зайві пробіли на краях і згортає послідовності пробілів у один."""
    return re.sub(r"\s+", " ", s.strip())


def parse_lines_from_settings_value(val: Any) -> list[str]:
    """Розбиває textarea / список на рядки; порожні рядки відкидаються."""
    if isinstance(val, list):
        out: list[str] = []
        for x in val:
            n = _normalize_text_line(str(x))
            if n:
                out.append(n)
        return out
    if isinstance(val, str):
        out = []
        for ln in val.replace("\r\n", "\n").split("\n"):
            n = _normalize_text_line(ln)
            if n:
                out.append(n)
        return out
    return []


def parse_export_columns_value(val: Any) -> list[str]:
    """Колонки Excel: список або текст (рядки / через кому); порожні елементи відкидаються."""
    if isinstance(val, list):
        out = [_normalize_text_line(str(x)) for x in val]
        out = [x for x in out if x]
        return out if out else list(DEFAULT_SETTINGS["export_columns"])
    if not isinstance(val, str):
        return list(DEFAULT_SETTINGS["export_columns"])
    out_cols: list[str] = []
    for line in val.replace("\r\n", "\n").split("\n"):
        line = _normalize_text_line(line)
        if not line:
            continue
        if "," in line or ";" in line:
            for p in re.split(r"[,;]+", line):
                n = _normalize_text_line(p)
                if n:
                    out_cols.append(n)
        else:
            out_cols.append(line)
    return out_cols if out_cols else list(DEFAULT_SETTINGS["export_columns"])


class ConfigManager:
    """Робота з ``settings.json`` у теці користувача ``Documents/FakturyScanner``."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or _settings_path()

    @property
    def path(self) -> str:
        return self._path

    def load(self) -> dict[str, Any]:
        """Повертає налаштування; якщо файлу немає — створює каталог і файл з порожніми списками ЄДРПОУ/назв."""
        if not os.path.isfile(self._path):
            _ensure_settings_parent_dir(self._path)
            self.save(dict(DEFAULT_SETTINGS))
            return dict(DEFAULT_SETTINGS)
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            _ensure_settings_parent_dir(self._path)
            self.save(dict(DEFAULT_SETTINGS))
            return dict(DEFAULT_SETTINGS)

        merged = dict(DEFAULT_SETTINGS)
        if not isinstance(data, dict):
            return merged

        merged.update(data)

        if isinstance(data.get("my_edrpou_list"), list):
            merged["my_edrpou_list"] = parse_lines_from_settings_value(data["my_edrpou_list"])
        else:
            old_e = data.get("my_company_edrpou", "")
            merged["my_edrpou_list"] = (
                parse_lines_from_settings_value([old_e]) if old_e else []
            )

        if isinstance(data.get("my_names_list"), list):
            merged["my_names_list"] = parse_lines_from_settings_value(data["my_names_list"])
        else:
            old_n = data.get("my_company_name", "")
            merged["my_names_list"] = (
                parse_lines_from_settings_value([old_n]) if old_n else []
            )

        if "export_columns" not in data or not isinstance(data.get("export_columns"), list):
            merged["export_columns"] = list(DEFAULT_SETTINGS["export_columns"])

        return merged

    def save(self, settings: dict[str, Any]) -> None:
        """Зберігає повний словник налаштувань у JSON."""
        out = dict(DEFAULT_SETTINGS)
        out.update(settings)

        if "my_edrpou_list" in settings:
            out["my_edrpou_list"] = parse_lines_from_settings_value(settings["my_edrpou_list"])
        if "my_names_list" in settings:
            out["my_names_list"] = parse_lines_from_settings_value(settings["my_names_list"])
        if "export_columns" in settings:
            out["export_columns"] = parse_export_columns_value(settings["export_columns"])

        for deprecated in ("my_company_edrpou", "my_company_name"):
            out.pop(deprecated, None)

        _ensure_settings_parent_dir(self._path)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
