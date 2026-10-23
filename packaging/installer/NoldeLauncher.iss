; Inno Setup script for Nolde Launcher (Windows 10/11, 64-bit).
; Build with scripts\build_installer.ps1, or run ISCC on this file after PyInstaller has
; produced dist\NoldeLauncher. Requires Inno Setup 6: https://jrsoftware.org/isinfo.php
;
; Installs per user (no administrator rights) into %LOCALAPPDATA%\Programs.

#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif
#define MyAppName "Nolde Launcher"
#define MyAppExe "NoldeLauncher.exe"
#define MyAppPublisher "Nolde Launcher contributors"

[Setup]
AppId={{B6F1C2A4-7E0B-4C5D-9A61-2F3E8D9C1A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://nolde.pages.dev/
AppSupportURL=https://nolde.pages.dev/
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\installer
OutputBaseFilename=NoldeLauncher-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExe}
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\NoldeLauncher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Start {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// The uninstaller keeps the user's data by default. That data includes the library list,
// the settings, and the default game folder, so removing it is a separate, explicit choice.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\NoldeLauncher');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete your Nolde Launcher data?' + #13#10 + #13#10 +
                'This removes the library list, settings, cached artwork, and the default ' +
                'game folder under:' + #13#10 + DataDir + #13#10 + #13#10 +
                'Choose No to keep your installed games.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
