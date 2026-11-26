"""El filtro viaja por la URL: tiene que aguantar cualquier cosa escrita a mano."""

from gestor_peliculas.busqueda.filtros import EstadoFicha, FiltroBusqueda, Orden, Pagina


def desde(datos: dict) -> FiltroBusqueda:
    return FiltroBusqueda.desde_parametros(lambda clave, por_defecto="": datos.get(clave, por_defecto))


def test_lee_los_parametros_normales():
    filtro = desde({"q": "tiburon", "pais": "Japon", "anio": "1975",
                    "genero": "Terror", "idioma": "ingles", "ficha": "pendientes",
                    "sin_imdb": "1", "ubicacion": "3", "orden": "puntaje", "pagina": "2"})
    assert filtro.texto == "tiburon"
    assert filtro.anio == "1975"
    assert filtro.ficha is EstadoFicha.PENDIENTES
    assert filtro.sin_imdb is True
    assert filtro.ubicacion_id == 3
    assert filtro.orden is Orden.PUNTAJE
    assert filtro.pagina == 2


def test_valores_invalidos_se_ignoran_en_lugar_de_fallar():
    filtro = desde({"anio": "mil novecientos", "ficha": "inventado",
                    "orden": "inventado", "pagina": "-5", "ubicacion": "abc"})
    assert filtro.anio == ""
    assert filtro.ficha is EstadoFicha.TODAS
    assert filtro.orden is Orden.TITULO
    assert filtro.pagina == 1
    assert filtro.ubicacion_id is None


def test_el_texto_se_recorta():
    assert len(desde({"q": "x" * 500}).texto) == 200


def test_filtro_vacio_no_esta_activo():
    assert not FiltroBusqueda().activo
    assert FiltroBusqueda(texto="algo").activo
    assert FiltroBusqueda(sin_imdb=True).activo
    assert not FiltroBusqueda(orden=Orden.PUNTAJE, pagina=4).activo


def test_limpio_conserva_orden_y_paginado():
    filtro = FiltroBusqueda(texto="x", pais="Japon", orden=Orden.PUNTAJE, por_pagina=24)
    limpio = filtro.limpio()
    assert not limpio.activo
    assert limpio.orden is Orden.PUNTAJE
    assert limpio.por_pagina == 24


def test_como_parametros_arma_enlaces_sin_valores_vacios():
    filtro = FiltroBusqueda(texto="tiburon", pais="Japon")
    cadena = filtro.como_parametros()
    assert "q=tiburon" in cadena
    assert "pais=Japon" in cadena
    assert "genero=" not in cadena
    assert "pagina=" not in cadena          # la pagina 1 no se escribe


def test_como_parametros_permite_cambiar_de_pagina():
    assert "pagina=3" in FiltroBusqueda(texto="x").como_parametros(pagina=3)


def test_paginacion_calcula_la_ventana():
    pagina = Pagina(peliculas=[], total=250, pagina=5, por_pagina=60)
    assert pagina.total_paginas == 5
    assert pagina.ventana(radio=2) == [3, 4, 5]
    assert pagina.tiene_anterior
    assert not pagina.tiene_siguiente
    assert (pagina.desde, pagina.hasta) == (241, 250)


def test_pagina_vacia_no_divide_por_cero():
    vacia = Pagina()
    assert vacia.total_paginas == 1
    assert vacia.desde == 0
    assert vacia.ventana() == [1]
