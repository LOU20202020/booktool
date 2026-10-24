@echo off
chcp 65001 >nul
title 安装 书籍制作工具
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0安装.ps1"
pause
