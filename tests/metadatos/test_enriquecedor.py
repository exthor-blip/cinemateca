"""Enriquecimiento con TMDb, contra respuestas fijas.

No se toca la red: se reemplaza la sesion HTTP por una que devuelve fichas
preparadas. Asi se puede probar lo importante, que es cuando el enriquecedor
guarda solo y cuando manda a revision.
"""

import pytest

from gestor_peliculas.errores import ErrorFuenteExterna, RequiereRevision
from gestor_peliculas.metadatos.cliente_tmdb import ClienteTmdb
from gestor_peliculas.metadatos.enriquecedor import Enriquecedor
from gestor_peliculas.modelos import Pelicula

FICHA_TIBURON = {
    "id": 578, "imdb_id": "tt0073195", "title": "Tiburon", "original_title": "Jaws",
    "release_date": "1975-06-20", "runtime": 124,
    "overview": "Un tiburon blanco aterroriza un pueblo costero.",
    "original_language": "en",
    "production_countries": [{"iso_3166_1": "US", "name": "United States of America"}],
    "genres": [{"id": 27, "name": "Terror"}, {"id": 12, "name": "Aventura"}],
    "spoken_languages": [{"iso_639_1": "en", "english_name": "English"}],
    "credits": {"crew": [
        {"job": "Director", "name": "Steven Spielberg"},
        {"job": "Editor", "name": "Verna Fields"},
    ]},
}

RESULTADO_BUSQUEDA = {
    "id": 578, "title": "Tiburon", "original_title": "Jaws",
    "release_date": "1975-06-20", "poster_path": "/abc123.jpg",
}


class SesionFalsa:
    """Devuelve respuestas preparadas y anota que se pidio."""

    def __init__(self, respuestas: dict, fallo: Exception | None = None) -> None:
        self.respuestas = respuestas
        self.fallo = fallo
        self.pedidos: list[str] = []

    def obtener_json(self, url, *, fuente, params=None, headers=None,
                     cancelado=None, usar_cache=True):
        camino = url.split("/3/", 1)[-1]
        self.pedidos.append(camino)
        if self.fallo:
            raise self.fallo
        for clave, valor in self.respuestas.items():
            if camino.startswith(clave):
                return valor
        return {"results": [], "total_pages": 1}


def enriquecedor_con(respuestas, fallo=None) -> Enriquecedor:
    cliente = ClienteTmdb("0123456789abcdef0123456789abcdef",
                          sesion=SesionFalsa(respuestas, fallo))
    return Enriquecedor(cliente)


def peli(**campos) -> Pelicula:
    base = dict(id=1, ubicacion_id=1, ruta_relativa="1975 - Tiburon",
                archivo_video="v.mkv", titulo_carpeta="Tiburon", anio_carpeta="1975")
    base.update(campos)
    return Pelicula(**base)


def test_con_imdb_va_directo_a_la_ficha():
    """Si la carpeta ya tiene imdb.url, no hay nada que adivinar."""
    enriquecedor = enriquecedor_con({
        "find/tt0073195": {"movie_results": [{"id": 578}]},
        "movie/578": FICHA_TIBURON,
    })

    encontrada = enriquecedor.enriquecer(peli(imdb_id="tt0073195"))

    assert encontrada.imdb_id == "tt0073195"
    assert encontrada.metadatos.titulo == "Tiburon"
    assert encontrada.metadatos.titulo_original == "Jaws"
    assert encontrada.metadatos.director == "Steven Spielberg"
    assert encontrada.metadatos.duracion_min == 124
    assert encontrada.metadatos.paises == ["Estados Unidos"]
    assert encontrada.metadatos.idiomas == ["ingles"]
    assert encontrada.metadatos.idiomas_verificados


def test_una_sola_coincidencia_de_titulo_y_anio_se_guarda_sola():
    enriquecedor = enriquecedor_con({
        "search/movie": {"results": [RESULTADO_BUSQUEDA], "total_pages": 1},
        "movie/578/external_ids": {"imdb_id": "tt0073195"},
        "movie/578": FICHA_TIBURON,
    })

    encontrada = enriquecedor.enriquecer(peli())

    assert encontrada.metadatos.titulo == "Tiburon"
    assert encontrada.imdb_id == "tt0073195"


def test_dos_coincidencias_van_a_revision():
    otra = {**RESULTADO_BUSQUEDA, "id": 999, "title": "Tiburon"}
    enriquecedor = enriquecedor_con({
        "search/movie": {"results": [RESULTADO_BUSQUEDA, otra], "total_pages": 1},
        "movie/578/alternative_titles": {"titles": []},
        "movie/999/alternative_titles": {"titles": []},
    })

    with pytest.raises(RequiereRevision) as fallo:
        enriquecedor.enriquecer(peli())
    assert len(fallo.value.candidatos) == 2


def test_sin_resultados_va_a_revision():
    enriquecedor = enriquecedor_con({"search/movie": {"results": [], "total_pages": 1}})
    with pytest.raises(RequiereRevision, match="no devolvio"):
        enriquecedor.enriquecer(peli())


def test_sin_anio_no_se_busca():
    """Titulo solo da demasiados falsos positivos: decide la persona."""
    enriquecedor = enriquecedor_con({})
    with pytest.raises(RequiereRevision, match="titulo y anio"):
        enriquecedor.enriquecer(peli(anio_carpeta=""))


def test_un_titulo_demasiado_generico_va_a_revision():
    enriquecedor = enriquecedor_con({
        "search/movie": {"results": [RESULTADO_BUSQUEDA], "total_pages": 40},
    })
    with pytest.raises(RequiereRevision, match="generico"):
        enriquecedor.enriquecer(peli())


def test_encuentra_por_titulo_alternativo():
    """Carpeta "Tiburon", ficha "Jaws": solo coinciden por los alias."""
    jaws = {"id": 578, "title": "Jaws", "original_title": "Jaws",
            "release_date": "1975-06-20", "poster_path": "/abc.jpg"}
    enriquecedor = enriquecedor_con({
        "search/movie": {"results": [jaws], "total_pages": 1},
        "movie/578/alternative_titles": {"titles": [{"title": "Tiburon"}]},
        "movie/578/external_ids": {"imdb_id": "tt0073195"},
        "movie/578": FICHA_TIBURON,
    })

    encontrada = enriquecedor.enriquecer(peli())
    assert encontrada.imdb_id == "tt0073195"


def test_no_acepta_una_ficha_de_otro_imdb():
    """Salvaguarda del original: la ficha devuelta tiene que ser la pedida."""
    enriquecedor = enriquecedor_con({
        "find/tt0073195": {"movie_results": [{"id": 578}]},
        "movie/578": {**FICHA_TIBURON, "imdb_id": "tt9999999"},
    })

    with pytest.raises(ErrorFuenteExterna, match="no coincide"):
        enriquecedor.enriquecer(peli(imdb_id="tt0073195"))


def test_no_acepta_una_ficha_con_otro_id():
    enriquecedor = enriquecedor_con({
        "find/tt0073195": {"movie_results": [{"id": 578}]},
        "movie/578": {**FICHA_TIBURON, "id": 111},
    })
    with pytest.raises(ErrorFuenteExterna, match="no es la que se pidio"):
        enriquecedor.enriquecer(peli(imdb_id="tt0073195"))


def test_un_imdb_que_tmdb_no_conoce():
    enriquecedor = enriquecedor_con({"find/tt0073195": {"movie_results": []}})
    with pytest.raises(ErrorFuenteExterna, match="no tiene ninguna pelicula"):
        enriquecedor.enriquecer(peli(imdb_id="tt0073195"))


def test_un_401_detiene_el_lote():
    fallo = ErrorFuenteExterna("Credencial rechazada", fuente="TMDb",
                               estado=401, detener_lote=True)
    enriquecedor = enriquecedor_con({}, fallo)

    with pytest.raises(ErrorFuenteExterna) as capturado:
        enriquecedor.enriquecer(peli(imdb_id="tt0073195"))
    assert capturado.value.detener_lote


def test_falta_de_credencial_da_un_mensaje_util():
    from gestor_peliculas.errores import ErrorConfiguracion

    with pytest.raises(ErrorConfiguracion, match=r"\.env"):
        ClienteTmdb("")


def test_busqueda_libre_por_enlace_de_imdb():
    enriquecedor = enriquecedor_con({
        "find/tt0073195": {"movie_results": [{"id": 578}]},
        "movie/578": FICHA_TIBURON,
    })

    candidatos = enriquecedor.candidatos_para("https://www.imdb.com/title/tt0073195/")

    assert len(candidatos) == 1
    assert candidatos[0].imdb_id == "tt0073195"
    assert candidatos[0].titulo == "Tiburon"


def test_busqueda_libre_ordena_por_cercania_de_anio():
    lejos = {"id": 1, "title": "Tiburon", "release_date": "1999-01-01"}
    cerca = {"id": 2, "title": "Tiburon", "release_date": "1976-01-01"}
    enriquecedor = enriquecedor_con({
        "search/movie": {"results": [lejos, cerca], "total_pages": 1},
    })

    candidatos = enriquecedor.candidatos_para("Tiburon", "1975")
    assert [c.tmdb_id for c in candidatos] == [2, 1]
