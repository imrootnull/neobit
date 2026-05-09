#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  NeoBit Gateway — Network Start Script
# ─────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

# ── 0. Limpiar procesos y shared memory anteriores ───────────────
echo "🧹 Limpiando procesos anteriores..."
pkill -9 -f "python3 run.py"   2>/dev/null || true
pkill -9 -f "python3 worker.py" 2>/dev/null || true
sleep 1
# Limpiar slots de shared memory de corridas anteriores
python3 -c "
import glob
from multiprocessing.shared_memory import SharedMemory
for name in ['nb_raw_2','nb_ann_2','nb_raw_3','nb_ann_3']:
    try:
        s = SharedMemory(name=name); s.close(); s.unlink()
        print(f'  limpiado: {name}')
    except Exception:
        pass
" 2>/dev/null || true

# ── 1. Build del dashboard ────────────────────────────────────────
echo "🔨 Compilando dashboard..."
cd dashboard && npm run build --silent && cd ..
echo "✅ Dashboard compilado"

# ── 2. Detectar IP local ──────────────────────────────────────────
LOCAL_IP=$(hostname -I | awk '{print $1}')
PORT=8000

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🚀 NeoBit Gateway arrancando..."
echo "  📡 http://${LOCAL_IP}:${PORT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 3. Levantar HTTP server ───────────────────────────────────────
export NEOBIT_NO_INFERENCE=1
export HSA_OVERRIDE_GFX_VERSION=12.0.0
unset CUDA_VISIBLE_DEVICES
python3 run.py &
HTTP_PID=$!
echo "  [PID ${HTTP_PID}] HTTP server"

# ── 4. Levantar analytics worker ─────────────────────────────────
sleep 2
python3 worker.py &
WORKER_PID=$!
echo "  [PID ${WORKER_PID}] Analytics worker (GPU)"
echo ""
echo "  Ctrl+C para detener"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 5. Esperar y limpiar ──────────────────────────────────────────
_cleanup() {
    echo ""
    echo "Deteniendo procesos..."
    kill "$HTTP_PID" "$WORKER_PID" 2>/dev/null || true
    wait "$HTTP_PID" "$WORKER_PID" 2>/dev/null || true
    exit 0
}
trap _cleanup INT TERM

# Si uvicorn muere, matar worker también y salir
wait "$HTTP_PID"
echo "⚠️  HTTP server terminó — deteniendo worker..."
kill "$WORKER_PID" 2>/dev/null || true

