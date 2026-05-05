#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  NeoBit Gateway — Network Start Script
#  Levanta el backend sirviendo el dashboard compilado.
#  Accesible desde cualquier PC en la misma red.
# ─────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

# ── 1. Build del dashboard (si hay cambios) ───────────────────────
echo "🔨 Compilando dashboard..."
cd dashboard && npm run build --silent && cd ..
echo "✅ Dashboard compilado"

# ── 2. Detectar IP local ──────────────────────────────────────────
LOCAL_IP=$(hostname -I | awk '{print $1}')
PORT=8000

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🚀 NeoBit Gateway arrancando..."
echo "  📡 Acceso desde la red:"
echo "     http://${LOCAL_IP}:${PORT}"
echo "  💻 Acceso local:"
echo "     http://localhost:${PORT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 3. Levantar backend ───────────────────────────────────────────
python3 run.py
