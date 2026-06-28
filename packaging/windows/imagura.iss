; Inno Setup script for Imagura.
;
; Packages the PyInstaller one-dir output (dist\Imagura\) into a single
; setup.exe that installs Imagura to Program Files, creates Start Menu and
; (optional) desktop shortcuts, registers file associations for the image
; formats Imagura actually supports, and uninstalls cleanly.
;
; Build the installer with the Inno Setup command-line compiler (ISCC):
;
;     iscc packaging\windows\imagura.iss
;
; Override the version or source on the command line if needed:
;
;     iscc /DMyAppVersion=2.0.0 packaging\windows\imagura.iss
;
; Prerequisite: run the PyInstaller build first so dist\Imagura\Imagura.exe
; exists (see README.md). Inno Setup 6 or later required, tested with 7.0.1
; (https://jrsoftware.org).

#define MyAppName "Imagura"
#define MyAppPublisher "Barmagloth"
#define MyAppExeName "Imagura.exe"
#define MyAppId "{{B6E2A1F4-3C7D-4A92-9E1B-IMAGURA000001}}"

; Version: pass /DMyAppVersion=x.y.z on the ISCC command line to override.
; Keep the default in sync with pyproject.toml / version_info.txt.
#ifndef MyAppVersion
  #define MyAppVersion "2.1.0"
#endif

; ProgID used for all Imagura file associations.
#define MyAppProgId "Imagura.Image"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; One-dir app is 64-bit; install into the native Program Files on x64.
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
OutputDir=..\..\dist\installer
OutputBaseFilename=Imagura-{#MyAppVersion}-setup
SetupIconFile=imagura.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate"; Description: "Associate supported image files with {#MyAppName}"; GroupDescription: "File associations:"

[Files]
; Bundle the entire PyInstaller one-dir output. Build it first (see README).
Source: "..\..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; --- ProgID for Imagura images (one shared class for all extensions) ---
Root: HKA; Subkey: "Software\Classes\{#MyAppProgId}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppName} Image"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\{#MyAppProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

; --- Per-extension association to the ProgID ---
; Supported set confirmed from imagura/config.py (IMG_EXTS) + viewers registry
; (.webp via WebPViewer). .tga and .qoi are supported by the loader but rarely
; useful as shell defaults, so they are included for completeness.
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.gif\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.tga\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.qoi\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
