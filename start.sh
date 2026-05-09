#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  NeoBit Gateway — Network Start Script
#  Two-process architecture:
#    PID A: uvicorn HTTP server  (no inference → no GIL contention)
#    PID B: analytics worker     (YOLO/InsightFace — own GIL)
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

# ── 3. Levantar HTTP server (sin inferencia) ──────────────────────
export NEOBIT_NO_INFERENCE=1
python3 run.py &
HTTP_PID=$!
echo "  [PID ${HTTP_PID}] HTTP server"

# ── 4. Levantar analytics worker (inferencia separada) ────────────
sleep 2   # espera que uvicorn levante primero
python3 worker.py &
WORKER_PID=$!
echo "  [PID ${WORKER_PID}] Analytics worker"

echo ""
echo "  Ctrl+C para detener ambos procesos"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 5. Esperar y limpiar ──────────────────────────────────────────
trap "echo ''; echo 'Deteniendo...'; kill $HTTP_PID $WORKER_PID 2>/dev/null; exit 0" INT TERM
wait $HTTP_PID
