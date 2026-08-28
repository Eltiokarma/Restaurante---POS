# POS de auto-atención — imagen para desplegar en la nube (Railway, etc.)
# Etapa 1: compilar el frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Etapa 2: backend sirviendo el frontend compilado (todo en un puerto)
FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# La BD vive en /data: monta ahí un volumen persistente o se pierde en
# cada despliegue. ADMIN_PASSWORD se define como variable de entorno.
ENV DATABASE_PATH=/data/pos.db
RUN mkdir -p /data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
