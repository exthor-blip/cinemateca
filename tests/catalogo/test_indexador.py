"""Indexado: sincronizar el disco con la base sin perder lo ya sabido."""

import pytest

from gestor_peliculas.catalogo import indexador
from gestor_peliculas.errores import ErrorDominio
from gestor_peliculas.modelos import Metadatos


def test_indexar_da_de_alta_las_peliculas(bd, coleccion):
    ubicacion, resumen = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")

    assert ubicacion.id is not None
    assert resumen.peliculas_nuevas == 7      # 6 carpetas con video, y una de ellas tiene 2
    assert resumen.peliculas_actualizadas == 0
    assert bd.peliculas.contar() == 7


def test_reindexar_no_duplica(bd, coleccion):
    indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
    _, segundo = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")

    assert segundo.peliculas_nuevas == 0
    assert segundo.peliculas_actualizadas == 7
    assert bd.peliculas.contar() == 7


def test_reindexar_conserva_la_ficha_y_el_imdb_puesto_a_mano(bd, coleccion):
    """Lo mas importante del re-indexado: no pisar el trabajo ya hecho."""
    ubicacion, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
    padrino = bd.peliculas.obtener_por_ruta(ubicacion.id, "1972 - El Padrino")

    bd.peliculas.fijar_imdb_id(padrino.id, "tt0068646")
    bd.metadatos.guardar(padrino.id, Metadatos(
        tmdb_id=238, titulo="El Padrino", anio="1972",
        paises=["Estados Unidos"], generos=["Drama"], idiomas=["ingles"],
        idiomas_verificados=True,
    ))

    indexador.indexar_ubicacion(bd, ubicacion)

    despues = bd.peliculas.obtener(padrino.id)
    assert despues.imdb_id == "tt0068646"
    assert despues.metadatos is not None
    assert despues.metadatos.titulo == "El Padrino"


def test_una_pelicula_borrada_del_disco_se_da_de_baja(bd, coleccion):
    ubicacion, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
    carpeta = coleccion / "1972 - El Padrino"
    for archivo in carpeta.iterdir():
        archivo.unlink()
    carpeta.rmdir()

    resumen = indexador.indexar_ubicacion(bd, ubicacion)

    assert resumen.peliculas_eliminadas == 1
    assert bd.peliculas.contar() == 6
    assert bd.peliculas.obtener_por_ruta(ubicacion.id, "1972 - El Padrino") is None


def test_se_puede_pedir_que_no_de_de_baja_nada(bd, coleccion):
    """Util cuando el disco puede estar a medio conectar."""
    ubicacion, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
    carpeta = coleccion / "1972 - El Padrino"
    for archivo in carpeta.iterdir():
        archivo.unlink()
    carpeta.rmdir()

    resumen = indexador.indexar_ubicacion(bd, ubicacion, dar_de_baja_ausentes=False)

    assert resumen.peliculas_eliminadas == 0
    assert bd.peliculas.contar() == 7


def test_la_misma_carpeta_no_se_da_de_alta_dos_veces(bd, coleccion):
    primera, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
    segunda, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Otro nombre")
    assert primera.id == segunda.id
    assert len(bd.ubicaciones.listar()) == 1


def test_carpeta_inexistente_da_error_claro(bd, tmp_path):
    with pytest.raises(ErrorDominio, match="No existe la carpeta"):
        indexador.indexar_carpeta(bd, tmp_path / "no-existe")


def test_reindexar_todo_saltea_las_ubicaciones_no_disponibles(bd, coleccion, tmp_path):
    indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
    desconectada = tmp_path / "disco-externo"
    desconectada.mkdir()
    bd.ubicaciones.alta(desconectada, "Disco externo")
    desconectada.rmdir()

    resultados = indexador.reindexar_todo(bd)

    assert "Peliculas" in resultados
    assert "Disco externo" not in resultados
    assert bd.peliculas.contar() == 7
