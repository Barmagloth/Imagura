; Imagura - Inno Setup Installer Script
; Compile with Inno Setup 6.x: https://jrsoftware.org/isinfo.php
;
; Prerequisites:
;   1. Build the app first: python build.py
;   2. Then compile this script with Inno Setup Compiler

#define MyAppName "Imagura"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Barmagloth"
#define MyAppURL "https://github.com/Barmagloth/Imagura"
#define MyAppExeName "Imagura.exe"

[Setup]
AppId={{B8A3F1D2-7E4C-4A9B-8F6D-1C2E3A4B5D6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output settings
OutputDir=..\dist
OutputBaseFilename=Imagura_Setup_{#MyAppVersion}
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; UI
WizardStyle=modern
; Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Icon (if available)
; SetupIconFile=imagura.ico
; Uninstaller
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Misc
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "Ассоциировать с файлами изображений (.png, .jpg, .bmp, .gif, .tga, .qoi)"; GroupDescription: "Ассоциации файлов:"

[Files]
; Main application files from PyInstaller output
Source: "..\dist\Imagura\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; File associations (when task selected)
; .png
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: string; ValueName: "Imagura.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; .jpg
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: string; ValueName: "Imagura.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; .jpeg
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "Imagura.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; .bmp
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: string; ValueName: "Imagura.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; .gif
Root: HKA; Subkey: "Software\Classes\.gif\OpenWithProgids"; ValueType: string; ValueName: "Imagura.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; .tga
Root: HKA; Subkey: "Software\Classes\.tga\OpenWithProgids"; ValueType: string; ValueName: "Imagura.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; .qoi
Root: HKA; Subkey: "Software\Classes\.qoi\OpenWithProgids"; ValueType: string; ValueName: "Imagura.Image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc

; ProgId registration
Root: HKA; Subkey: "Software\Classes\Imagura.Image"; ValueType: string; ValueName: ""; ValueData: "Imagura Image"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Imagura.Image\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Imagura.Image\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc

; App Paths registration (allows running "imagura" from Run dialog)
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up user config on uninstall (optional — commented out to preserve settings)
; Type: filesandordirs; Name: "{userappdata}\Imagura"

[Code]
// Notify shell of file association changes
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Notify Windows of file association changes
    // SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0)
    RegWriteStringValue(HKEY_CURRENT_USER, 'Software\Classes\Imagura.Image\shell\open\command',
      '', '"' + ExpandConstant('{app}\{#MyAppExeName}') + '" "%1"');
  end;
end;
