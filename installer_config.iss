; Автоматично згенеровано build_clean.py — спочатку збірка PyInstaller, потім: iscc installer_config.iss
; Inno лише пакує вміст dist\FakturyScanner\ — без свіжого PyInstaller буде старий exe.
#define MyAppName "Faktury Scanner PRO"
#define MyAppExeName "FakturyScanner.exe"
#define MyAppVersion "1.1.1"
#define MyAppInstallFolder "Faktury Scanner"

[Setup]
AppId={{C2FE7C9E-07F2-4B48-8BAE-25EA9DE449A0}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
VersionInfoVersion=1.1.1.0
DefaultDirName={autopf}\{#MyAppInstallFolder}
DefaultGroupName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=FakturyScannerSetup-{#MyAppVersion}
SetupIconFile=logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\FakturyScanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Flags: nowait postinstall skipifsilent
