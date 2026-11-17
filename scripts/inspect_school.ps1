param([switch]$UseForeground, [int]$InspectorProcessId=0)
# Read-only inspection: no Invoke, Select, SetValue, focus, mouse, or keyboard calls.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$probeStage='Windows UI Automation 초기화'
trap {
 @{status='error';message='화면 인식 도중 오류가 발생했습니다.';stage=$probeStage;error_type=$_.Exception.GetType().FullName;error_category=[string]$_.CategoryInfo.Category;script_line=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json -Compress
 exit 1
}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class SchoolWindows {
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 public delegate bool Callback(IntPtr h, IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumWindows(Callback callback, IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, Callback callback, IntPtr p);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder text, int count);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder text, int count);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
'@
$probeStage='학사 프로세스 찾기'
$expected = 'C:\hguniv\download\학사정보시스템.exe'
if ($UseForeground) {
 $foreground=[SchoolWindows]::GetForegroundWindow()
 [uint32]$foregroundOwner=0
 [void][SchoolWindows]::GetWindowThreadProcessId($foreground,[ref]$foregroundOwner)
 if ($foregroundOwner -eq 0 -or $foregroundOwner -eq $InspectorProcessId -or $foregroundOwner -eq $PID) {
  @{status='not_found';message='학사 프로그램 창을 활성화한 뒤 다시 검사하세요. 업무 도구 창이 선택되어 있습니다.'} | ConvertTo-Json -Compress
  exit
 }
 $targets = @(Get-Process -Id $foregroundOwner -ErrorAction SilentlyContinue)
} else {
 $targets = @(Get-Process | Where-Object { try { $_.Path -ieq $expected } catch { $false } })
}
if ($targets.Count -eq 0) {
 @{status='not_found';message='지정 경로의 프로세스를 찾지 못했습니다. 현재 활성 창 검사 옵션을 선택하고 학사 창을 활성화해 주세요.'} | ConvertTo-Json -Compress
 exit
}
$ids = @($targets | ForEach-Object { $_.Id })
$handles = New-Object 'System.Collections.Generic.List[System.IntPtr]'
$enum = [SchoolWindows+Callback]{param($h,$p)
 [uint32]$owner=0; [void][SchoolWindows]::GetWindowThreadProcessId($h,[ref]$owner)
 if (($ids -contains [int]$owner) -and [SchoolWindows]::IsWindowVisible($h)) { $handles.Add($h) }
 return $true
}
[void][SchoolWindows]::EnumWindows($enum,[IntPtr]::Zero)
$patterns = [ordered]@{
 '매입'='^매입$';'매출'='^매출$';'세금계산서'='^세금계산서$';'계산서'='^계산서$';
 '조회'='^(조회|조회\([A-Z]\))$';'기본엑셀'='^기본엑셀$';
 '저장'='^(저장|저장\([A-Z]\))$';'파일 이름'='^파일이름(?:\([A-Z]\))?[:：]?$';
 '작성년월일'='^작성[년연]월일$';'합계표'='^\(세금\)계산서합계표$'
}
$recognizedControls = New-Object System.Collections.ArrayList
$classes = @{}; $types = @{}; $scanned=0; $truncated=$false
function Record-Control($name,$class,$type,$backend,$visible,$enabled,$patternsAvailable) {
 $text=([string]$name -replace '\s','' -replace '&','')
 foreach ($label in $patterns.Keys) {
  if ($text -match $patterns[$label]) {
   [void]$recognizedControls.Add(@{label=$label;backend=$backend;class=[string]$class;type=[string]$type;visible=$visible;enabled=$enabled;patterns=@($patternsAvailable)})
  }
 }
}
$probeStage='화면 요소 읽기'
foreach ($handle in $handles) {
 try {
  $root=[System.Windows.Automation.AutomationElement]::FromHandle($handle)
  $queue=New-Object System.Collections.Queue
  $queue.Enqueue(@($root,0))
  $walker=[System.Windows.Automation.TreeWalker]::ControlViewWalker
  while ($queue.Count -gt 0) {
   if ($scanned -ge 1800) { $truncated=$true;break }
   $pair=$queue.Dequeue();$element=$pair[0];$depth=[int]$pair[1];$scanned++
   try {
    $current=$element.Current
    if ($ids -notcontains $current.ProcessId) {continue}
    $class=[string]$current.ClassName;$type=[string]$current.ControlType.ProgrammaticName
    if ($class) {if (!$classes.ContainsKey($class)) {$classes[$class]=0};$classes[$class]++}
    if (!$types.ContainsKey($type)) {$types[$type]=0};$types[$type]++
    $supported=@($element.GetSupportedPatterns() | ForEach-Object {$_.ProgrammaticName})
    if ($type -notin @('ControlType.DataGrid','ControlType.Table','ControlType.DataItem','ControlType.ListItem','ControlType.Edit')) {
     Record-Control $current.Name $class $type 'UIA' (!$current.IsOffscreen) $current.IsEnabled $supported
    }
    if ($type -in @('ControlType.DataGrid','ControlType.Table','ControlType.DataItem','ControlType.ListItem')) {continue}
    if ($depth -lt 14) {
     $child=$walker.GetFirstChild($element)
     while ($null -ne $child) {
      $queue.Enqueue(@($child,($depth+1)));$child=$walker.GetNextSibling($child)
      if ($queue.Count -ge 1800) {$truncated=$true;break}
     }
    } else {$truncated=$true}
   } catch { }
  }
 } catch { }
 # Legacy controls may expose HWND text but no UIA patterns. Read them separately.
 $legacy=[SchoolWindows+Callback]{param($h,$p)
  $name=New-Object System.Text.StringBuilder 512;$class=New-Object System.Text.StringBuilder 256
  [void][SchoolWindows]::GetClassName($h,$class,256)
  if ($class.ToString() -match 'Edit|Grid|List|Combo') {return $true}
  [void][SchoolWindows]::GetWindowText($h,$name,512)
  Record-Control ($name.ToString()) ($class.ToString()) 'HWND' 'Win32' ([SchoolWindows]::IsWindowVisible($h)) $null @()
  return $true
 }
 [void][SchoolWindows]::EnumChildWindows($handle,$legacy,[IntPtr]::Zero)
}
@{status='ok';selection_mode=$(if ($UseForeground) {'foreground'} else {'path'});process_names=@($targets | ForEach-Object {$_.ProcessName});process_count=$targets.Count;window_count=$handles.Count;scanned=$scanned;truncated=$truncated;matches=@($recognizedControls);control_types=$types;control_classes=$classes} | ConvertTo-Json -Depth 7 -Compress
