$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot '书籍制作工具'
$dst = Join-Path $env:LOCALAPPDATA 'Programs\XPlusBookTool'
Write-Host "正在安装到：$dst"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force

$wsh = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = $wsh.CreateShortcut((Join-Path $desktop '书籍制作工具.lnk'))
$lnk.TargetPath = (Join-Path $dst '书籍制作工具.exe')
$lnk.WorkingDirectory = $dst
$lnk.IconLocation = (Join-Path $dst '书籍制作工具.exe')
$lnk.Save()

$programs = [Environment]::GetFolderPath('Programs')
$lnk2 = $wsh.CreateShortcut((Join-Path $programs '书籍制作工具.lnk'))
$lnk2.TargetPath = (Join-Path $dst '书籍制作工具.exe')
$lnk2.WorkingDirectory = $dst
$lnk2.Save()

Copy-Item (Join-Path $PSScriptRoot '卸载.ps1') (Join-Path $dst '卸载.ps1') -Force
Copy-Item (Join-Path $PSScriptRoot '卸载.bat') (Join-Path $dst '卸载.bat') -Force

$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\XPlusBookTool'
New-Item -Path $key -Force | Out-Null
Set-ItemProperty $key DisplayName '书籍制作工具'
Set-ItemProperty $key DisplayVersion '1.0.0'
Set-ItemProperty $key Publisher 'LOU0122'
Set-ItemProperty $key DisplayIcon (Join-Path $dst '书籍制作工具.exe')
Set-ItemProperty $key UninstallString ('"' + (Join-Path $dst '卸载.bat') + '"')

Write-Host ''
Write-Host '安装完成：桌面和开始菜单都有「书籍制作工具」。'
Write-Host '首次运行如果提示“未知发布者”，点“更多信息 → 仍要运行”。'
Start-Process (Join-Path $dst '书籍制作工具.exe')
