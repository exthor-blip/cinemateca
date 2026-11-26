"""Parseo de nombres de carpeta: las tres convenciones del proyecto viejo."""

import pytest

from gestor_peliculas.nucleo.titulos import (
    OrigenAnio,
    limpiar_titulo,
    mismo_titulo,
    normalizar_titulo,
    parsear_anio_titulo,
    quitar_sufijo_origen,
    variantes_consulta,
)


@pytest.mark.parametrize(("nombre", "titulo", "anio", "origen"), [
    # Formato estricto que exigia IMDB linker 4.3.ps1.
    ("1975 - Tiburon", "Tiburon", "1975", OrigenAnio.EXPLICITO),
    ("1975 – Tiburon", "Tiburon", "1975", OrigenAnio.EXPLICITO),
    ("1975 — Tiburon", "Tiburon", "1975", OrigenAnio.EXPLICITO),
    # Formato con el anio al final, que aceptaba Mi_Cinemateca.
    ("Tiburon (1975)", "Tiburon", "1975", OrigenAnio.EXPLICITO),
    # Anio suelto: nombres estilo scene.
    ("The.Matrix.1999.1080p.BluRay", "The Matrix", "1999", OrigenAnio.SUELTO),
    ("El_Padrino_1972", "El Padrino", "1972", OrigenAnio.SUELTO),
    # Sin anio: el nombre crudo, como hacia el Organizador.
    ("Pelicula sin fecha", "Pelicula sin fecha", "", OrigenAnio.AUSENTE),
    ("", "", "", OrigenAnio.AUSENTE),
])
def test_parsear_reconoce_las_tres_convenciones(nombre, titulo, anio, origen):
    resultado = parsear_anio_titulo(nombre)
    assert (resultado.titulo, resultado.anio, resultado.origen) == (titulo, anio, origen)


def test_anio_dentro_del_titulo_se_conserva():
    """2001 Odisea del espacio lleva un anio en el titulo; el prefijo manda."""
    resultado = parsear_anio_titulo("2001 - 2001 Odisea del espacio")
    assert resultado.es_explicito
    assert resultado.titulo == "2001 Odisea del espacio"
    assert resultado.anio == "2001"


@pytest.mark.parametrize(("entrada", "esperado"), [
    ("Mi vecino Totoro (Japon)", "Mi vecino Totoro"),
    ("Z (Francia) (Argelia)", "Z"),
    ("Amelie (Francia)", "Amelie"),
    # Un subtitulo oficial entre parentesis NO es una etiqueta de origen y se conserva.
    ("Blade Runner (The Final Cut)", "Blade Runner (The Final Cut)"),
    ("Dr. Strangelove (1964)", "Dr. Strangelove (1964)"),
])
def test_quitar_sufijo_origen_respeta_los_subtitulos(entrada, esperado):
    assert quitar_sufijo_origen(entrada) == esperado


def test_limpiar_titulo_quita_prefijo_sufijo_y_origen():
    assert limpiar_titulo("1988 - Mi vecino Totoro (Japon)") == "Mi vecino Totoro"
    assert limpiar_titulo("Tiburon (1975)") == "Tiburon"


def test_normalizar_quita_tildes_y_puntuacion():
    assert normalizar_titulo("¿Qué He Hecho Yo?!") == "que he hecho yo"
    assert normalizar_titulo("Amélie") == normalizar_titulo("Amelie")
    assert normalizar_titulo("WALL·E") == "wall e"
    assert normalizar_titulo("L’Avventura") == "lavventura"
    assert normalizar_titulo("") == ""


def test_mismo_titulo_ignora_formato():
    assert mismo_titulo("El Padrino", "el  padrino")
    assert mismo_titulo("Amelie", "Amélie")
    assert not mismo_titulo("El Padrino", "El Padrino II")
    assert not mismo_titulo("", "cualquiera")


def test_variantes_consulta_parte_por_separadores():
    assert variantes_consulta("Blade Runner - The Final Cut", "1982") == [
        "Blade Runner - The Final Cut", "Blade Runner", "The Final Cut",
    ]
    assert variantes_consulta("Tiburon 1975", "1975") == ["Tiburon"]
    assert variantes_consulta("", "1975") == []
