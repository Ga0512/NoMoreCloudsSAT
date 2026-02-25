#!/bin/bash

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   🛰️  Satellite Image Compositor                ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Verifica se setup foi executado
if [ ! -d "venv" ]; then
    echo "❌ Ambiente virtual não encontrado. Execute ./setup.sh primeiro!"
    exit 1
fi

if [ ! -d "frontend/node_modules" ]; then
    echo "❌ Dependências Node.js não encontradas. Execute ./setup.sh primeiro!"
    exit 1
fi

# Cria pastas
mkdir -p outputs uploads

# Ativa venv
source venv/bin/activate

# ── Inicia Backend ──
echo "🚀 Iniciando Backend (FastAPI) na porta 8000..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

sleep 3

# ── Inicia Frontend ──
echo "🚀 Iniciando Frontend (Node.js) na porta 3000..."
cd frontend
node server.js &
FRONTEND_PID=$!
cd "$PROJECT_DIR"

sleep 2

# ── Abre navegador ──
echo "🌐 Abrindo navegador..."
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:3000 2>/dev/null &
elif command -v open &>/dev/null; then
    open http://localhost:3000
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   ✅ App rodando!                                ║"
echo "║                                                  ║"
echo "║   🌐 WebApp:  http://localhost:3000              ║"
echo "║   📡 API:     http://localhost:8000              ║"
echo "║   📚 Docs:    http://localhost:8000/docs         ║"
echo "║                                                  ║"
echo "║   Pressione Ctrl+C para parar tudo.              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Cleanup ao sair
cleanup() {
    echo ""
    echo "🛑 Parando serviços..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo "👋 Encerrado."
    exit 0
}

trap cleanup SIGINT SIGTERM

# Mantém rodando
wait
