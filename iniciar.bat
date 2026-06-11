@echo off
REM ============================================================
REM   Painel de Suprimentos - Impressoras
REM   Duplique clicar neste arquivo para iniciar
REM ============================================================

REM -- Garante que o cmd fica na pasta deste .bat, nao no System32 --
cd /d "%~dp0"

echo Instalando dependencias (so na primeira vez)...
pip install flask

echo.
echo Iniciando o painel... o navegador vai abrir sozinho em http://localhost:5000
echo Para parar: feche esta janela ou pressione Ctrl+C
echo.
python app.py
pause
