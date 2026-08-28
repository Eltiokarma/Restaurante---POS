@echo off
REM Arranque en modo produccion (Windows): compila el frontend una vez y
REM levanta todo el sistema en el puerto 8000 con un solo proceso.
REM
REM   Doble clic en este archivo, o desde cmd:  scripts\iniciar.bat
REM
REM URLs: http://localhost:8000/  (cliente) - /cocina - /admin - /ticketera

cd /d "%~dp0.."

if not exist backend\.env (
  echo Falta backend\.env - copia backend\.env.example y pon tu contrasena.
  pause
  exit /b 1
)

echo Compilando frontend...
cd frontend
call npm run build
if errorlevel 1 (
  pause
  exit /b 1
)
cd ..

echo Iniciando servidor en http://localhost:8000
cd backend
call .venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
