-- Esquema del Gestor de Peliculas.
-- Se aplica completo sobre una base vacia; las migraciones posteriores viven
-- en bd.py y se identifican por user_version.

CREATE TABLE IF NOT EXISTS ubicaciones (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre         TEXT NOT NULL,
    ruta           TEXT NOT NULL UNIQUE,
    agregada_en    TEXT NOT NULL,
    ultimo_escaneo TEXT
);

-- Una fila por carpeta con exactamente un video.
-- ruta_relativa es relativa a la ubicacion, nunca absoluta: asi mover el disco
-- de peliculas no invalida el catalogo. El .imdb_linker_estado.json original
-- indexaba por ruta absoluta y se perdia entero al renombrar la raiz.
CREATE TABLE IF NOT EXISTS peliculas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ubicacion_id    INTEGER NOT NULL REFERENCES ubicaciones(id) ON DELETE CASCADE,
    ruta_relativa   TEXT NOT NULL,
    archivo_video   TEXT NOT NULL,
    titulo_carpeta  TEXT NOT NULL,
    anio_carpeta    TEXT NOT NULL DEFAULT '',
    imdb_id         TEXT NOT NULL DEFAULT '',
    poster_relativo TEXT NOT NULL DEFAULT '',
    tamanio_bytes   INTEGER NOT NULL DEFAULT 0,
    visto_en        TEXT
);

-- La identidad de una pelicula es (ubicacion, carpeta, archivo de video), no
-- solo la carpeta: una carpeta de saga puede tener varios videos, cada uno una
-- pelicula distinta. Va como indice con nombre y no como UNIQUE en linea para
-- poder cambiarlo sin reconstruir la tabla.
CREATE UNIQUE INDEX IF NOT EXISTS idx_peliculas_identidad
    ON peliculas(ubicacion_id, ruta_relativa, archivo_video);

CREATE INDEX IF NOT EXISTS idx_peliculas_imdb      ON peliculas(imdb_id) WHERE imdb_id <> '';
CREATE INDEX IF NOT EXISTS idx_peliculas_ubicacion ON peliculas(ubicacion_id);
CREATE INDEX IF NOT EXISTS idx_peliculas_anio      ON peliculas(anio_carpeta);

CREATE TABLE IF NOT EXISTS metadatos (
    pelicula_id         INTEGER PRIMARY KEY REFERENCES peliculas(id) ON DELETE CASCADE,
    tmdb_id             INTEGER,
    titulo              TEXT NOT NULL DEFAULT '',
    titulo_original     TEXT NOT NULL DEFAULT '',
    anio                TEXT NOT NULL DEFAULT '',
    director            TEXT NOT NULL DEFAULT '',
    duracion_min        INTEGER,
    sinopsis            TEXT NOT NULL DEFAULT '',
    idiomas_verificados INTEGER NOT NULL DEFAULT 0,
    actualizado_en      TEXT NOT NULL DEFAULT ''
);

-- Pais / genero / idioma normalizados. Los <select> de filtros salen de aca
-- con una consulta, en lugar de recorrer todo el catalogo en memoria como
-- hacia refreshFilters() en el HTML.
CREATE TABLE IF NOT EXISTS etiquetas (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo  TEXT NOT NULL CHECK (tipo IN ('pais', 'genero', 'idioma')),
    valor TEXT NOT NULL,
    UNIQUE (tipo, valor)
);

CREATE TABLE IF NOT EXISTS pelicula_etiquetas (
    pelicula_id INTEGER NOT NULL REFERENCES peliculas(id) ON DELETE CASCADE,
    etiqueta_id INTEGER NOT NULL REFERENCES etiquetas(id) ON DELETE CASCADE,
    PRIMARY KEY (pelicula_id, etiqueta_id)
);

CREATE INDEX IF NOT EXISTS idx_pel_etiq_etiqueta ON pelicula_etiquetas(etiqueta_id);

-- Dataset no comercial de IMDb (title.ratings.tsv.gz), importado completo.
-- Reemplaza los 11,7 MB de base64 que el HTML descomprimia en el navegador.
CREATE TABLE IF NOT EXISTS puntajes_imdb (
    imdb_id TEXT PRIMARY KEY,
    puntaje REAL NOT NULL,
    votos   INTEGER NOT NULL
);

-- Estado del enlazado. Reemplaza .imdb_linker_estado.json, incluidos los
-- candidatos que la persona rechazo para no volver a ofrecerlos.
CREATE TABLE IF NOT EXISTS revisiones (
    pelicula_id            INTEGER PRIMARY KEY REFERENCES peliculas(id) ON DELETE CASCADE,
    estado                 TEXT NOT NULL DEFAULT 'pendiente',
    detalle                TEXT NOT NULL DEFAULT '',
    candidato_id           TEXT NOT NULL DEFAULT '',
    candidato_titulo       TEXT NOT NULL DEFAULT '',
    candidato_anio         TEXT NOT NULL DEFAULT '',
    candidato_poster       TEXT NOT NULL DEFAULT '',
    candidatos_rechazados  TEXT NOT NULL DEFAULT '[]',
    actualizado_en         TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_revisiones_estado ON revisiones(estado);

-- Busqueda de texto. Es una tabla FTS5 normal (no contentless) para poder
-- hacer DELETE y UPDATE corrientes: los titulos vienen de dos tablas
-- (peliculas.titulo_carpeta y metadatos.titulo), asi que la sincroniza
-- repositorio_peliculas._sincronizar_fts en lugar de un trigger.
CREATE VIRTUAL TABLE IF NOT EXISTS peliculas_fts USING fts5(
    pelicula_id UNINDEXED,
    titulo,
    titulo_original,
    ruta,
    tokenize="unicode61 remove_diacritics 2"
);
