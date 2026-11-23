Unicode true
!ifdef SETUP_AMD64
Target amd64-unicode
!endif
!include "MUI2.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"

Name "Work Space ${VERSION}"
OutFile "${SETUP_FILE}"
InstallDir "$LOCALAPPDATA\Programs\WorkSpace"
InstallDirRegKey HKCU "Software\WorkSpace" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 16
ShowInstDetails show

Var AutoRestart
Var InstallMutex

!define MUI_ICON "..\assets\workspace.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\WorkSpace.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipUpdatePage
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipUpdatePage
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Windows 64비트에서 설치할 수 있습니다."
    Abort
  ${EndIf}
  SetRegView 64
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\WorkSpaceInstalling") p.r1 ?e'
  Pop $2
  StrCmp $1 0 blocked
  StrCmp $2 183 blocked

  StrCpy $InstallMutex $1
  ${GetParameters} $0
  ${GetOptions} $0 "/AUTORESTART=" $AutoRestart
  ClearErrors
  ${GetOptions} $0 "/WAITPID=" $0
  IfErrors check_running
  System::Call 'kernel32::OpenProcess(i 0x100000, i 0, i r0) p.r1'
  StrCmp $1 0 check_running
  System::Call 'kernel32::WaitForSingleObject(p r1, i 60000) i.r2'
  System::Call 'kernel32::CloseHandle(p r1)'
  StrCmp $2 0 check_running blocked

  check_running:
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\WorkSpaceRunning") p.r0'
  StrCmp $0 0 done
  System::Call 'kernel32::CloseHandle(p r0)'
  blocked:
  SetErrorLevel 1
  IfSilent +2
  MessageBox MB_ICONSTOP "Work Space를 종료한 뒤 설치해 주세요."
  Abort
  done:
FunctionEnd

Function SkipUpdatePage
  StrCmp $AutoRestart "1" 0 +2
  Abort
FunctionEnd

Function .onInstSuccess
  StrCmp $AutoRestart "1" 0 done
  System::Call 'kernel32::CloseHandle(p $InstallMutex)'
  ClearErrors
  Exec '"$INSTDIR\WorkSpace.exe"'
  IfErrors 0 done
  SetErrorLevel 1
  MessageBox MB_ICONEXCLAMATION "설치는 완료됐습니다. 바탕화면에서 Work Space를 다시 실행해 주세요."
  done:
FunctionEnd

Section "Work Space"
  StrCmp $AutoRestart "1" 0 +2
  SetAutoClose true
  SetRegView 64
  SetShellVarContext current
  SetOutPath "$INSTDIR\versions\${VERSION}"
  File /r "${PAYLOAD}\versions\${VERSION}\*"
  SetOutPath "$INSTDIR"
  File "${PAYLOAD}\WorkSpace.exe"
  File "${PAYLOAD}\current.json"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Work Space"
  CreateShortCut "$SMPROGRAMS\Work Space\Work Space.lnk" "$INSTDIR\WorkSpace.exe"
  CreateShortCut "$DESKTOP\Work Space.lnk" "$INSTDIR\WorkSpace.exe"
  WriteRegStr HKCU "Software\WorkSpace" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorkSpace" "DisplayName" "Work Space"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorkSpace" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorkSpace" "DisplayIcon" "$INSTDIR\WorkSpace.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorkSpace" "UninstallString" '"$INSTDIR\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  SetRegView 64
  SetShellVarContext current
  Delete "$DESKTOP\Work Space.lnk"
  Delete "$SMPROGRAMS\Work Space\Work Space.lnk"
  RMDir "$SMPROGRAMS\Work Space"
  Delete "$INSTDIR\WorkSpace.exe"
  Delete "$INSTDIR\current.json"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\downloads\WorkSpace-Setup-*-x64.exe"
  Delete "$INSTDIR\downloads\WorkSpace-Setup-*-x64.part"
  RMDir "$INSTDIR\downloads"
  RMDir /r "$INSTDIR\versions\${VERSION}"
  RMDir "$INSTDIR\versions"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorkSpace"
  DeleteRegValue HKCU "Software\WorkSpace" "InstallDir"
SectionEnd
