#define MyAppName "NTA-AutoBot"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Re"
#define MyAppURL "https://github.com/Relieq/NTA-AutoBot"
#define MyAppExeName "NTA-AutoBot.exe"

[Setup]
AppId={{A9B1F6C6-6B2A-4A7B-9B42-9E1A6D8D2C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=NTA-AutoBot-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\NTA-AutoBot\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NTA-AutoBot"; Flags: nowait postinstall skipifsilent unchecked
