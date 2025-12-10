@echo off
:: One-click stealth deployment launcher
:: Right-click and "Run as Administrator" for best results

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0deploy.ps1"

