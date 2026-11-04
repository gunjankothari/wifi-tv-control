; Inno Setup script. The workflow passes /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
[Setup]
AppId={{6F1B2C84-5D0E-4C3A-9B7A-2E7D3C1A9F10}
AppName=TV Remote
AppVersion={#AppVersion}
DefaultDirName={autopf}\TV Remote
DefaultGroupName=TV Remote
OutputDir=..\dist
OutputBaseFilename=TVRemote-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\TVRemote.exe
[Files]
Source: "..\dist\TVRemote\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{group}\TV Remote"; Filename: "{app}\TVRemote.exe"
Name: "{autodesktop}\TV Remote"; Filename: "{app}\TVRemote.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
[Run]
Filename: "{app}\TVRemote.exe"; Description: "Start TV Remote"; Flags: nowait postinstall skipifsilent
