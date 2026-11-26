@echo off
setlocal
cd /d "%~dp0"
py -m gestor_peliculas.cli servir --abrir-navegador
if errorlevel 1 (
 echo.
 echo El Gestor de Peliculas finalizo con un error.
 echo Si es la primera vez, instala las dependencias con:
 echo     py -m pip install -e .
 pause
)
endlocal
