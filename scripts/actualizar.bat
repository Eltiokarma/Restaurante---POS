@echo off
REM Actualiza el POS a la ultima version publicada y lo inicia.
REM Uso: doble clic (con el servidor detenido; cierra su ventana primero).
REM No toca tu base de datos (pos.db) ni tu configuracion (.env).

cd /d "%~dp0.."

echo === Descargando la ultima version...
git pull
if errorlevel 1 (
  echo.
  echo No se pudo descargar. Revisa tu conexion a internet.
  pause
  exit /b 1
)

echo === Actualizando dependencias del backend...
cd backend
call .venv\Scripts\activate
pip install -r requirements.txt
cd ..

echo === Actualizando dependencias de la interfaz...
cd frontend
call npm install
cd ..

echo.
echo === Todo actualizado. Iniciando el sistema...
call scripts\iniciar.bat
