@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Satellite WebApp — Setup

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   🛰️  Satellite Image Compositor — SETUP         ║
echo ╚══════════════════════════════════════════════════╝
echo.

:: ─────────────────────────────────────────────────────
:: 1. VERIFICA / INSTALA PYTHON
:: ─────────────────────────────────────────────────────
echo [1/6] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python nao encontrado. Tentando instalar via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo   ❌ Nao foi possivel instalar Python automaticamente.
        echo      Baixe e instale manualmente: https://www.python.org/downloads/
        echo      IMPORTANTE: Marque "Add Python to PATH" durante a instalacao!
        echo.
        pause
        exit /b 1
    )
    echo   ✅ Python instalado. REINICIE este terminal e rode setup.bat novamente.
    pause
    exit /b 0
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   ✅ Python %%v encontrado.
)

:: ─────────────────────────────────────────────────────
:: 2. VERIFICA / INSTALA NODE.JS
:: ─────────────────────────────────────────────────────
echo [2/6] Verificando Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Node.js nao encontrado. Tentando instalar via winget...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo   ❌ Nao foi possivel instalar Node.js automaticamente.
        echo      Baixe e instale manualmente: https://nodejs.org/
        echo.
        pause
        exit /b 1
    )
    echo   ✅ Node.js instalado. REINICIE este terminal e rode setup.bat novamente.
    pause
    exit /b 0
) else (
    for /f "tokens=1" %%v in ('node --version 2^>^&1') do echo   ✅ Node.js %%v encontrado.
)

:: ─────────────────────────────────────────────────────
:: 3. CRIA AMBIENTE VIRTUAL PYTHON
:: ─────────────────────────────────────────────────────
echo [3/6] Criando ambiente virtual Python...
if not exist "venv" (
    python -m venv venv
    echo   ✅ Venv criado.
) else (
    echo   ✅ Venv ja existe.
)

:: Ativa venv
call ./venv/Scripts/activate

:: ─────────────────────────────────────────────────────
:: 4. INSTALA DEPENDENCIAS PYTHON
:: ─────────────────────────────────────────────────────
echo [4/6] Instalando dependencias Python (pode demorar na primeira vez)...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo   ❌ Erro ao instalar dependencias Python. Verifique o log acima.
    pause
    exit /b 1
)
echo   ✅ Dependencias Python instaladas.

:: ─────────────────────────────────────────────────────
:: 5. INSTALA DEPENDENCIAS NODE.JS
:: ─────────────────────────────────────────────────────
echo [5/6] Instalando dependencias Node.js...
cd frontend
call npm install --silent
if %errorlevel% neq 0 (
    echo   ❌ Erro ao instalar dependencias Node.js.
    cd ..
    pause
    exit /b 1
)
cd ..
echo   ✅ Dependencias Node.js instaladas.

:: ─────────────────────────────────────────────────────
:: 6. CRIA PASTAS
:: ─────────────────────────────────────────────────────
echo [6/6] Criando pastas...
if not exist "outputs" mkdir outputs
if not exist "uploads" mkdir uploads
echo   ✅ Pastas criadas.

:: ─────────────────────────────────────────────────────
:: PRONTO
:: ─────────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   ✅ Setup concluido!                            ║
echo ╠══════════════════════════════════════════════════╣
echo ║                                                  ║
echo ║   Para rodar o app:                              ║
echo ║     run.bat                                      ║
echo ║                                                  ║
echo ║   CONTAS NECESSARIAS:                            ║
echo ║   • Google Earth Engine:                         ║
echo ║     https://earthengine.google.com/              ║
echo ║   • Copernicus Data Space:                       ║
echo ║     https://dataspace.copernicus.eu/             ║
echo ║   • Planetary Computer: sem conta (publico)      ║
echo ║                                                  ║
echo ║   (Opcional) Pre-autenticar GEE:                 ║
echo ║     venv\Scripts\activate.bat                    ║
echo ║     earthengine authenticate                     ║
echo ║                                                  ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
