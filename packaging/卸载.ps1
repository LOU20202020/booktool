$dst = Join-Path $env:LOCALAPPDATA 'Programs\XPlusBookTool'
Get-Process '书籍制作工具' -ErrorAction SilentlyContinue | Stop-Process -Force
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
Remove-Item (Join-Path $desktop '书籍制作工具.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $programs '书籍制作工具.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\XPlusBookTool' -Recurse -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300
Remove-Item $dst -Recurse -Force -ErrorAction SilentlyContinue
Write-Host '已卸载。'
