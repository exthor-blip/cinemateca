"""Las rutas responden, y los POST exigen token CSRF."""

import pytest

from gestor_peliculas.catalogo import indexador
from gestor_peliculas.config import Ajustes
from gestor_peliculas.modelos import Metadatos
from gestor_peliculas.web import crear_app


@pytest.fixture()
def app(tmp_path, coleccion):
    """Aplicacion con un catalogo chico ya indexado."""
    ruta_bd = tmp_path / "web.db"
    ajustes = Ajustes(carpeta_datos=tmp_path, ruta_bd=ruta_bd, por_pagina=4)

    from gestor_peliculas.almacenamiento.bd import BaseDatos

    with BaseDatos(ruta_bd) as bd:
        ubicacion, _ = indexador.indexar_carpeta(bd, coleccion, nombre="Peliculas")
        tiburon = bd.peliculas.obtener_por_ruta(ubicacion.id, "1975 - Tiburon")
        bd.metadatos.guardar(tiburon.id, Metadatos(
            tmdb_id=578, titulo="Tiburon", titulo_original="Jaws", anio="1975",
            paises=["Estados Unidos"], generos=["Terror"], idiomas=["ingles"],
            director="Steven Spielberg", duracion_min=124, idiomas_verificados=True,
        ))
        bd.puntajes.guardar_lote([("tt0073195", 8.1, 650000)])
        bd.conexion.commit()
        ids = {
            "con_ficha": tiburon.id,
            "sin_ficha": bd.peliculas.obtener_por_ruta(ubicacion.id, "1972 - El Padrino").id,
        }

    aplicacion = crear_app(ajustes, ruta_bd=ruta_bd)
    aplicacion.config.update(TESTING=True)
    aplicacion.ids = ids
    aplicacion.coleccion = coleccion
    return aplicacion


@pytest.fixture()
def cliente(app):
    return app.test_client()


@pytest.mark.parametrize("url", [
    "/",
    "/?q=tibu",
    "/?pais=Estados+Unidos",
    "/?genero=Terror",
    "/?anio=1975",
    "/?ficha=pendientes",
    "/?sin_imdb=1",
    "/?orden=puntaje",
    "/?pagina=2",
    "/ubicaciones/",
    "/ubicaciones/explorar",
    "/organizador/",
    "/metadatos/pendientes",
    "/peliculas/vlc/estado",
])
def test_las_pantallas_responden(cliente, url):
    assert cliente.get(url).status_code == 200


def test_la_ficha_muestra_los_metadatos(cliente, app):
    pagina = cliente.get(f"/peliculas/{app.ids['con_ficha']}").get_data(as_text=True)
    assert "Steven Spielberg" in pagina
    assert "2 h 4 min" in pagina
    assert "tt0073195" in pagina
    assert "8,1/10" in pagina


def test_la_ficha_sin_metadatos_ofrece_resolverla(cliente, app):
    pagina = cliente.get(f"/peliculas/{app.ids['sin_ficha']}").get_data(as_text=True)
    assert "Metadatos pendientes" in pagina
    assert "Vincular Imdb" in pagina


def test_una_pelicula_que_no_existe_da_un_mensaje_claro(cliente):
    respuesta = cliente.get("/peliculas/99999")
    assert respuesta.status_code == 400
    assert "No hay ninguna pelicula" in respuesta.get_data(as_text=True)


def test_el_catalogo_pagina(cliente):
    primera = cliente.get("/?pagina=1").get_data(as_text=True)
    segunda = cliente.get("/?pagina=2").get_data(as_text=True)
    assert "pagination" in primera
    assert primera != segunda


def test_un_texto_con_sintaxis_fts_no_rompe_la_busqueda(cliente):
    for raro in ['"', "NEAR(", "*", "OR AND", "()"]:
        assert cliente.get("/", query_string={"q": raro}).status_code == 200


def test_el_poster_se_sirve_y_el_que_falta_da_404(cliente, app):
    assert cliente.get(f"/poster/{app.ids['con_ficha']}").status_code == 200
    assert cliente.get(f"/poster/{app.ids['sin_ficha']}").status_code == 404


@pytest.mark.parametrize("url", [
    "/indice/vaciar",
    "/ubicaciones/agregar",
    "/ubicaciones/reindexar",
    "/metadatos/completar",
    "/organizador/analizar",
])
def test_los_post_exigen_token_csrf(cliente, url):
    """La aplicacion lanza procesos y renombra archivos: los POST van protegidos."""
    assert cliente.post(url, data={}).status_code == 400


def test_reproducir_sin_token_tambien_se_rechaza(cliente, app):
    assert cliente.post(f"/peliculas/{app.ids['sin_ficha']}/reproducir").status_code == 400


def test_con_token_el_post_pasa(cliente, app):
    """Se comprueba con el formulario de analisis, que no modifica nada."""
    pagina = cliente.get("/organizador/").get_data(as_text=True)
    token = pagina.split('name="csrf_token" value="')[1].split('"')[0]

    respuesta = cliente.post("/organizador/analizar",
                             data={"csrf_token": token, "ruta": str(app.coleccion)})
    assert respuesta.status_code == 302


def test_el_explorador_lista_carpetas(cliente, app):
    datos = cliente.get("/ubicaciones/explorar",
                        query_string={"ruta": str(app.coleccion)}).get_json()
    nombres = {c["nombre"] for c in datos["carpetas"]}
    assert "1975 - Tiburon" in nombres
    assert datos["padre"] is not None


def test_el_explorador_rechaza_una_carpeta_que_no_existe(cliente):
    assert cliente.get("/ubicaciones/explorar",
                       query_string={"ruta": "Z:/no/existe"}).status_code == 404


def test_una_pagina_que_no_existe_da_404(cliente):
    assert cliente.get("/no-existe").status_code == 404


def test_sin_credencial_no_se_ofrece_completar_metadatos(cliente):
    pagina = cliente.get("/").get_data(as_text=True)
    assert "hace falta la clave de TMDb" in pagina


def test_bootstrap_se_sirve_desde_el_proyecto(cliente):
    """La aplicacion tiene que funcionar sin internet."""
    pagina = cliente.get("/").get_data(as_text=True)
    assert "cdn.jsdelivr.net" not in pagina
    assert cliente.get("/static/vendor/bootstrap/css/bootstrap.min.css").status_code == 200
    assert cliente.get("/static/css/cinemateca.css").status_code == 200
