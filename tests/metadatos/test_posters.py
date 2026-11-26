"""Miniaturas de poster: rapidez y archivos problematicos."""

import pytest
from PIL import Image

from gestor_peliculas.errores import ErrorFuenteExterna
from gestor_peliculas.metadatos import posters

JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


def crear_jpeg(ruta, tamanio=(948, 1400)):
    Image.new("RGB", tamanio, (40, 60, 90)).save(ruta, "JPEG", quality=90)
    return ruta


def test_genera_la_miniatura_al_ancho_pedido(tmp_path):
    origen = crear_jpeg(tmp_path / "poster.jpg")
    cache = tmp_path / "cache"

    destino = posters.miniatura(origen, cache)

    assert destino is not None and destino.is_file()
    with Image.open(destino) as imagen:
        assert imagen.width == posters.ANCHO_MINIATURA
        # Se conserva la proporcion del original.
        assert abs(imagen.height / imagen.width - 1400 / 948) < 0.02


def test_reutiliza_la_miniatura_ya_generada(tmp_path):
    origen = crear_jpeg(tmp_path / "poster.jpg")
    cache = tmp_path / "cache"

    primera = posters.miniatura(origen, cache)
    marca = primera.stat().st_mtime_ns
    segunda = posters.miniatura(origen, cache)

    assert segunda == primera
    assert segunda.stat().st_mtime_ns == marca


def test_se_regenera_si_cambia_el_original(tmp_path):
    origen = crear_jpeg(tmp_path / "poster.jpg")
    cache = tmp_path / "cache"
    primera = posters.miniatura(origen, cache)

    crear_jpeg(origen, (600, 900))
    segunda = posters.miniatura(origen, cache)

    assert segunda != primera


def test_un_poster_enorme_no_rompe(tmp_path):
    """En la coleccion real hay posters de mas de 100 megapixeles."""
    origen = crear_jpeg(tmp_path / "poster.jpg", (6000, 9000))
    destino = posters.miniatura(origen, tmp_path / "cache")

    assert destino is not None
    with Image.open(destino) as imagen:
        assert imagen.width == posters.ANCHO_MINIATURA


def test_un_archivo_que_no_es_imagen_devuelve_none(tmp_path):
    roto = tmp_path / "poster.jpg"
    roto.write_bytes(b"esto no es una imagen")
    assert posters.miniatura(roto, tmp_path / "cache") is None


def test_un_archivo_que_no_existe_devuelve_none(tmp_path):
    assert posters.miniatura(tmp_path / "no-existe.jpg", tmp_path / "cache") is None


def test_valida_el_formato_por_bytes_magicos():
    assert posters.formato_de(JPEG + b"\x00" * 12) == "jpg"
    assert posters.formato_de(b"\x89PNG\r\n\x1a\n" + b"\x00" * 12) == "png"
    assert posters.formato_de(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 4) == "webp"
    assert posters.formato_de(b"no soy una imagen") == ""
    assert posters.es_jpeg(JPEG)
    assert not posters.es_jpeg(b"\x89PNG")


def test_no_sobrescribe_un_poster_existente(tmp_path):
    carpeta = tmp_path / "pelicula"
    carpeta.mkdir()
    (carpeta / "poster.jpg").write_bytes(b"el que ya estaba")

    posters.guardar_poster(JPEG, carpeta)

    assert (carpeta / "poster.jpg").read_bytes() == b"el que ya estaba"


def test_no_guarda_algo_que_no_es_imagen(tmp_path):
    carpeta = tmp_path / "pelicula"
    carpeta.mkdir()
    with pytest.raises(ErrorFuenteExterna):
        posters.guardar_poster(b"<html>404</html>", carpeta)
    assert not (carpeta / "poster.jpg").exists()
    # Y no deja temporales tirados.
    assert list(carpeta.iterdir()) == []
