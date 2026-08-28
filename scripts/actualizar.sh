#!/usr/bin/env bash
# Actualiza el POS a la última versión publicada y lo inicia.
# No toca la base de datos (pos.db) ni la configuración (.env).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "▸ Descargando la última versión…"
git pull

echo "▸ Actualizando dependencias del backend…"
(cd backend && source .venv/bin/activate && pip install -r requirements.txt)

echo "▸ Actualizando dependencias de la interfaz…"
(cd frontend && npm install)

echo "▸ Todo actualizado. Iniciando el sistema…"
exec ./scripts/iniciar.sh
