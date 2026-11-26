# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Instalar en modo editable (la primera vez)
py -m pip install -e ".[dev]"

# Levantar la web (waitress, solo 127.0.0.1)
py -m gestor_peliculas.cli servir --abrir-navegador
# O el lanzador de Windows
iniciar_app.bat

# Comandos de consola
py -m gestor_peliculas.cli estado
py -m gestor_peliculas.cli indexar "D:\Peliculas"
py -m gestor_peliculas.cli enriquecer --limite 50
py -m gestor_peliculas.cli organizar "D:\Peliculas" --renombrar-pares --escribir
py -m gestor_peliculas.cli vincular --escribir
py -m gestor_peliculas.cli importar-puntajes title.ratings.tsv.gz

# Tests y linter
py -m pytest
py -m ruff check .
```

## Arquitectura

Estructura `src/` layout. La regla que sostiene todo:

```
web/ y cli/  ->  servicios/  ->  catalogo/ busqueda/ metadatos/ organizador/ reproduccion/
                                          ->  nucleo/  y  almacenamiento/
```

Nunca al revés. `nucleo/` no importa nada del propio proyecto.

**`nucleo/`** — lógica pura, sin red ni disco. Es lo más testeado:
- `titulos.py`: `parsear_anio_titulo()` acepta las tres convenciones que en el
  proyecto viejo estaban separadas (`AÑO - TÍTULO` del linker, año suelto del
  HTML, nombre crudo del Organizador) y devuelve un `OrigenAnio` que dice
  cuánto confiar en el año. `quitar_sufijo_origen()` saca los paréntesis de
  país o idioma, pero no los subtítulos oficiales.
- `identificadores.py`: extrae `tt\d{7,}` de URLs, nombres de archivo y
  sidecars (`.url` en UTF-16 con BOM, `.nfo` de Kodi con `<uniqueid>`).
- `coincidencias.py`: `clasificar()` decide `EXACTA` / `REVISAR` /
  `SIN_COINCIDENCIA`. **Sólo una ficha única con título principal y año exactos
  se guarda sin preguntar.** Es la regla más importante del proyecto.

**`almacenamiento/`** — SQLite con `user_version` para migraciones.
`peliculas.ruta_relativa` es relativa a la ubicación, nunca absoluta, para que
mover el disco no invalide el catálogo. `repositorio_peliculas._sincronizar_fts()`
es el único lugar que toca `peliculas_fts`; hay que llamarlo tras cualquier
cambio de título o ficha.

**`catalogo/`** — `escaner.py` recorre con `os.scandir`, `sidecars.py` lee los
`imdb.url` / `poster.jpg` que deja el linker, `indexador.py` sincroniza. El
re-indexado es idempotente y **no pisa** el `imdb_id` ni el póster ya conocidos
(ver `alta_o_actualizacion`).

**`busqueda/`** — FTS5 con fallback a `LIKE`. `preparar_consulta_fts()` cita y
agrega `*` a cada palabra: un texto cualquiera no puede ser sintaxis FTS5
inválida y hacer fallar la consulta.

**`metadatos/`** — `sesion_http.py` tiene lo que al original le faltaba:
reintentos con backoff, caché en memoria y `ErrorFuenteExterna.detener_lote`
para cortar el lote ante 401/403/429/5xx. `enriquecedor.py` consulta TMDb;
`vinculador.py` es la cascada IMDb → Wikidata → TMDb → Wikipedia.

**`servicios/tareas.py`** — registro de tareas en hilo con progreso y
cancelación. La web consulta `GET /tareas/<id>` y `progreso.js` mueve la barra.
Una sola tarea viva por tipo.

**`web/`** — sólo interfaz. Bootstrap 5.3 vendorizado en
`static/vendor/bootstrap/` (sin CDN: la app funciona sin internet). La paleta
del original está en `static/css/cinemateca.css` como variables `--bs-*`.

## Reglas que no hay que romper

1. **`organizar` y `vincular` simulan por defecto.** Escribir exige
   `--escribir` en consola o marcar la casilla de confirmación en la web.
2. **Nunca se borra de forma definitiva.** Todo va a la Papelera con
   `send2trash`.
3. **Nunca se sobrescribe un sidecar.** Si ya hay un `imdb.url`, no se toca.
4. **El servidor escucha sólo en 127.0.0.1** y todos los POST llevan token CSRF:
   la aplicación lanza procesos y renombra archivos.
5. **Ninguna credencial en el código.** Van en `.env`, que está en `.gitignore`.

## Trampas de Windows

- `Path("A.mkv") == Path("a.mkv")` devuelve **True** en Windows: `PurePath`
  compara sin distinguir la caja. Para decidir si un archivo hay que renombrar
  se usa `renombrador.misma_ruta_exacta()`, que compara con `str()`.
- Un renombrado que sólo cambia mayúsculas necesita dos pasos con un nombre
  temporal (`renombrar_solo_caja`), porque NTFS no distingue la caja.
- Al pasar a minúsculas se recorren primero los archivos y después las
  carpetas, ordenadas de la ruta más larga a la más corta.
- Los enlaces simbólicos y puntos de unión (`FILE_ATTRIBUTE_REPARSE_POINT`) se
  saltean siempre, para no salir de la colección ni entrar en bucles.

## Dependencias clave

```
Flask, Flask-WTF, Jinja2, requests, python-dotenv, Pillow, Send2Trash, waitress
pytest, ruff
```

Bootstrap 5.3.3 va vendorizado, no por npm: no hay paso de compilación.

## Datos

La base vive en `%LOCALAPPDATA%\GestorPeliculas\cinemateca.db`, **fuera del
proyecto**, porque el proyecto está en OneDrive y SQLite en una carpeta
sincronizada se corrompe. Se puede redirigir con `GESTOR_DATOS_DIR`.
