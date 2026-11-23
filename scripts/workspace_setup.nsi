Unicode true
!ifdef SETUP_AMD64
Target amd64-unicode
!endif
!include "MUI2.nsh"
!include "x64.nsh"

Name "Work Space ${VERSION}"
OutFile "${SETUP_FILE}"
InstallDir "$LOCALAPPDATA\Programs\WorkSpace"
InstallDirRegKey HKCU "Software\WorkSpace" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 16
ShowInstDetails show

!define MUI_ICON "..\assets\workspace.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\WorkSpace.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
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
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\WorkSpaceRunning") p.r0'
  StrCmp $0 0 done
  System::Call 'kernel32::CloseHandle(p r0)'
  MessageBox MB_ICONSTOP "Work Space를 종료한 뒤 설치해 주세요."
  Abort
  done:
FunctionEnd

Section "Work Space"
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
  RMDir /r "$INSTDIR\versions\${VERSION}"
  RMDir "$INSTDIR\versions"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorkSpace"
  DeleteRegValue HKCU "Software\WorkSpace" "InstallDir"
SectionEnd
