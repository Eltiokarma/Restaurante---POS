@echo off
REM Puente de impresion: conecta el POS, este en la nube o en la laptop,
REM con la impresora termica de red del local. Deja esta ventana abierta
REM durante el servicio.
REM
REM La primera vez pide la URL del POS y el PIN, y los recuerda en
REM puente-config.txt. Borra ese archivo si quieres cambiarlos.

setlocal
cd /d "%~dp0"
set "CONFIG=puente-config.txt"
set "POS_URL="
set "POS_PIN="

if not exist "%CONFIG%" goto preguntar
for /f "usebackq tokens=1,* delims==" %%a in ("%CONFIG%") do (
    if "%%a"=="URL" set "POS_URL=%%b"
    if "%%a"=="PIN" set "POS_PIN=%%b"
)
if "%POS_URL%"=="" goto preguntar
goto iniciar

:preguntar
echo.
echo Direccion de tu POS, por ejemplo: https://tu-pos.up.railway.app
set /p POS_URL=URL del POS:
echo.
echo PIN del local, el mismo que piden las pantallas. Enter si no tiene.
set /p POS_PIN=PIN:
>"%CONFIG%" echo URL=%POS_URL%
>>"%CONFIG%" echo PIN=%POS_PIN%

:iniciar
echo.
echo Iniciando puente de impresion hacia %POS_URL% ...
python puente_impresion.py --url "%POS_URL%" --pin "%POS_PIN%"
echo.
echo El puente se detuvo. Revisa el mensaje de arriba.
pause
