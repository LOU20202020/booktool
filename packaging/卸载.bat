@echo off
chcp 65001 >nul
title 卸载 书籍制作工具
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0卸载.ps1"
pause
