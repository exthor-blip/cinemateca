"""Extraccion de identificadores IMDb desde URLs, nombres de archivo y sidecars."""

import pytest

from gestor_peliculas.nucleo import identificadores as ident


@pytest.mark.parametrize(("texto", "esperado"), [
    ("https://www.imdb.com/title/tt0073195/", "tt0073195"),
    ("https://www.imdb.com/es/title/tt1442519/?ref_=nv_sr_1", "tt1442519"),
    ("//m.imdb.com/title/tt12345678", "tt12345678"),
    ("http://akas.imdb.com/title/tt0068646/", "tt0068646"),
    ("tt0073195", "tt0073195"),
    ("TT0073195", "tt0073195"),
    ('<movie><uniqueid type="imdb">tt0110912</uniqueid></movie>', "tt0110912"),
    ("<imdbid>tt0110912</imdbid>", "tt0110912"),
    ("no hay nada aca", ""),
    ("tt123", ""),                     # los identificadores tienen 7 digitos o mas
    ("", ""),
])
def test_extraer_imdb_id(texto, esperado):
    assert ident.extraer_imdb_id(texto) == esperado


def test_extraer_de_nombre_de_archivo():
    assert ident.extraer_imdb_id_de_nombre("Tiburon [tt0073195].mkv") == "tt0073195"
    assert ident.extraer_imdb_id_de_nombre("pelicula.mkv") == ""


def test_sidecar_en_utf16_con_bom():
    """Los accesos directos de Windows pueden venir en UTF-16: es un caso real."""
    contenido = "[InternetShortcut]\r\nURL=https://www.imdb.com/title/tt0073195/\r\n"
    assert ident.extraer_imdb_de_sidecar(b"\xff\xfe" + contenido.encode("utf-16-le")) == "tt0073195"
    assert ident.extraer_imdb_de_sidecar(b"\xfe\xff" + contenido.encode("utf-16-be")) == "tt0073195"
    assert ident.extraer_imdb_de_sidecar(contenido.encode("ascii")) == "tt0073195"


def test_sidecar_con_entidades_html():
    datos = b'<a href="https://www.imdb.com&#x2F;title&#x2F;tt0073195&#x2F;">ficha</a>'
    assert ident.extraer_imdb_de_sidecar(datos) == "tt0073195"


def test_sidecar_ilegible_no_lanza():
    assert ident.extraer_imdb_de_sidecar(b"\x00\x01\x02\xff\xfe\xfd") == ""
    assert ident.extraer_imdb_de_sidecar(b"") == ""


def test_enlaces_canonicos():
    assert ident.enlace_imdb("TT0073195") == "https://www.imdb.com/title/tt0073195/"
    assert ident.enlace_imdb("basura") == ""
    assert ident.enlace_tmdb(578) == "https://www.themoviedb.org/movie/578"
    assert ident.enlace_tmdb(None) == ""


def test_tmdb_desde_url():
    assert ident.extraer_tmdb_id("https://www.themoviedb.org/movie/578") == 578
    assert ident.extraer_tmdb_id("https://www.themoviedb.org/tv/1399") is None
