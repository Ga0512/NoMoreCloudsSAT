@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Satellite WebApp — Running

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   🛰️  Satellite Image Compositor                ║
echo ╚══════════════════════════════════════════════════╝
echo.

:: Verifica se setup foi executado
if not exist "venv" (
    echo ❌ Ambiente virtual nao encontrado. Execute setup.bat primeiro!
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo ❌ Dependencias Node.js nao encontradas. Execute setup.bat primeiro!
    pause
    exit /b 1
)

:: Cria pastas se nao existem
if not exist "outputs" mkdir outputs
if not exist "uploads" mkdir uploads

:: ─────────────────────────────────────────────────────
:: INICIA BACKEND (FastAPI) em nova janela
:: ─────────────────────────────────────────────────────
echo Iniciando Backend (FastAPI) na porta 8000...
start "Backend - FastAPI" cmd /k "cd /d %~dp0 && call venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000"

:: Espera backend subir
echo Aguardando backend iniciar...
timeout /t 4 /nobreak >nul

:: ─────────────────────────────────────────────────────
:: INICIA FRONTEND (Node.js) em nova janela
:: ─────────────────────────────────────────────────────
echo Iniciando Frontend (Node.js) na porta 3000...
start "Frontend - Node.js" cmd /k "cd /d %~dp0\frontend && node server.js"

:: Espera frontend subir
timeout /t 2 /nobreak >nul

:: ─────────────────────────────────────────────────────
:: ABRE NAVEGADOR
:: ─────────────────────────────────────────────────────
echo Abrindo navegador...
start http://localhost:3000

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   ✅ App rodando!                                ║
echo ║                                                  ║
echo ║   🌐 WebApp:  http://localhost:3000              ║
echo ║   📡 API:     http://localhost:8000              ║
echo ║   📚 Docs:    http://localhost:8000/docs         ║
echo ║                                                  ║
echo ║   Para parar: feche as janelas do terminal       ║
echo ║   ou pressione Ctrl+C em cada uma.               ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
