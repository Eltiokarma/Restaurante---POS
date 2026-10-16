# Servicio del estudio de rentabilidad (aparte del POS). En Railway:
# Root Directory = /estudio, variables DATABASE_URL (referencia a la
# base Postgres del estudio) y ESTUDIO_TOKEN.

# 1) El panel (React) se compila aquí y se sirve desde el mismo servicio
FROM node:20-slim AS panel
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
COPY --from=panel /web/dist ./web/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
