"""Importacion del dataset de puntajes de IMDb."""

import gzip

import pytest

from gestor_peliculas import puntajes
from gestor_peliculas.errores import ErrorDominio


def test_importa_y_descarta_las_filas_invalidas(bd, archivo_puntajes):
    resultado = puntajes.importar(bd, archivo_puntajes)

    assert resultado.leidas == 6
    assert resultado.guardadas == 4          # las cuatro validas
    assert resultado.descartadas == 2        # sin votos y fuera de rango
    assert bd.puntajes.contar() == 4


def test_los_valores_quedan_bien(bd, archivo_puntajes):
    puntajes.importar(bd, archivo_puntajes)
    puntaje = bd.puntajes.obtener("tt0073195")

    assert puntaje.puntaje == pytest.approx(8.1)
    assert puntaje.votos == 650000
    assert puntaje.texto == "8,1/10"


def test_descarta_las_filas_sin_votos_o_fuera_de_rango(bd, archivo_puntajes):
    puntajes.importar(bd, archivo_puntajes)
    assert bd.puntajes.obtener("tt9999999") is None   # 0 votos
    assert bd.puntajes.obtener("tt8888888") is None   # puntaje 11


def test_se_puede_filtrar_por_los_del_catalogo(bd, archivo_puntajes):
    resultado = puntajes.importar(bd, archivo_puntajes, solo_estos={"tt0073195"})
    assert resultado.guardadas == 1
    assert bd.puntajes.contar() == 1


def test_reimportar_actualiza_en_lugar_de_duplicar(bd, archivo_puntajes):
    puntajes.importar(bd, archivo_puntajes)
    puntajes.importar(bd, archivo_puntajes)
    assert bd.puntajes.contar() == 4


def test_rechaza_un_archivo_que_no_es_el_dataset(bd, tmp_path):
    otro = tmp_path / "title.basics.tsv.gz"
    with gzip.open(otro, "wt", encoding="utf-8") as salida:
        salida.write("tconst\ttitleType\tprimaryTitle\n")
        salida.write("tt0073195\tmovie\tJaws\n")

    with pytest.raises(ErrorDominio, match="title.ratings.tsv.gz"):
        puntajes.importar(bd, otro)


def test_archivo_vacio(bd, tmp_path):
    vacio = tmp_path / "title.ratings.tsv.gz"
    with gzip.open(vacio, "wt", encoding="utf-8"):
        pass
    with pytest.raises(ErrorDominio, match="vacio"):
        puntajes.importar(bd, vacio)


def test_archivo_inexistente(bd, tmp_path):
    with pytest.raises(ErrorDominio, match="No existe"):
        puntajes.importar(bd, tmp_path / "no-existe.tsv.gz")


def test_tambien_lee_el_tsv_sin_comprimir(bd, tmp_path):
    plano = tmp_path / "title.ratings.tsv"
    plano.write_text("tconst\taverageRating\tnumVotes\ntt0073195\t8.1\t650000\n",
                     encoding="utf-8")
    assert puntajes.importar(bd, plano).guardadas == 1


def test_se_puede_cancelar(bd, archivo_puntajes):
    llamadas = []

    def cancelado() -> bool:
        llamadas.append(1)
        return len(llamadas) > 2

    puntajes.importar(bd, archivo_puntajes, cancelado=cancelado)
    assert bd.puntajes.contar() <= 4


def test_el_catalogo_junta_el_puntaje_con_la_pelicula(bd, coleccion, archivo_puntajes):
    from gestor_peliculas.catalogo import indexador

    ubicacion, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
    puntajes.importar(bd, archivo_puntajes)

    tiburon = bd.peliculas.obtener_por_ruta(ubicacion.id, "1975 - Tiburon")
    assert tiburon.puntaje is not None
    assert tiburon.puntaje.texto == "8,1/10"

    # Una pelicula sin enlace de IMDb no puede tener puntaje.
    padrino = bd.peliculas.obtener_por_ruta(ubicacion.id, "1972 - El Padrino")
    assert padrino.puntaje is None
