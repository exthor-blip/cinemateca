"""Agrupado de copias: la misma pelicula en dos carpetas o dos discos."""

from gestor_peliculas.catalogo import duplicados
from gestor_peliculas.modelos import Metadatos, Pelicula


def peli(**campos) -> Pelicula:
    base = dict(
        id=1, ubicacion_id=1, ruta_relativa="carpeta", archivo_video="v.mkv",
        titulo_carpeta="Pelicula", tamanio_bytes=1000,
    )
    base.update(campos)
    return Pelicula(**base)


def test_el_imdb_manda_sobre_la_ruta():
    """Dos carpetas distintas con el mismo IMDb son la misma pelicula."""
    una = peli(id=1, ruta_relativa="1975 - Tiburon", imdb_id="tt0073195")
    otra = peli(id=2, ruta_relativa="Jaws (1975)", imdb_id="tt0073195")
    assert duplicados.clave_identidad(una) == duplicados.clave_identidad(otra)
    assert len(duplicados.unicas([una, otra])) == 1


def test_sin_imdb_se_compara_por_archivo_y_tamanio():
    una = peli(id=1, ruta_relativa="disco1", archivo_video="peli.mkv", tamanio_bytes=5000)
    otra = peli(id=2, ruta_relativa="disco2", archivo_video="peli.mkv", tamanio_bytes=5000)
    distinta = peli(id=3, ruta_relativa="disco3", archivo_video="peli.mkv", tamanio_bytes=9999)

    grupos = duplicados.agrupar([una, otra, distinta])
    assert len(grupos) == 2


def test_se_queda_con_la_copia_mas_completa():
    """La que tiene ficha gana; si empatan, la que tiene poster; luego el tamanio."""
    pelada = peli(id=1, imdb_id="tt1", ruta_relativa="a")
    con_poster = peli(id=2, imdb_id="tt1", ruta_relativa="b", poster_relativo="poster.jpg")
    con_ficha = peli(id=3, imdb_id="tt1", ruta_relativa="c",
                     metadatos=Metadatos(titulo="Con ficha", idiomas_verificados=True))

    elegida = duplicados.unicas([pelada, con_poster, con_ficha])
    assert len(elegida) == 1
    assert elegida[0].id == 3


def test_contar_duplicadas():
    peliculas = [
        peli(id=1, imdb_id="tt1"), peli(id=2, imdb_id="tt1"),
        peli(id=3, imdb_id="tt2"),
    ]
    assert duplicados.contar_duplicadas(peliculas) == 1


def test_copias_de_excluye_la_propia():
    una = peli(id=1, imdb_id="tt1")
    otra = peli(id=2, imdb_id="tt1")
    ajena = peli(id=3, imdb_id="tt2")
    assert [c.id for c in duplicados.copias_de(una, [una, otra, ajena])] == [2]


def test_ninguna_copia_se_pierde_del_catalogo():
    """Las dos copias siguen existiendo: solo se muestran agrupadas."""
    una = peli(id=1, imdb_id="tt1", ruta_relativa="disco-a")
    otra = peli(id=2, imdb_id="tt1", ruta_relativa="disco-b")
    grupos = duplicados.agrupar([una, otra])
    assert sum(len(copias) for copias in grupos.values()) == 2
