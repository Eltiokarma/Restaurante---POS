# Servicio del estudio de rentabilidad (aparte del POS). En Railway:
# Root Directory = /estudio, variables DATABASE_URL (referencia a la
# base Postgres del estudio) y ESTUDIO_TOKEN.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
