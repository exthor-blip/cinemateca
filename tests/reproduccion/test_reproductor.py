"""Reproduccion: la validacion de ruta es lo critico.

Porta las comprobaciones de ResolveVideo e IsSegment de Mi_Cinemateca_VLC.cs.
Una ruta que se escape de la ubicacion significaria poder abrir cualquier
archivo del disco, asi que hay un test por cada forma de intentarlo.
"""

from pathlib import Path

import pytest

from gestor_peliculas.errores import ErrorReproduccion, RutaFueraDeUbicacion
from gestor_peliculas.modelos import Pelicula
from gestor_peliculas.reproduccion import localizador_vlc, reproductor


@pytest.fixture()
def ubicacion(tmp_path):
    raiz = tmp_path / "Peliculas"
    (raiz / "1975 - Tiburon").mkdir(parents=True)
    (raiz / "1975 - Tiburon" / "1975 - Tiburon.mkv").write_bytes(b"\x00" * 64)
    # Un archivo fuera de la ubicacion, que nunca deberia poder abrirse.
    (tmp_path / "secreto.mkv").write_bytes(b"\x00")
    return raiz


def peli(ubicacion, relativa="1975 - Tiburon", archivo="1975 - Tiburon.mkv"):
    return Pelicula(
        id=1, ubicacion_id=1, ubicacion_ruta=ubicacion,
        ruta_relativa=relativa, archivo_video=archivo, titulo_carpeta="Tiburon",
    )


def test_resuelve_una_ruta_valida(ubicacion):
    destino = reproductor.resolver_video(ubicacion, "1975 - Tiburon", "1975 - Tiburon.mkv")
    assert destino.is_file()
    assert destino.name == "1975 - Tiburon.mkv"


@pytest.mark.parametrize("relativa", [
    "..",
    "../..",
    "1975 - Tiburon/../..",
    "../otra",
])
def test_rechaza_salirse_de_la_ubicacion(ubicacion, relativa):
    with pytest.raises(RutaFueraDeUbicacion):
        reproductor.resolver_video(ubicacion, relativa, "secreto.mkv")


def test_rechaza_un_nombre_de_archivo_con_separadores(ubicacion):
    """El nombre tiene que ser un nombre, no un pedazo de ruta."""
    for nombre in ("../secreto.mkv", "sub/otro.mkv", "C:\\Windows\\notepad.mkv"):
        with pytest.raises(RutaFueraDeUbicacion):
            reproductor.resolver_video(ubicacion, "1975 - Tiburon", nombre)


def test_rechaza_una_extension_que_no_es_de_video(ubicacion):
    (ubicacion / "1975 - Tiburon" / "script.bat").write_text("echo hola")
    with pytest.raises(RutaFueraDeUbicacion, match="extension de video"):
        reproductor.resolver_video(ubicacion, "1975 - Tiburon", "script.bat")


def test_rechaza_un_archivo_que_ya_no_esta(ubicacion):
    with pytest.raises(RutaFueraDeUbicacion, match="ya no esta"):
        reproductor.resolver_video(ubicacion, "1975 - Tiburon", "borrada.mkv")


def test_rechaza_una_raiz_relativa():
    with pytest.raises(RutaFueraDeUbicacion, match="absoluta"):
        reproductor.resolver_video(Path("relativa"), "", "x.mkv")


def test_reproducir_sin_vlc_da_un_mensaje_util(ubicacion, monkeypatch):
    monkeypatch.setattr(localizador_vlc, "localizar", lambda *a, **k: None)
    with pytest.raises(ErrorReproduccion, match="videolan.org"):
        reproductor.reproducir(peli(ubicacion))


def test_reproducir_arma_bien_el_comando(ubicacion, monkeypatch, tmp_path):
    """Se comprueba el comando sin abrir VLC de verdad."""
    falso_vlc = tmp_path / "vlc.exe"
    falso_vlc.write_bytes(b"\x00")
    monkeypatch.setattr(localizador_vlc, "localizar", lambda *a, **k: falso_vlc)

    lanzados = []
    monkeypatch.setattr(reproductor.subprocess, "Popen",
                        lambda comando, **kwargs: lanzados.append((comando, kwargs)))

    destino = reproductor.reproducir(peli(ubicacion))

    comando, _kwargs = lanzados[0]
    assert comando[0] == str(falso_vlc)
    assert "--one-instance" in comando
    # El -- antes de la ruta evita que un nombre con guion se tome por opcion.
    assert comando[-2] == "--"
    assert comando[-1] == str(destino)


def test_reproducir_sin_ubicacion_falla_claro():
    suelta = Pelicula(id=1, archivo_video="x.mkv")
    with pytest.raises(ErrorReproduccion, match="ubicacion"):
        reproductor.reproducir(suelta)


class TestLocalizadorVlc:
    def test_la_ruta_configurada_tiene_prioridad(self, tmp_path):
        localizador_vlc.olvidar()
        falso = tmp_path / "vlc.exe"
        falso.write_bytes(b"\x00")
        assert localizador_vlc.localizar(str(falso)) == falso
        # Tambien acepta que apunten a la carpeta en lugar del ejecutable.
        assert localizador_vlc.localizar(str(tmp_path)) == falso

    def test_una_ruta_configurada_invalida_no_rompe(self, tmp_path):
        localizador_vlc.olvidar()
        resultado = localizador_vlc.localizar(str(tmp_path / "no-existe.exe"))
        # Cae a la busqueda normal: puede encontrar VLC o no, pero no lanza.
        assert resultado is None or resultado.is_file()
