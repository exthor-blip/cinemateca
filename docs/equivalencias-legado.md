# Qué era cada cosa y en qué se convirtió

Mapa entre el proyecto original (en [`../legado/`](../legado/)) y esta versión.
Sirve para dos cosas: encontrar rápido dónde quedó una función conocida, y
entender por qué se cambió lo que se cambió.

## Las tres piezas originales

| Original | Qué era | Dónde está ahora |
|---|---|---|
| `Mi_Cinemateca_1_14.html` | 796 líneas: HTML + CSS + 600 de JS, datos en IndexedDB | `web/`, `catalogo/`, `busqueda/`, `metadatos/` |
| `IMDB linker 4.3.ps1` | 609 líneas: GUI WPF + 4 clientes HTTP + lógica de coincidencia | `metadatos/vinculador.py`, `metadatos/cliente_*.py`, `cli/vincular.py` |
| `Organizador_Peliculas.ps1` | 370 líneas: GUI WPF + renombrado + limpieza | `organizador/`, `cli/organizar.py` |
| `Mi_Cinemateca_VLC.cs` + `.exe` | protocolo propio `micinemateca-vlc:` + claves de registro | `reproduccion/` (el `.exe` y el protocolo desaparecen) |
| `Mi_Cinemateca_Puntajes_IMDb.js` | 11,7 MB de base64 con `title.ratings.tsv.gz` | tabla `puntajes_imdb`, cargada con `puntajes.py` |

## Función por función

### Del catálogo HTML

| Antes | Ahora |
|---|---|
| `getYear()`, `clean()` | `nucleo.titulos.extraer_anio()`, `limpiar_titulo()` |
| `normalizeTitle()` | `nucleo.titulos.normalizar_titulo()` |
| `titleQueries()` | `nucleo.titulos.variantes_consulta()` |
| `imdbId()`, `idFromName()` | `nucleo.identificadores.extraer_imdb_id()` y `_de_nombre()` |
| `extractImdb()` | `nucleo.identificadores.decodificar_texto()` + `extraer_imdb_de_sidecar()` |
| `groupImdbId()` | `catalogo.sidecars.buscar_imdb_id()` |
| `posterOf()` | `catalogo.sidecars.buscar_poster()` |
| `indexGroups()`, `addPicker()` | `catalogo.escaner` + `catalogo.indexador` |
| `uniqueMovies()` | `catalogo.duplicados.unicas()` |
| `refreshFilters()`, `matchesFilters()` | `busqueda.facetas` + `busqueda.consultas` |
| `apiCall()` | `metadatos.sesion_http` + `metadatos.cliente_tmdb` |
| `searchMovie()`, `findMovie()`, `fetchMovieDetails()` | `metadatos.enriquecedor` |
| `enrich()` (el lote con barra y Detener) | `servicios.servicio_metadatos.completar_lote()` + `servicios.tareas` |
| `reviewMovie()` (ventana de revisión) | `web/templates/peliculas/revision.html` + `rutas/peliculas.py` |
| `importRatings()` | `puntajes.importar()` |
| IndexedDB `mi-cinemateca-1-1` | tablas `peliculas`, `ubicaciones`, `metadatos` |
| IndexedDB `mi-cinemateca-imdb-ratings` | tabla `puntajes_imdb` |

### Del IMDB linker

| Antes | Ahora |
|---|---|
| `Parse-Folder` | `nucleo.titulos.parsear_anio_titulo()` (admite más formatos) |
| `Normalize-Title` | `nucleo.titulos.normalizar_titulo()` |
| `Remove-OriginSuffix`, `$originTags` | `nucleo.titulos.quitar_sufijo_origen()`, `ETIQUETAS_ORIGEN` |
| `Get-Candidates` | `metadatos.cliente_imdb_sugerencias` |
| `Get-WikidataCandidates` | `metadatos.cliente_wikidata` |
| `Search-Tmdb` | `metadatos.cliente_tmdb` |
| `Get-WikipediaAlternates` | `metadatos.cliente_wikipedia` |
| `Search-Imdb`, `Search-Multi` | `metadatos.vinculador` + `nucleo.coincidencias.clasificar()` |
| `Write-Result`, `Write-ExternalResult` | `metadatos.escritor_sidecars` |
| `Get-ReviewOptions` | `nucleo.coincidencias.ordenar_para_revision()` |
| `Show-CandidateReview`, `Show-ManualLastResort` | pantalla de revisión en la web |
| `.imdb_linker_estado.json` | tabla `revisiones`; se importa con `cli importar-estado` |

### Del Organizador

| Antes | Ahora |
|---|---|
| `Analyze` | `organizador.analizador.analizar()` |
| `IsSubtitleFile` | `organizador.deteccion_subtitulos` |
| `SafeRename`, `RenameCaseOnly` | `organizador.renombrador` |
| `DestinationOccupied` | `organizador.renombrador.destino_ocupado()` |
| `ConvertAllToLowercase` | `organizador.minusculas.convertir()` |
| `RecycleSelected` | `organizador.limpieza.a_papelera()` |
| `SaveReports` | `organizador.informes.guardar()` (mismo formato de CSV) |
| `IsProtected` | `organizador.analizador.esta_protegido()` |
| Las cuatro pestañas de la ventana | `web/templates/organizador/index.html` |

### Del lanzador de VLC

| Antes | Ahora |
|---|---|
| protocolo `micinemateca-vlc:` + payload base64 | ya no hace falta: el backend corre en la misma máquina |
| `HKCU\Software\Classes\micinemateca-vlc\Locations` | tabla `ubicaciones` |
| `ResolveVideo` (anti path traversal) | `reproduccion.reproductor.resolver_video()` |
| `FindVlc` | `reproduccion.localizador_vlc.localizar()` |
| `Mi_Cinemateca_VLC.exe` | se elimina |

## Errores del original que se corrigieron

1. **La verificación de año de Wikidata no existía.** El bloque
   `if($releaseYears.Count -gt 0 -and $year -notin $releaseYears){ }` de
   `IMDB linker 4.3.ps1` (líneas 147-150) tenía el cuerpo vacío: estaba
   documentada pero no hacía nada. Ahora `cliente_wikidata` compara de verdad.

2. **Los errores de red se confundían con «no está».** Todos los `catch` del
   linker devolvían vacío en silencio, así que un corte de wifi dejaba la
   película marcada como «No encontrada». Ahora cada fallo levanta
   `ErrorFuenteExterna`, y `ResultadoVinculacion.busqueda_completa` avisa si
   alguna fuente no contestó.

3. **Criterios distintos para el mismo conflicto.** El Organizador comparaba el
   destino con `-cne` (sensible a mayúsculas) en los videos sueltos y con
   `OrdinalIgnoreCase` en los pares. Ahora hay un solo criterio,
   `renombrador.misma_ruta_exacta()`.

4. **Cualquier `.txt` se renombraba como subtítulo.** `.txt` estaba en
   `$subExt`, así que la publicidad que dejan los grupos de release terminaba
   convertida en `1975 - Tiburón.txt`. Ahora `.txt` tiene que demostrar por
   contenido que es un subtítulo.

5. **Un `.nfo` con el ID de IMDb se podía mandar a la Papelera.** El
   Organizador no sabía que el catálogo lee los `.nfo`. Ahora
   `esta_protegido()` protege cualquier sidecar que contenga un identificador.

6. **Sin reintentos ni caché.** `Get-Candidates` se llamaba desde cinco lugares
   sin recordar nada: una búsqueda en Wikidata con 7 idiomas disparaba decenas
   de consultas repetidas por una sola película.

7. **El estado se perdía al mover la colección.** El JSON del linker indexaba
   por ruta absoluta. Ahora las rutas se guardan relativas a la ubicación.

8. **Consultas redundantes de puntajes.** El HTML re-descomprimía los 11,7 MB
   del `.js` cada vez que aparecían identificadores nuevos.

## Diferencias de comportamiento, a propósito

| Tema | Antes | Ahora | Por qué |
|---|---|---|---|
| Elegir carpeta | `showDirectoryPicker()` del navegador | explorador propio en `/ubicaciones` | con backend, la carpeta está en el disco del servidor y ningún navegador le pasa una ruta local a una página |
| Mostrar el catálogo | todas las tarjetas en cada tecleo | paginado, 60 por página | no se degrada con el tamaño de la colección, y la búsqueda queda en la URL |
| Reproducir | `<video>` embebido, fallaba con mkv y avi | VLC | cualquier códec |
| Dónde viven los datos | IndexedDB del navegador | SQLite en `%LOCALAPPDATA%` | no se pierden al cambiar de navegador o de perfil |
| Clave de TMDb | campo en la página, sólo durante la sesión | `.env` | no hay que volver a pegarla cada vez |
| Renombrar y limpiar | cuadro de diálogo de confirmación | simula por defecto | sin diálogo modal, que no pase nada tiene que ser lo predeterminado |
