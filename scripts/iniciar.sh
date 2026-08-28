#!/usr/bin/env bash
# Arranque en modo producción (Linux/macOS): compila el frontend una vez y
# levanta todo el sistema en el puerto 8000 con un solo proceso.
#
#   ./scripts/iniciar.sh
#
# URLs: http://localhost:8000/  (cliente) · /cocina · /admin · /ticketera
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f backend/.env ]; then
  echo "⚠️  Falta backend/.env — copia backend/.env.example y pon tu contraseña."
  exit 1
fi

echo "▸ Compilando frontend…"
(cd frontend && npm run build)

echo "▸ Iniciando servidor en http://localhost:8000"
cd backend
source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
