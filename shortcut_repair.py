"""Repair this installation's own user shortcuts after an update, on Windows only."""
import base64
from pathlib import Path
import subprocess
import sys


def repair_shortcuts(root):
    if sys.platform!='win32' or not getattr(sys,'frozen',False):return
    root=Path(root).resolve()
    launcher=root/'WorkSpace.exe'
    if not launcher.is_file():return
    # Match this install's stable launcher or legacy versioned app shortcuts.
    literal=str(root).replace("'","''")
    # The stable launcher is intentionally not replaced by ordinary updates.
    # Point shortcuts at the active payload's icon so its image still updates.
    icon=Path(__file__).resolve().parent/'assets'/'workspace.ico'
    icon_literal=str(icon if icon.is_file() else launcher).replace("'","''")
    script="""
$ErrorActionPreference='Stop'
$install='ROOT'
$exe=Join-Path $install 'WorkSpace.exe'
$icon='ICON'
$shell=New-Object -ComObject WScript.Shell
$folders=@([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('StartMenu'))
$pattern='^'+[regex]::Escape((Join-Path $install 'versions'))+'\\\\[^\\\\]+\\\\WorkSpaceApp\\.exe$'
foreach($folder in $folders){
 if(-not $folder){continue}
 Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
  $link=$shell.CreateShortcut($_.FullName)
  if(($link.TargetPath -ieq $exe) -or ($link.TargetPath -match $pattern)){
   $link.TargetPath=$exe;$link.WorkingDirectory=$install;$link.IconLocation=$icon+',0';$link.Save()
  }
 }
}
""".replace("$install='ROOT'","$install='"+literal+"'").replace("$icon='ICON'","$icon='"+icon_literal+"'")
    encoded=base64.b64encode(script.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],check=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),capture_output=True)
