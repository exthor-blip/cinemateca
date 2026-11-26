"""Escaneo del disco: que carpetas son una pelicula y que datos salen de ellas."""

from gestor_peliculas.catalogo import escaner


def peliculas_por_carpeta(raiz):
    return {p.ruta_relativa: p for p in escaner.escanear(raiz, nombre_ubicacion="Peliculas")}


def test_solo_las_carpetas_con_video_son_peliculas(coleccion):
    encontradas = peliculas_por_carpeta(coleccion)
    assert "1975 - Tiburon" in encontradas
    assert "1972 - El Padrino" in encontradas
    assert "1994 - Pulp Fiction" in encontradas
    # Una carpeta sin video no es una pelicula.
    assert "_Notas" not in encontradas


def test_lee_titulo_anio_poster_y_subtitulo(coleccion):
    pelicula = peliculas_por_carpeta(coleccion)["1975 - Tiburon"]
    assert pelicula.titulo == "Tiburon"
    assert pelicula.anio == "1975"
    assert pelicula.archivo_video == "1975 - Tiburon.mkv"
    assert pelicula.poster == "poster.jpg"
    assert pelicula.subtitulos == ["1975 - Tiburon.srt"]
    assert pelicula.tamanio_bytes == 2048


def test_lee_el_imdb_del_acceso_directo_que_escribe_el_linker(coleccion):
    """El contrato con IMDB linker 4.3.ps1: imdb.url dentro de la carpeta."""
    assert peliculas_por_carpeta(coleccion)["1975 - Tiburon"].imdb_id == "tt0073195"


def test_lee_el_imdb_de_un_nfo_de_kodi(coleccion):
    pelicula = peliculas_por_carpeta(coleccion)["1994 - Pulp Fiction"]
    assert pelicula.imdb_id == "tt0110912"
    assert pelicula.poster == "poster.png"


def test_lee_el_imdb_del_nombre_del_archivo(coleccion):
    pelicula = peliculas_por_carpeta(coleccion)["The.Matrix.1999.1080p"]
    assert pelicula.imdb_id == "tt0133093"
    assert pelicula.titulo == "The Matrix"
    assert pelicula.anio == "1999"


def test_sin_sidecar_el_imdb_queda_vacio(coleccion):
    pelicula = peliculas_por_carpeta(coleccion)["1972 - El Padrino"]
    assert pelicula.imdb_id == ""
    assert pelicula.poster == ""


def test_un_nfo_sin_identificador_no_inventa_nada(coleccion):
    pelicula = peliculas_por_carpeta(coleccion)["1988 - Mi vecino Totoro (Japon)"]
    assert pelicula.imdb_id == ""
    assert pelicula.titulo == "Mi vecino Totoro"


def test_carpeta_con_dos_videos_se_marca_ambigua(coleccion):
    pelicula = peliculas_por_carpeta(coleccion)["2000 - Ambigua"]
    assert pelicula.varios_videos is True


def test_se_ignoran_las_carpetas_de_sistema_y_las_ocultas(coleccion):
    (coleccion / "1975 - Tiburon" / "Subs").mkdir()
    (coleccion / "1975 - Tiburon" / "Subs" / "extra.mkv").write_bytes(b"\x00")
    (coleccion / ".oculta").mkdir()
    (coleccion / ".oculta" / "pelicula.mkv").write_bytes(b"\x00")

    rutas = set(peliculas_por_carpeta(coleccion))
    assert "1975 - Tiburon/Subs" not in rutas
    assert ".oculta" not in rutas


def test_el_progreso_informa_y_la_cancelacion_corta(coleccion):
    avisos = []
    consumidas = []
    for pelicula in escaner.escanear(
        coleccion, cancelado=lambda: len(consumidas) >= 2,
        progreso=lambda n, nombre: avisos.append(n),
    ):
        consumidas.append(pelicula)
    assert len(consumidas) <= 3
    assert avisos  # el aviso final siempre se emite


def test_raiz_inexistente_no_lanza(tmp_path):
    assert list(escaner.escanear(tmp_path / "no-existe")) == []
