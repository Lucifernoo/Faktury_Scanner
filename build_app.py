#!/usr/bin/env python3
"""
Збірка: PyArmor + PyInstaller у режимі onedir (швидкий старт, без розпаковки в TEMP).
Запускати з кореня проєкту: python build_app.py
Після збірки створюється setup_script.iss для Inno Setup Compiler (iscc).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

# Відображувана назва (Inno, повідомлення)
APP_NAME_DISPLAY = "Faktury Scanner"
# Ім'я для PyInstaller / каталог dist — без пробілів (інакше PyArmor ламає makespec)
APP_NAME_SAFE = "FakturyScanner"


def _pyarmor_cli() -> list[str]:
    """PyArmor 8/9: консольний вхід — ``python -m pyarmor.cli``."""
    return [sys.executable, "-m", "pyarmor.cli"]


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
LOGO_ICO = ROOT / "logo.ico"
SETUP_ISS = ROOT / "setup_script.iss"


def _clean_build_artifacts() -> None:
    for path in (DIST, BUILD):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _validate_icon() -> None:
    if not LOGO_ICO.is_file():
        print(f"Помилка: потрібен файл іконки у корені проєкту: {LOGO_ICO}", file=sys.stderr)
        sys.exit(1)


def _write_inno_setup_script() -> None:
    """Генерує setup_script.iss для Inno Setup (іконка установника, ярлик на робочому столі)."""
    app_guid = str(uuid.uuid4()).upper()
    # Inno: AppId={{GUID}} — подвійні фігурні дужки навколо GUID
    lines = [
        "; Автоматично згенеровано build_app.py — збірка: iscc setup_script.iss",
        '#define MyAppName "' + APP_NAME_DISPLAY.replace('"', '""') + '"',
        '#define MyAppExeName "' + APP_NAME_SAFE + '.exe"',
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
        # Джерело: dist/Faktury Scanner/ (усі файли one-dir збірки)
        'Source: "dist\\' + APP_NAME_SAFE + '\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs',
        "",
        "[Icons]",
        r'Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"',
        r'Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"',
        "",
        "[Run]",
        r'Filename: "{app}\{#MyAppExeName}"; Flags: nowait postinstall skipifsilent',
        "",
    ]
    SETUP_ISS.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    os.chdir(ROOT)
    _clean_build_artifacts()
    _validate_icon()

    # PyInstaller: режим onedir задає ``gen --pack onedir``. ``--clean`` лише у pyinstaller build, не у makespec — прибираємо (каталоги dist/build чистимо на початку скрипта).
    pyi_options = (
        " --noconsole"
        f" --name={APP_NAME_SAFE}"
        " --icon=logo.ico"
        " --add-data web;web"
        " --add-data tesseract_bin;tesseract_bin"
    )
    cli = _pyarmor_cli()
    # Один аргумент «name=value» — інакше «;» у --add-data ламає парсер і PowerShell
    subprocess.run([*cli, "cfg", "pack:pyi_options=" + pyi_options], cwd=ROOT, check=True)
    subprocess.run([*cli, "gen", "--pack", "onedir", "main.py"], cwd=ROOT, check=True)

    _write_inno_setup_script()

    out_dir = ROOT / "dist" / APP_NAME_SAFE
    print(f"Готово. Програма: {out_dir}")
    print(f"Inno Setup: iscc {SETUP_ISS.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
