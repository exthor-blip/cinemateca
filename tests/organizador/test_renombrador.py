"""Renombrado seguro: conflictos y el caso NTFS de solo-mayusculas."""

from gestor_peliculas.organizador.renombrador import (
    Resultado,
    destino_ocupado,
    nombre_destino,
    renombrar,
    renombrar_solo_caja,
)


def test_renombra_un_archivo(tmp_path):
    origen = tmp_path / "viejo.mkv"
    origen.write_bytes(b"x")
    destino = tmp_path / "nuevo.mkv"

    operacion = renombrar(origen, destino)

    assert operacion.resultado is Resultado.RENOMBRADO
    assert destino.exists() and not origen.exists()


def test_no_sobrescribe_nunca(tmp_path):
    """La regla mas importante: si el destino existe, no se toca nada."""
    origen = tmp_path / "a.mkv"
    origen.write_bytes(b"origen")
    destino = tmp_path / "b.mkv"
    destino.write_bytes(b"destino")

    operacion = renombrar(origen, destino)

    assert operacion.resultado is Resultado.CONFLICTO
    assert origen.read_bytes() == b"origen"
    assert destino.read_bytes() == b"destino"


def test_origen_igual_a_destino_no_hace_nada(tmp_path):
    archivo = tmp_path / "igual.mkv"
    archivo.write_bytes(b"x")
    assert renombrar(archivo, archivo).resultado is Resultado.SIN_CAMBIOS


def test_simular_no_escribe(tmp_path):
    origen = tmp_path / "viejo.mkv"
    origen.write_bytes(b"x")
    destino = tmp_path / "nuevo.mkv"

    operacion = renombrar(origen, destino, simular=True)

    assert operacion.resultado is Resultado.SIMULADO
    assert origen.exists() and not destino.exists()


def test_cambio_de_solo_mayusculas(tmp_path):
    """NTFS no distingue la caja: hace falta pasar por un nombre temporal."""
    origen = tmp_path / "PELICULA.MKV"
    origen.write_bytes(b"contenido")

    operacion = renombrar_solo_caja(origen, "pelicula.mkv")

    assert operacion.resultado is Resultado.RENOMBRADO
    nombres = [a.name for a in tmp_path.iterdir()]
    assert nombres == ["pelicula.mkv"]
    assert (tmp_path / "pelicula.mkv").read_bytes() == b"contenido"
    # Y no queda ningun temporal tirado.
    assert not any(n.startswith(".__organizador_tmp_") for n in nombres)


def test_cambio_de_caja_que_ya_esta_bien(tmp_path):
    archivo = tmp_path / "pelicula.mkv"
    archivo.write_bytes(b"x")
    assert renombrar_solo_caja(archivo, "pelicula.mkv").resultado is Resultado.SIN_CAMBIOS


def test_renombrar_detecta_el_cambio_de_caja_solo(tmp_path):
    """renombrar() delega en la via de dos pasos cuando hace falta."""
    origen = tmp_path / "Pelicula.MKV"
    origen.write_bytes(b"x")

    operacion = renombrar(origen, tmp_path / "pelicula.mkv")

    assert operacion.resultado is Resultado.RENOMBRADO
    assert [a.name for a in tmp_path.iterdir()] == ["pelicula.mkv"]


def test_destino_ocupado_ignora_los_origenes_del_lote(tmp_path):
    """Dentro de un lote, que el destino de uno sea el origen de otro no es conflicto."""
    uno = tmp_path / "uno.mkv"
    uno.write_bytes(b"1")
    dos = tmp_path / "dos.mkv"
    dos.write_bytes(b"2")

    assert destino_ocupado(uno, [dos]) is True
    assert destino_ocupado(uno, [uno, dos]) is False
    assert destino_ocupado(tmp_path / "no-existe.mkv", []) is False


def test_nombre_destino_usa_el_nombre_de_la_carpeta(tmp_path):
    carpeta = tmp_path / "1975 - Tiburon"
    carpeta.mkdir()
    assert nombre_destino(carpeta, ".mkv").name == "1975 - Tiburon.mkv"
    assert nombre_destino(carpeta, ".srt", "1").name == "1975 - Tiburon1.srt"
