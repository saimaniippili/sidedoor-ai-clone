@echo off
title Sidedoor Gmail Authentication
cd /d "%~dp0"
echo Starting Gmail authentication flow...
.\venv\Scripts\python.exe generate_token.py
echo.
pause
