; Inno Setup script of the Minecraft Server Creator installer.
; Don't compile it directly: run `python installer/build_installer.py`, which
; prepares the private Python in build\installer\stage and passes AppVersion,
; StageDir and OutputDir to ISCC.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef StageDir
  #define StageDir "..\build\installer\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

#define AppName "Minecraft Server Creator"
#define AppUrl "https://github.com/ddavidel/minecraft-server-creator"
; Same AppUserModelID as mcsc_gui.core.shortcuts: the taskbar groups the
; window with its shortcut and pinning it relaunches the app.
#define AppUserModelId "mcsc.MinecraftServerCreator"

[Setup]
; Never change AppId: it's how a new installer recognises an older install.
AppId={{7F92D691-6470-4FC5-BEE3-FAA6B06D70D3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ddavidel
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
; Per-user install, no admin rights: the in-app updater runs pip on this
; Python, so its folder must stay writable by the user.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=mcsc-setup-{#AppVersion}
SetupIconFile=..\src\mcsc_gui\static\logo.ico
UninstallDisplayIcon={app}\mcsc.ico
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
; Close a running MCSC (its Python holds the Qt DLLs) before replacing files
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[CustomMessages]
en.AppComment=Create and manage Minecraft servers
it.AppComment=Crea e gestisci server Minecraft

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Start every install/upgrade from a clean Python: no leftovers from older
; versions or from packages the updater installed. User data (servers,
; settings, logs) lives in %LOCALAPPDATA%\mcsc and is never touched.
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#StageDir}\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\mcsc_gui\static\logo.ico"; DestDir: "{app}"; DestName: "mcsc.ico"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m mcsc_gui"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\mcsc.ico"; Comment: "{cm:AppComment}"; AppUserModelID: "{#AppUserModelId}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m mcsc_gui"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\mcsc.ico"; Comment: "{cm:AppComment}"; AppUserModelID: "{#AppUserModelId}"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m mcsc_gui"; WorkingDir: "{%USERPROFILE}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Files created after the install: bytecode caches, packages and launchers
; written by the in-app updater (pip).
Type: filesandordirs; Name: "{app}\python"
; The app can create the same desktop shortcut itself (Settings > Create
; desktop shortcut): without the app it would point to nothing.
Type: files; Name: "{autodesktop}\{#AppName}.lnk"
Type: dirifempty; Name: "{app}"
