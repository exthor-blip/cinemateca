# Arquitectura

## La regla

```
   web/          cli/
     |             |
     +------+------+
            v
       servicios/            casos de uso: lo único que la interfaz llama
            v
   catalogo/  busqueda/  metadatos/  organizador/  reproduccion/  puntajes.py
            v
      nucleo/        almacenamiento/
   (lógica pura)      (SQLite)
```

Las flechas van en un solo sentido. `nucleo/` no importa nada del propio
proyecto, y por eso es donde vive lo que más se prueba. `web/` no toca la base
ni la red por su cuenta: pide, recibe y renderiza.

El efecto práctico es que todo lo que hace la página se puede hacer desde la
consola, con el mismo código. No hay lógica duplicada entre las dos.

## Los módulos

### `nucleo/` — lógica pura

Sin red, sin disco, sin Flask. Funciones que reciben texto y devuelven texto.

- **`extensiones.py`** — un solo juego de extensiones para todo el proyecto.
  Antes cada pieza tenía la suya y no coincidían.
- **`titulos.py`** — el parseo de nombres de carpeta. `parsear_anio_titulo()`
  devuelve un `OrigenAnio` (`EXPLICITO`, `SUELTO`, `AUSENTE`) para que quien
  necesite ser estricto pueda serlo: el vinculador no busca con un año suelto.
- **`identificadores.py`** — extraer `tt…` de donde sea.
- **`coincidencias.py`** — la decisión de cuándo una coincidencia es segura.

### `almacenamiento/` — persistencia

SQLite en WAL, con `foreign_keys` encendido y migraciones por `user_version`.

```
ubicaciones ─┬─ peliculas ─┬─ metadatos
             │             ├─ revisiones
             │             └─ pelicula_etiquetas ── etiquetas
             │
             └─ (peliculas.imdb_id) ── puntajes_imdb
                                       peliculas_fts
```

Dos decisiones que importan:

- **`ruta_relativa`, no absoluta.** Mover el disco de películas no invalida el
  catálogo. El `.imdb_linker_estado.json` original indexaba por ruta absoluta y
  se perdía entero al renombrar la raíz.
- **Etiquetas normalizadas.** País, género e idioma son filas de `etiquetas`,
  no texto repetido. Los desplegables de filtros son una consulta con conteo,
  no un recorrido de todo el catálogo en memoria.

### `catalogo/` — carga de películas

Una película es una carpeta con al menos un vídeo.

`escaner.py` recorre con `os.scandir` (bastante más rápido que `iterdir` en
Windows) y devuelve un generador, así un indexado de miles de carpetas puede
informar progreso y cancelarse. `sidecars.py` lee los `imdb.url` y `poster.jpg`
que deja el linker: ese es el contrato con el proyecto viejo, y por eso una
colección ya procesada aparece completa desde el primer indexado.

`indexador.py` es idempotente: re-indexar no duplica nada y **no pisa** el
`imdb_id` ni el póster ya conocidos. Si el escaneo no encuentra sidecar pero la
base ya tenía un identificador, se conserva.

`duplicados.py` agrupa la misma película en dos carpetas, pero **conserva las
dos filas**. Dos discos con la misma película son un hecho de la colección;
borrar una significaría no poder reproducirla si el otro disco no está
conectado. Lo que se hace es mostrar una sola tarjeta.

### `busqueda/` — búsqueda y filtros

`FiltroBusqueda` es un objeto inmutable que viaja de la query string al SQL.
Que el filtro sea un dato y no el estado del DOM es lo que hace que una
búsqueda quede en la URL y en el historial del navegador.

La búsqueda de texto usa FTS5 con el tokenizador `unicode61 remove_diacritics 2`,
así «amelie» encuentra «Amélie». `preparar_consulta_fts()` parte el texto en
palabras y las cita: un texto cualquiera no puede ser sintaxis FTS5 inválida y
hacer fallar la consulta. Si FTS5 no estuviera compilado, cae a `LIKE`.

El índice junta el título de la carpeta y el de TMDb, así buscar «Jaws»
encuentra la carpeta «1975 - Tiburón».

### `metadatos/` — fuentes externas

`sesion_http.py` es la base de los cuatro clientes y tiene lo que al original
le faltaba: reintentos con espera creciente, caché en memoria con tiempo de
vida, y errores que distinguen un 401 de un «no está». `ErrorFuenteExterna`
lleva `detener_lote`, que corta el lote entero ante 401, 403, 429 y 5xx.

- `enriquecedor.py` completa la ficha desde TMDb. Dos caminos: con
  identificador IMDb va directo (`find/tt…`, exacto); sin él busca por título y
  año y sólo acepta una coincidencia única.
- `vinculador.py` busca el identificador cuando no lo hay, recorriendo IMDb,
  Wikidata, TMDb y Wikipedia. Una ficha que llega por una vía indirecta nunca
  se da por exacta.

### `organizador/` — archivos en el disco

El único módulo que modifica la colección, y por eso el más conservador:

- simula por defecto,
- nunca sobrescribe,
- nunca borra de forma definitiva: todo va a la Papelera,
- cada operación que escribe deja dos CSV, con el mismo formato que generaba el
  Organizador original.

### `reproduccion/` — VLC

Reemplaza el protocolo propio, las claves de registro y el `.exe` compilado por
un `subprocess.Popen`. Lo que sí se conserva del C# es la validación de ruta,
que era lo valioso de aquel código: la ruta resuelta tiene que seguir estando
dentro de la raíz de la ubicación.

### `servicios/` — casos de uso

Lo único que la interfaz llama. `tareas.py` es un registro de tareas en hilo
con progreso y cancelación: la web lanza el trabajo, recibe un identificador y
consulta `GET /tareas/<id>`. Es deliberadamente simple —un diccionario en
memoria y un hilo por tarea— porque la aplicación corre en una sola computadora
y nunca hay más de una tarea de cada tipo. Si el servidor se reinicia las
tareas se pierden, que es lo correcto: lo que ya se escribió en la base queda.

### `web/` — sólo interfaz

Flask con plantillas Jinja2 y Bootstrap 5.3 vendorizado (sin CDN: funciona sin
internet, y no hay paso de compilación porque no hay Node). La paleta del
original se mapea a variables `--bs-*` en `cinemateca.css`, así los componentes
nativos de Bootstrap salen con el aspecto de siempre sin reescribirlos.

El tema oscuro usa `data-bs-theme="dark"` y toma los colores del prototipo
`tarjeta-cinemateca.html` que ya existía en el proyecto viejo.

### `cli/` — los scripts, como módulo

Cada comando es un archivo que registra su subparser y llama a un servicio.

## Seguridad

La aplicación lanza procesos y renombra archivos del disco, así que:

1. El servidor escucha **sólo en `127.0.0.1`**. No queda accesible desde la red
   local.
2. Todos los POST llevan token CSRF (Flask-WTF), en un `<meta>` para que los
   `fetch` lo encuentren siempre.
3. Las rutas de vídeo se validan contra la raíz de su ubicación antes de
   abrirlas.
4. El explorador de carpetas lista **sólo nombres de carpeta**, nunca contenido
   de archivos.
5. Ninguna credencial en el código: van en `.env`, que está en `.gitignore`.

## Qué se prueba

197 tests. Los que más valen:

- `nucleo/`: parseo de las tres convenciones de nombre, extracción de
  identificadores desde `.url` en UTF-16 y `.nfo` de Kodi, y la tabla de
  verdad de `clasificar()`.
- `organizador/`: renombrado con conflicto, renombrado que sólo cambia
  mayúsculas, detección de subtítulos por contenido. Todo sobre árboles de
  archivos reales en `tmp_path`.
- `reproduccion/`: que `..` y las rutas fuera de la ubicación sean rechazadas.
- `metadatos/`: enriquecimiento con respuestas de TMDb fijas, incluido el caso
  en que TMDb devuelve una ficha cuyo `imdb_id` no coincide con el pedido.
- `web/`: que cada ruta responda y que los POST sin token den 400.
