@echo off
cd /d "%~dp0"
echo Instalando dependencias (se necessario)...
pip install flask >nul 2>&1
echo.
python diagnostico.py
