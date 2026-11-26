# Gestor de Películas

Catálogo, organización y reproducción de una colección local de películas, para
Windows. Es la reescritura en Python de tres herramientas que antes iban por
separado: el catálogo `Mi_Cinemateca.html`, el `IMDB linker` y el
`Organizador de Películas`. Los originales quedan en [`legado/`](legado/) como
referencia.

## Qué hace

- **Catálogo**: recorre tus carpetas de películas y arma un índice con póster,
  título, año, país, género, idioma, duración, dirección y puntaje de IMDb.
- **Búsqueda**: por título (también el original, así «Jaws» encuentra
  «Tiburón»), por año y por los cuatro filtros de siempre. Cada búsqueda queda
  en la URL, así que se puede guardar en favoritos.
- **Metadatos**: completa las fichas desde TMDb. Lo que no es seguro no se
  guarda solo: queda marcado para que lo confirmes vos.
- **Reproducción**: abre el archivo original en VLC, con cualquier códec.
- **Organizador**: renombra el vídeo y los subtítulos al nombre de su carpeta,
  pasa todo a minúsculas y manda los archivos sobrantes a la Papelera.
- **Vinculador**: busca el identificador de IMDb de cada carpeta en IMDb,
  Wikidata, TMDb y Wikipedia, y deja el `imdb.url` y el `poster.jpg` que lee el
  catálogo.

## Instalación

Hace falta Python 3.12 o posterior y, para reproducir, VLC.

```powershell
py -m pip install -e .
```

Después, copiá `.env.example` como `.env` y pegá tu clave de TMDb:

```powershell
copy .env.example .env
```

```
TMDB_TOKEN=tu_clave_o_token_aca
```

Sirve tanto el token de lectura v4 (empieza con `eyJ`) como la clave v3. Se
obtiene en <https://www.themoviedb.org/settings/api>. Sin clave la aplicación
funciona igual: no completa fichas automáticamente, pero podés pegar enlaces de
IMDb a mano.

## Uso

Doble clic en `iniciar_app.bat`, o desde la consola:

```powershell
py -m gestor_peliculas.cli servir --abrir-navegador
```

Se abre en <http://127.0.0.1:5000/>. El servidor escucha sólo en esta
computadora.

### Comandos de consola

```powershell
py -m gestor_peliculas.cli estado
```

```powershell
py -m gestor_peliculas.cli indexar "D:\Peliculas"
```

```powershell
py -m gestor_peliculas.cli enriquecer --limite 50
```

```powershell
py -m gestor_peliculas.cli organizar "D:\Peliculas" --renombrar-pares
```

```powershell
py -m gestor_peliculas.cli vincular --limite 20
```

```powershell
py -m gestor_peliculas.cli importar-puntajes --descargar
```

**`organizar` y `vincular` simulan por defecto.** Muestran lo que harían y no
tocan nada. Para que escriban de verdad hay que agregar `--escribir`.

## Dónde se guardan los datos

En `%LOCALAPPDATA%\GestorPeliculas`:

| Archivo | Qué es |
|---|---|
| `cinemateca.db` | el catálogo (SQLite) |
| `miniaturas/` | pósters redimensionados para la grilla |
| `registros/gestor.log` | el registro de la aplicación |

No está dentro del proyecto a propósito: el proyecto vive en OneDrive y una base
SQLite en una carpeta que se sincroniza se corrompe o se queda bloqueada. Se
puede cambiar con `GESTOR_DATOS_DIR` en el `.env`.

**Tus videos y pósters nunca se copian ni se modifican**, salvo que pidas
explícitamente un renombrado o una limpieza desde el Organizador.

## Viniendo de la versión anterior

No hay nada que migrar: indexá tus carpetas y listo. El catálogo lee los
`imdb.url` y `poster.jpg` que dejó el IMDB linker, así que una colección ya
procesada aparece completa desde el primer indexado.

Lo único que conviene importar es el estado del linker, que guarda qué
candidatos descartaste a mano:

```powershell
py -m gestor_peliculas.cli importar-estado "D:\Peliculas\.imdb_linker_estado.json"
```

Los puntajes ya no viajan en un `.js` de 11,7 MB: se importan una vez a la base
con `importar-puntajes` y después las consultas son instantáneas.

## Desarrollo

```powershell
py -m pip install -e ".[dev]"
```

```powershell
py -m pytest
```

```powershell
py -m ruff check .
```

La arquitectura está explicada en [`docs/arquitectura.md`](docs/arquitectura.md),
y qué parte del proyecto viejo se convirtió en qué, en
[`docs/equivalencias-legado.md`](docs/equivalencias-legado.md).

## Créditos

Este producto utiliza la API de TMDb, pero no está avalado ni certificado por
TMDb. Metadatos: [The Movie Database](https://www.themoviedb.org/).
Puntajes: [IMDb Non-Commercial Datasets](https://developer.imdb.com/non-commercial-datasets/).
