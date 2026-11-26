"""Busqueda y filtros sobre el catalogo."""

import pytest

from gestor_peliculas.busqueda import facetas
from gestor_peliculas.busqueda.consultas import ConsultaCatalogo, preparar_consulta_fts
from gestor_peliculas.busqueda.filtros import EstadoFicha, FiltroBusqueda, Orden
from gestor_peliculas.catalogo import indexador
from gestor_peliculas.modelos import Metadatos


@pytest.fixture()
def catalogo(bd, coleccion):
    """Catalogo indexado con dos fichas de TMDb cargadas."""
    ubicacion, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")

    tiburon = bd.peliculas.obtener_por_ruta(ubicacion.id, "1975 - Tiburon")
    bd.metadatos.guardar(tiburon.id, Metadatos(
        tmdb_id=578, titulo="Tiburon", titulo_original="Jaws", anio="1975",
        paises=["Estados Unidos"], generos=["Terror", "Aventura"], idiomas=["ingles"],
        director="Steven Spielberg", duracion_min=124, idiomas_verificados=True,
    ))
    totoro = bd.peliculas.obtener_por_ruta(ubicacion.id, "1988 - Mi vecino Totoro (Japon)")
    bd.metadatos.guardar(totoro.id, Metadatos(
        tmdb_id=8392, titulo="Mi vecino Totoro", titulo_original="Tonari no Totoro",
        anio="1988", paises=["Japon"], generos=["Animacion", "Fantasia"],
        idiomas=["japones"], idiomas_verificados=True,
    ))
    bd.puntajes.guardar_lote([("tt0073195", 8.1, 650000)])
    bd.conexion.commit()
    return ConsultaCatalogo(bd.conexion, usar_fts=bd.fts_disponible)


def titulos(pagina):
    return sorted(p.titulo for p in pagina.peliculas)


def test_sin_filtro_devuelve_todo(catalogo):
    pagina = catalogo.buscar(FiltroBusqueda())
    assert pagina.total == 7
    assert len(pagina.peliculas) == 7


def test_busca_por_titulo_parcial(catalogo):
    """Escribir 'tibu' tiene que encontrar Tiburon, como el includes() del HTML."""
    assert titulos(catalogo.buscar(FiltroBusqueda(texto="tibu"))) == ["Tiburon"]


def test_busca_por_titulo_original(catalogo):
    """Buscando Jaws aparece la pelicula cuya carpeta se llama Tiburon."""
    assert titulos(catalogo.buscar(FiltroBusqueda(texto="jaws"))) == ["Tiburon"]


def test_busca_sin_tildes(catalogo):
    assert titulos(catalogo.buscar(FiltroBusqueda(texto="japones"))) == []
    assert catalogo.buscar(FiltroBusqueda(texto="totoro")).total == 1


def test_busca_por_anio(catalogo):
    assert titulos(catalogo.buscar(FiltroBusqueda(texto="1975"))) == ["Tiburon"]


def test_texto_con_puntuacion_no_rompe_la_consulta(catalogo):
    """Un texto que seria sintaxis FTS5 invalida no puede hacer fallar la busqueda."""
    for raro in ['"', "NEAR(", "*", "OR AND", "()", "tibu*ron", "a:b"]:
        catalogo.buscar(FiltroBusqueda(texto=raro))


def test_filtra_por_pais_genero_e_idioma(catalogo):
    assert titulos(catalogo.buscar(FiltroBusqueda(pais="Japon"))) == ["Mi vecino Totoro"]
    assert titulos(catalogo.buscar(FiltroBusqueda(genero="Terror"))) == ["Tiburon"]
    assert titulos(catalogo.buscar(FiltroBusqueda(idioma="ingles"))) == ["Tiburon"]
    assert catalogo.buscar(FiltroBusqueda(pais="Marte")).total == 0


def test_filtra_por_anio_exacto(catalogo):
    assert titulos(catalogo.buscar(FiltroBusqueda(anio="1988"))) == ["Mi vecino Totoro"]


def test_filtra_pendientes_y_con_ficha(catalogo):
    con_ficha = catalogo.buscar(FiltroBusqueda(ficha=EstadoFicha.CON_FICHA))
    pendientes = catalogo.buscar(FiltroBusqueda(ficha=EstadoFicha.PENDIENTES))
    assert con_ficha.total == 2
    assert pendientes.total == 5
    assert con_ficha.total + pendientes.total == 7


def test_filtra_las_que_no_tienen_enlace_imdb(catalogo):
    """Es el boton 'Sin enlace Imdb' de la version 1.14."""
    sin_imdb = catalogo.buscar(FiltroBusqueda(sin_imdb=True))
    assert "Tiburon" not in titulos(sin_imdb)
    assert "El Padrino" in titulos(sin_imdb)


def test_combina_filtros(catalogo):
    filtro = FiltroBusqueda(texto="totoro", pais="Japon", genero="Animacion")
    assert titulos(catalogo.buscar(filtro)) == ["Mi vecino Totoro"]
    assert catalogo.buscar(FiltroBusqueda(texto="totoro", pais="Japon",
                                          genero="Terror")).total == 0


def test_ordena_por_anio_y_por_puntaje(catalogo):
    nuevas = catalogo.buscar(FiltroBusqueda(orden=Orden.ANIO_DESC))
    assert nuevas.peliculas[0].anio >= nuevas.peliculas[-1].anio

    mejores = catalogo.buscar(FiltroBusqueda(orden=Orden.PUNTAJE))
    assert mejores.peliculas[0].titulo == "Tiburon"


def test_pagina_y_cuenta_bien(catalogo):
    primera = catalogo.buscar(FiltroBusqueda(por_pagina=2, pagina=1))
    segunda = catalogo.buscar(FiltroBusqueda(por_pagina=2, pagina=2))

    assert primera.total == 7
    assert primera.total_paginas == 4
    assert len(primera.peliculas) == 2
    assert primera.tiene_siguiente and not primera.tiene_anterior
    assert segunda.tiene_anterior
    assert (primera.desde, primera.hasta) == (1, 2)
    assert not set(titulos(primera)) & set(titulos(segunda))


def test_pagina_fuera_de_rango_queda_vacia_sin_error(catalogo):
    pagina = catalogo.buscar(FiltroBusqueda(pagina=99))
    assert pagina.peliculas == []
    assert pagina.total == 7


def test_ids_que_coinciden(catalogo):
    ids = catalogo.ids_que_coinciden(FiltroBusqueda(sin_imdb=True))
    assert len(ids) == catalogo.buscar(FiltroBusqueda(sin_imdb=True)).total


def test_facetas_traen_valores_con_conteo(bd, catalogo):
    calculadas = facetas.calcular(bd.conexion)
    assert [o.valor for o in calculadas.paises] == ["Estados Unidos", "Japon"]
    assert all(o.cantidad == 1 for o in calculadas.paises)
    assert "Terror" in [o.valor for o in calculadas.generos]
    assert calculadas.anios[0].valor >= calculadas.anios[-1].valor
    assert calculadas.ubicaciones[0][1] == "Peliculas"


def test_resumen_del_catalogo(bd, catalogo):
    resumen = facetas.resumir(bd.conexion, visibles=7)
    assert resumen.total == 7
    assert resumen.con_ficha == 2
    assert resumen.pendientes == 5
    assert resumen.ubicaciones == 1
    assert resumen.con_puntaje == 1


@pytest.mark.parametrize(("entrada", "esperado"), [
    ("tiburon", '"tiburon"*'),
    ("el padrino", '"el"* AND "padrino"*'),
    ('"raro', '"raro"*'),
    ("   ", ""),
    ("!!!", ""),
])
def test_preparar_consulta_fts(entrada, esperado):
    assert preparar_consulta_fts(entrada) == esperado
