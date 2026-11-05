; Установщик PoE Craft Helper (Inno Setup 6). Ставится в профиль пользователя без прав администратора,
; потому что программа хранит настройки, данные модов и иконки рядом с exe.
#ifndef MyVer
  #define MyVer "0.0.0"
#endif

[Setup]
AppId={{5B1C9E7A-3F7D-4C1E-9A54-POECRAFTHELPER}
AppName=PoE Craft Helper
AppVersion={#MyVer}
AppPublisher=guforeks322-droid
AppPublisherURL=https://github.com/guforeks322-droid/PoECraftHelper
DefaultDirName={localappdata}\PoECraftHelper
DefaultGroupName=PoE Craft Helper
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=PoECraftHelper-Setup-v{#MyVer}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\PoECraftHelper.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "release\PoECraftHelper\*"; DestDir: "{app}"; Excludes: "goals\*"; Flags: recursesubdirs ignoreversion
; настройки и свои крафты пользователя не перезаписываем при обновлении
Source: "release\PoECraftHelper\goals\*"; DestDir: "{app}\goals"; Flags: onlyifdoesntexist recursesubdirs

[Icons]
Name: "{group}\PoE Craft Helper"; Filename: "{app}\PoECraftHelper.exe"
Name: "{group}\Как пользоваться"; Filename: "{app}\Как пользоваться.txt"
Name: "{group}\Удалить PoE Craft Helper"; Filename: "{uninstallexe}"
Name: "{userdesktop}\PoE Craft Helper"; Filename: "{app}\PoECraftHelper.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PoECraftHelper.exe"; Description: "{cm:LaunchProgram,PoE Craft Helper}"; Flags: nowait postinstall skipifsilent
