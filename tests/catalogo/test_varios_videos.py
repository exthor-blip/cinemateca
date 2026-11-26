"""Carpetas con varios videos: cada uno es una pelicula.

Es el caso de las carpetas de saga ("- shrek" con los cuatro videos adentro) y
el de una carpeta con videos sueltos. El proyecto original se quedaba con uno
solo por carpeta y perdia el resto: sobre la coleccion real del usuario eso
significaba 259 peliculas invisibles de 688.
"""

import pytest

from gestor_peliculas.catalogo import escaner, indexador

ACCESO = "[InternetShortcut]\r\nURL=https://www.imdb.com/title/{}/\r\n"
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


@pytest.fixture()
def saga(tmp_path):
    """Una carpeta de saga como las de la coleccion real."""
    carpeta = tmp_path / "Peliculas" / "- shrek"
    carpeta.mkdir(parents=True)
    for nombre, anio in [("shrek 1", "2001"), ("shrek 2", "2004"), ("shrek 3", "2007")]:
        (carpeta / f"{nombre} - {anio}.mkv").write_bytes(b"\x00" * 100)
    return tmp_path / "Peliculas"


def encontradas(raiz):
    return {p.archivo_video: p for p in escaner.escanear(raiz, nombre_ubicacion="Peliculas")}


def test_cada_video_de_la_saga_es_una_pelicula(saga):
    peliculas = encontradas(saga)
    assert len(peliculas) == 3
    assert set(peliculas) == {
        "shrek 1 - 2001.mkv", "shrek 2 - 2004.mkv", "shrek 3 - 2007.mkv",
    }


def test_cada_una_toma_su_titulo_y_anio_del_archivo(saga):
    peliculas = encontradas(saga)
    primera = peliculas["shrek 1 - 2001.mkv"]
    tercera = peliculas["shrek 3 - 2007.mkv"]

    assert (primera.titulo, primera.anio) == ("shrek 1", "2001")
    assert (tercera.titulo, tercera.anio) == ("shrek 3", "2007")
    assert primera.varios_videos


def test_videos_sueltos_en_la_raiz_de_la_ubicacion(tmp_path):
    """El caso de la carpeta "coreanas": 15 .mkv sueltos, sin subcarpetas."""
    raiz = tmp_path / "coreanas"
    raiz.mkdir()
    for nombre in ("AP245PA.mkv", "CP278PC.mkv", "EP660PE.mkv"):
        (raiz / nombre).write_bytes(b"\x00" * 50)

    peliculas = encontradas(raiz)
    assert len(peliculas) == 3
    assert peliculas["AP245PA.mkv"].titulo == "AP245PA"


def test_una_carpeta_con_un_solo_video_no_cambia(coleccion):
    """La convencion de siempre: el titulo sale del nombre de la carpeta."""
    peliculas = encontradas(coleccion)
    tiburon = peliculas["1975 - Tiburon.mkv"]

    assert tiburon.titulo == "Tiburon"
    assert tiburon.anio == "1975"
    assert tiburon.imdb_id == "tt0073195"
    assert tiburon.poster == "poster.jpg"
    assert not tiburon.varios_videos


def test_un_sidecar_suelto_no_se_reparte_entre_varias(saga):
    """Un solo imdb.url no puede describir tres peliculas: no se usa para ninguna."""
    (saga / "- shrek" / "imdb.url").write_text(ACCESO.format("tt0126029"),
                                               encoding="ascii", newline="")
    (saga / "- shrek" / "poster.jpg").write_bytes(JPEG)

    peliculas = encontradas(saga)
    assert all(p.imdb_id == "" for p in peliculas.values())
    assert all(p.poster == "" for p in peliculas.values())


def test_un_sidecar_con_el_nombre_del_video_si_se_usa(saga):
    """Si el sidecar se llama como el video, es inequivoco a cual pertenece."""
    carpeta = saga / "- shrek"
    (carpeta / "shrek 2 - 2004.url").write_text(ACCESO.format("tt0298148"),
                                                encoding="ascii", newline="")
    (carpeta / "shrek 2 - 2004.jpg").write_bytes(JPEG)

    peliculas = encontradas(saga)
    assert peliculas["shrek 2 - 2004.mkv"].imdb_id == "tt0298148"
    assert peliculas["shrek 2 - 2004.mkv"].poster == "shrek 2 - 2004.jpg"
    assert peliculas["shrek 1 - 2001.mkv"].imdb_id == ""


def test_el_id_en_el_nombre_del_archivo_se_sigue_leyendo(tmp_path):
    carpeta = tmp_path / "Peliculas" / "varias"
    carpeta.mkdir(parents=True)
    (carpeta / "una [tt0073195].mkv").write_bytes(b"\x00")
    (carpeta / "otra [tt0068646].mkv").write_bytes(b"\x00")

    peliculas = encontradas(tmp_path / "Peliculas")
    assert peliculas["una [tt0073195].mkv"].imdb_id == "tt0073195"
    assert peliculas["otra [tt0068646].mkv"].imdb_id == "tt0068646"


def test_cada_video_se_queda_con_su_subtitulo(saga):
    carpeta = saga / "- shrek"
    (carpeta / "shrek 1 - 2001.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nx\n")
    (carpeta / "shrek 2 - 2004.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\ny\n")

    peliculas = encontradas(saga)
    assert peliculas["shrek 1 - 2001.mkv"].subtitulos == ["shrek 1 - 2001.srt"]
    assert peliculas["shrek 2 - 2004.mkv"].subtitulos == ["shrek 2 - 2004.srt"]
    assert peliculas["shrek 3 - 2007.mkv"].subtitulos == []


def test_se_indexan_y_el_reindexado_no_duplica(bd, saga):
    ubicacion, primero = indexador.indexar_carpeta(bd, saga, nombre="Peliculas")
    assert primero.peliculas_nuevas == 3
    assert primero.en_carpeta_compartida == 3

    _, segundo = indexador.indexar_carpeta(bd, saga, nombre="Peliculas")
    assert segundo.peliculas_nuevas == 0
    assert bd.peliculas.contar() == 3


def test_borrar_un_video_de_la_saga_da_de_baja_solo_ese(bd, saga):
    ubicacion, _ = indexador.indexar_carpeta(bd, saga, nombre="Peliculas")
    (saga / "- shrek" / "shrek 2 - 2004.mkv").unlink()

    resumen = indexador.indexar_ubicacion(bd, ubicacion)

    assert resumen.peliculas_eliminadas == 1
    assert bd.peliculas.contar() == 2
    assert bd.peliculas.obtener_por_ruta(ubicacion.id, "- shrek", "shrek 1 - 2001.mkv")
    assert bd.peliculas.obtener_por_ruta(ubicacion.id, "- shrek", "shrek 2 - 2004.mkv") is None


def test_se_pueden_pedir_por_archivo(bd, saga):
    ubicacion, _ = indexador.indexar_carpeta(bd, saga, nombre="Peliculas")
    tercera = bd.peliculas.obtener_por_ruta(ubicacion.id, "- shrek", "shrek 3 - 2007.mkv")
    assert tercera.titulo_carpeta == "shrek 3"
    assert tercera.video_absoluto.name == "shrek 3 - 2007.mkv"


def test_un_video_suelto_en_la_raiz_usa_su_nombre_de_archivo(tmp_path):
    """La raiz de una ubicacion es la coleccion, no la carpeta de una pelicula.

    Sin esto, un video suelto en la raiz se titulaba con el nombre de la
    ubicacion: el "@ heroes.mkv" de la coleccion real quedaba como "# HEROES".
    """
    raiz = tmp_path / "# HEROES"
    raiz.mkdir()
    (raiz / "1989 - batman.mkv").write_bytes(b"\x00")

    peliculas = {p.archivo_video: p for p in
                 escaner.escanear(raiz, nombre_ubicacion="# HEROES")}

    assert peliculas["1989 - batman.mkv"].titulo == "batman"
    assert peliculas["1989 - batman.mkv"].anio == "1989"
