# NeoBit AI Analytics Gateway

**Sistema NVR autónomo con IA en el borde** — detección de personas, caídas, EPP, intrusión y más, con grabación circular, compresión H.264/H.265 y gestión de discos externos.

## 🚀 Características

- 📹 **Streaming RTSP multi-cámara** con ONVIF y auto-descubrimiento
- 🧠 **Inferencia IA en tiempo real** — YOLO v8 para personas, vehículos, EPP, caídas, multitudes
- 💾 **NVR circular** — grabación continua o por evento con sobreescritura automática
- 🗜️ **Compresión H.264/H.265** vía ffmpeg — mismo estándar que NVRs profesionales
- 💿 **Selección de disco** — soporta USB, disco externo, NAS
- 📊 **Dashboard en tiempo real** — eventos, snapshots, clips de video con streaming HTTP Range
- ⚙️ **Control de resolución y FPS** — downscale en software sin tocar la cámara

## 📋 Requisitos

- Python 3.11+
- Node.js 18+
- `ffmpeg` (opcional, para compresión H.264/H.265)

```bash
sudo apt-get install ffmpeg   # Ubuntu/Debian
```

## ⚡ Instalación rápida

```bash
# 1. Backend
pip install -r requirements.txt

# 2. Frontend
cd dashboard && npm install && cd ..

# 3. Ejecutar
python run.py
```

El dashboard estará disponible en `http://localhost:5174`
La API en `http://localhost:8000`

## 📁 Modelos YOLO

Descarga automáticamente al primer arranque:
- `yolov8n.pt` — detección general
- `yolov8n-pose.pt` — detección de caídas

## 🗂️ Estructura

```
neobit/
├── backend/          # FastAPI + SQLAlchemy
│   ├── api/          # Endpoints REST
│   ├── core/         # Stream, Recording, EventBus
│   ├── inference/    # Pipeline YOLO + FallDetector
│   └── storage/      # DB models
├── dashboard/        # Vite + React frontend
└── run.py            # Punto de entrada
```

## 🔑 Variables de entorno

Copia `.env.example` a `.env` y configura:

```env
MAX_CAMERAS=16
SECRET_KEY=cambia_esto
```
