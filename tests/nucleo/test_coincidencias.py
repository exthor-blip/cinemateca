"""La regla mas importante: cuando una coincidencia se guarda sin preguntar."""

from gestor_peliculas.modelos import Candidato
from gestor_peliculas.nucleo.coincidencias import Veredicto, clasificar, ordenar_para_revision


def cand(imdb_id, titulo, anio, original=""):
    return Candidato(imdb_id=imdb_id, titulo=titulo, anio=anio, titulo_original=original)


def test_sin_candidatos_es_sin_coincidencia():
    resultado = clasificar([], "Tiburon", "1975")
    assert resultado.veredicto is Veredicto.SIN_COINCIDENCIA
    assert resultado.elegido is None


def test_una_sola_ficha_con_titulo_y_anio_exactos_es_exacta():
    resultado = clasificar([cand("tt0073195", "Tiburon", "1975")], "Tiburon", "1975")
    assert resultado.es_exacta
    assert resultado.elegido.imdb_id == "tt0073195"


def test_dos_fichas_con_mismo_titulo_y_anio_van_a_revision():
    """Nunca se elige sola entre dos: es el caso que mas dano hace si se equivoca."""
    candidatos = [cand("tt1", "Tiburon", "1975"), cand("tt2", "Tiburon", "1975")]
    resultado = clasificar(candidatos, "Tiburon", "1975")
    assert resultado.veredicto is Veredicto.REVISAR
    assert len(resultado.candidatos) == 2


def test_mismo_titulo_pero_otro_anio_va_a_revision_y_ordena_por_cercania():
    candidatos = [cand("tt_lejos", "Tiburon", "1990"), cand("tt_cerca", "Tiburon", "1976")]
    resultado = clasificar(candidatos, "Tiburon", "1975")
    assert resultado.veredicto is Veredicto.REVISAR
    assert resultado.elegido.imdb_id == "tt_cerca"


def test_coincidir_solo_el_anio_no_alcanza():
    resultado = clasificar([cand("tt9", "Otra pelicula", "1975")], "Tiburon", "1975")
    assert resultado.veredicto is Veredicto.REVISAR
    assert "anio" in resultado.nota.lower()


def test_el_titulo_original_tambien_cuenta():
    """Buscando Tiburon, una ficha cuyo titulo original es Jaws es exacta."""
    resultado = clasificar(
        [cand("tt0073195", "Jaws", "1975", original="Jaws")], "Tiburon", "1975",
        titulos_extra=["Jaws"],
    )
    assert resultado.es_exacta


def test_sin_anio_en_la_carpeta_nunca_es_exacta():
    """Sin anio no hay como confirmar: la decision queda en manos de la persona."""
    resultado = clasificar([cand("tt0073195", "Tiburon", "1975")], "Tiburon", "")
    assert resultado.veredicto is Veredicto.REVISAR


def test_ordenar_para_revision_descarta_los_rechazados():
    candidatos = [
        cand("tt_malo", "Tiburon", "1975"),
        cand("tt_bueno", "Tiburon", "1975"),
        cand("tt_otro", "Otra", "1999"),
    ]
    orden = ordenar_para_revision(candidatos, "Tiburon", "1975", rechazados={"tt_malo"})
    assert [c.imdb_id for c in orden] == ["tt_bueno", "tt_otro"]


def test_ordenar_pone_primero_el_titulo_exacto():
    candidatos = [cand("tt_parecido", "Tiburon 2", "1975"), cand("tt_exacto", "Tiburon", "1978")]
    orden = ordenar_para_revision(candidatos, "Tiburon", "1975")
    assert orden[0].imdb_id == "tt_exacto"
