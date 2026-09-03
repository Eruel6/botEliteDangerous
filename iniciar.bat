@echo off
REM iniciar.bat - sobe o cliente e abre o painel no navegador.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale em https://python.org
    echo Marque "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

if not exist config.txt (
    echo Falta o config.txt.
    echo Copie config.exemplo.txt para config.txt e coloque seu token nele.
    pause
    exit /b 1
)

python -m pip install --quiet --disable-pip-version-check requests
python cliente.py
pause
