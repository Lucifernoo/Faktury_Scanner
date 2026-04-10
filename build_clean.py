#!/usr/bin/env python3
"""
Збірка без PyArmor: лише PyInstaller (onedir).
Запуск з кореня проєкту: python build_clean.py
Після збірки: installer_config.iss для Inno Setup (iscc installer_config.iss).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

APP_NAME = "FakturyScanner"
APP_NAME_DISPLAY = "Faktury Scanner"

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
LOGO_ICO = ROOT / "logo.ico"
INSTALLER_ISS = ROOT / "installer_config.iss"


def _clean_build_artifacts() -> None:
    for path in (DIST, BUILD):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _validate_icon() -> None:
    if not LOGO_ICO.is_file():
        print(f"Помилка: потрібен logo.ico у корені проєкту: {LOGO_ICO}", file=sys.stderr)
        sys.exit(1)


def _write_installer_config() -> None:
    """Генерує installer_config.iss для Inno Setup."""
    app_guid = str(uuid.uuid4()).upper()
    lines = [
        "; Автоматично згенеровано build_clean.py — збірка: iscc installer_config.iss",
        '#define MyAppName "' + APP_NAME_DISPLAY.replace('"', '""') + '"',
        '#define MyAppExeName "' + APP_NAME + '.exe"',
        "",
        "[Setup]",
        "AppId={{" + app_guid + "}}",
        "AppName={#MyAppName}",
        "AppVersion=1.0.0",
        "AppPublisher={#MyAppName}",
        r'DefaultDirName={autopf}\{#MyAppName}',
        "DefaultGroupName={#MyAppName}",
        "OutputDir=installer_output",
        "OutputBaseFilename=FakturyScannerSetup",
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
    subprocess.run(cmd, cwd=ROOT, check=True)

    _write_installer_config()

    out_dir = ROOT / "dist" / APP_NAME
    print(f"Готово (PyInstaller onedir): {out_dir}")
    print(f"Inno Setup: iscc {INSTALLER_ISS.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
