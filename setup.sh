#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   🛰️  Satellite Image Compositor — SETUP         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ─────────────────────────────────────────────────────
# 1. VERIFICA / INSTALA PYTHON
# ─────────────────────────────────────────────────────
echo "[1/6] Verificando Python..."
if command -v python3 &>/dev/null; then
    PYTHON=python3
    echo "  ✅ $(python3 --version) encontrado."
elif command -v python &>/dev/null; then
    PYTHON=python
    echo "  ✅ $(python --version) encontrado."
else
    echo "  ❌ Python não encontrado. Instalando..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    elif command -v brew &>/dev/null; then
        brew install python@3.12
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip
    else
        echo "  ❌ Não foi possível instalar Python automaticamente."
        echo "     Instale manualmente: https://www.python.org/downloads/"
        exit 1
    fi
    PYTHON=python3
    echo "  ✅ Python instalado."
fi

# ─────────────────────────────────────────────────────
# 2. VERIFICA / INSTALA NODE.JS
# ─────────────────────────────────────────────────────
echo "[2/6] Verificando Node.js..."
if command -v node &>/dev/null; then
    echo "  ✅ Node.js $(node --version) encontrado."
else
    echo "  ❌ Node.js não encontrado. Instalando..."
    if command -v apt-get &>/dev/null; then
        # Instala via NodeSource
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    elif command -v brew &>/dev/null; then
        brew install node
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y nodejs npm
    else
        echo "  ❌ Não foi possível instalar Node.js automaticamente."
        echo "     Instale manualmente: https://nodejs.org/"
        exit 1
    fi
    echo "  ✅ Node.js instalado."
fi

# ─────────────────────────────────────────────────────
# 3. CRIA AMBIENTE VIRTUAL PYTHON
# ─────────────────────────────────────────────────────
echo "[3/6] Criando ambiente virtual Python..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "  ✅ Venv criado."
else
    echo "  ✅ Venv já existe."
fi

# Ativa venv
source venv/bin/activate

# ─────────────────────────────────────────────────────
# 4. INSTALA DEPENDENCIAS PYTHON
# ─────────────────────────────────────────────────────
echo "[4/6] Instalando dependências Python (pode demorar na primeira vez)..."
pip install --upgrade pip -q
pip install -r requirements.txt
echo "  ✅ Dependências Python instaladas."

# ─────────────────────────────────────────────────────
# 5. INSTALA DEPENDENCIAS NODE.JS
# ─────────────────────────────────────────────────────
echo "[5/6] Instalando dependências Node.js..."
cd frontend
npm install --silent
cd ..
echo "  ✅ Dependências Node.js instaladas."

# ─────────────────────────────────────────────────────
# 6. CRIA PASTAS
# ─────────────────────────────────────────────────────
echo "[6/6] Criando pastas..."
mkdir -p outputs uploads
echo "  ✅ Pastas criadas."

# ─────────────────────────────────────────────────────
# PRONTO
# ─────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   ✅ Setup concluído!                            ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║   Para rodar o app:                              ║"
echo "║     ./run.sh                                     ║"
echo "║                                                  ║"
echo "║   CONTAS NECESSÁRIAS:                            ║"
echo "║   • Google Earth Engine:                         ║"
echo "║     https://earthengine.google.com/              ║"
echo "║   • Copernicus Data Space:                       ║"
echo "║     https://dataspace.copernicus.eu/             ║"
echo "║   • Planetary Computer: sem conta (público)      ║"
echo "║                                                  ║"
echo "║   (Opcional) Pré-autenticar GEE:                 ║"
echo "║     source venv/bin/activate                     ║"
echo "║     earthengine authenticate                     ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
