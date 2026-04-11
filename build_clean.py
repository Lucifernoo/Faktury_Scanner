#!/usr/bin/env python3
"""
Збірка без PyArmor: лише PyInstaller (onedir).
Запуск з кореня проєкту: python build_clean.py
Після збірки: installer_config.iss для Inno Setup (iscc installer_config.iss).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "FakturyScanner"
APP_DISPLAY_NAME = "Faktury Scanner PRO"
INSTALL_FOLDER = "Faktury Scanner"
# Стабільний AppId — не змінюйте між випусками, інакше Windows бачитиме інший продукт
INNO_APP_ID = "C2FE7C9E-07F2-4B48-8BAE-25EA9DE449A0"

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
LOGO_ICO = ROOT / "logo.ico"
INSTALLER_ISS = ROOT / "installer_config.iss"
MAIN_PY = ROOT / "main.py"


def _read_app_version_from_main() -> str:
    """Бере ``APP_VERSION`` з ``main.py`` без імпорту (немає побічних ефектів Eel)."""
    text = MAIN_PY.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION:\s*Final\[str\]\s*=\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    return "1.1.1"


def _version_info_four_parts(version: str) -> str:
    """Inno ``VersionInfoVersion``: чотири числові сегменти (наприклад 1.1.1 → 1.1.1.0)."""
    parts = [p for p in version.split(".") if p.isdigit()]
    if not parts:
        return "1.0.0.0"
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts[:4])


def _clean_build_artifacts() -> None:
    for path in (DIST, BUILD):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _validate_icon() -> None:
    if not LOGO_ICO.is_file():
        print(f"Помилка: потрібен logo.ico у корені проєкту: {LOGO_ICO}", file=sys.stderr)
        sys.exit(1)


def _write_installer_config(app_version: str) -> None:
    """Генерує installer_config.iss (узгоджено з main.APP_VERSION)."""
    ver_info = _version_info_four_parts(app_version)
    lines = [
        "; Автоматично згенеровано build_clean.py — спочатку збірка PyInstaller, потім: iscc installer_config.iss",
        "; Inno лише пакує вміст dist\\FakturyScanner\\ — без свіжого PyInstaller буде старий exe.",
        '#define MyAppName "' + APP_DISPLAY_NAME.replace('"', '""') + '"',
        f'#define MyAppExeName "{APP_NAME}.exe"',
        f'#define MyAppVersion "{app_version}"',
        f'#define MyAppInstallFolder "{INSTALL_FOLDER}"',
        "",
        "[Setup]",
        "AppId={{" + INNO_APP_ID + "}}",
        "AppName={#MyAppName}",
        "AppVersion={#MyAppVersion}",
        "AppVerName={#MyAppName} {#MyAppVersion}",
        "AppPublisher={#MyAppName}",
        f"VersionInfoVersion={ver_info}",
        r"DefaultDirName={autopf}\{#MyAppInstallFolder}",
        "DefaultGroupName={#MyAppName}",
        "OutputDir=installer_output",
        "OutputBaseFilename=FakturyScannerSetup-{#MyAppVersion}",
        "SetupIconFile=logo.ico",
        "Compression=lzma2",
        "SolidCompression=yes",
        "WizardStyle=modern",
        "PrivilegesRequired=admin",
        "ArchitecturesInstallIn64BitMode=x64",
        "",
        "[Languages]",
        'Name: "english"; MessagesFile: "compiler:Default.isl"',
        "",
        "[Files]",
        'Source: "dist\\' + APP_NAME + '\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs',
        "",
        "[Icons]",
        r'Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"',
        r'Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"',
        "",
        "[Run]",
        r'Filename: "{app}\{#MyAppExeName}"; Flags: nowait postinstall skipifsilent',
        "",
    ]
    INSTALLER_ISS.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    os.chdir(ROOT)
    app_version = _read_app_version_from_main()

    _clean_build_artifacts()
    _validate_icon()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--name",
        APP_NAME,
        "--noconsole",
        "--icon=logo.ico",
        "--clean",
        "--add-data",
        "web;web",
        "--add-data",
        "tesseract_bin;tesseract_bin",
        "main.py",
    ]
    subprocess.run(cmd, cwd=str(ROOT), check=True)

    _write_installer_config(app_version)

    out_dir = ROOT / "dist" / APP_NAME
    print(f"Готово (PyInstaller onedir): {out_dir}")
    print(f"Версія для Inno: {app_version}")
    print(f"Inno Setup: iscc {INSTALLER_ISS.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
