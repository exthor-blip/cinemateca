"""Posteres: validacion, descarga y miniaturas.

Las tarjetas del catalogo miden 160 px de ancho, asi que servir un poster
original de 1000 px por cada una desperdicia disco y tiempo. Se genera una
miniatura por pelicula en la carpeta de datos y se sirve esa; el original nunca
se modifica.

La validacion por bytes magicos es la del linker: un archivo que se llama .jpg
pero no empieza con FF D8 no se guarda como poster.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .. import registro
from ..errores import ErrorFuenteExterna

log = registro.obtener(__name__)

ANCHO_MINIATURA = 320
CALIDAD = 82

#: Por encima de esto no se sirve el original como respaldo: se prefiere no
#: mostrar poster antes que mandarle 17 MB al navegador para una tarjeta de
#: 160 px. En la coleccion real hay posters de hasta 100 megapixeles.
TAMANIO_MAXIMO_ORIGINAL = 3 * 1024 * 1024

#: Firmas de los formatos que se aceptan como poster.
FIRMAS: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"RIFF": "webp",       # se confirma mas abajo con el marcador WEBP
}


def formato_de(datos: bytes) -> str:
    """Formato de imagen segun los bytes magicos, o '' si no se reconoce."""
    if not datos or len(datos) < 12:
        return ""
    if datos.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if datos.startswith(b"RIFF") and datos[8:12] == b"WEBP":
        return "webp"
    return ""


def es_jpeg(datos: bytes) -> bool:
    """La comprobacion exacta que hace Write-Result del linker."""
    return len(datos) > 3 and datos[0] == 0xFF and datos[1] == 0xD8


def validar_imagen(datos: bytes) -> str:
    """Devuelve el formato o levanta ErrorFuenteExterna si no es una imagen."""
    formato = formato_de(datos)
    if not formato:
        raise ErrorFuenteExterna(
            "Lo que se descargo no es una imagen reconocible; no se guarda.", fuente="poster"
        )
    return formato


def _clave(ruta: Path) -> str:
    """Nombre de la miniatura: depende de la ruta, el tamanio y la fecha.

    Asi, si se reemplaza el poster del disco, la miniatura se regenera sola sin
    tener que vaciar nada a mano.
    """
    try:
        estado = ruta.stat()
        semilla = f"{ruta}|{estado.st_size}|{int(estado.st_mtime)}"
    except OSError:
        semilla = str(ruta)
    return hashlib.sha256(semilla.encode("utf-8")).hexdigest()[:24]


def miniatura(origen: Path, carpeta_cache: Path, *, ancho: int = ANCHO_MINIATURA) -> Path | None:
    """Devuelve la miniatura del poster, generandola la primera vez.

    Si Pillow no puede abrir el archivo (un .jpg corrupto, por ejemplo) se
    devuelve None y quien llama sirve el original o el marcador de vacio. Un
    poster ilegible no puede tirar abajo la pagina del catalogo.
    """
    if not origen.is_file():
        return None

    destino = carpeta_cache / f"{_clave(origen)}.jpg"
    if destino.exists():
        return destino

    try:
        from PIL import Image, ImageOps

        # El limite de "bomba de descompresion" de Pillow protege contra
        # imagenes hostiles subidas por terceros. Aca los archivos son los
        # posters del disco de la propia persona, y algunos son legitimamente
        # enormes (hay varios de mas de 20 megapixeles, uno de 102). Se sube el
        # limite a proposito para que no corte la miniatura de un archivo suyo.
        if Image.MAX_IMAGE_PIXELS is not None and Image.MAX_IMAGE_PIXELS < 300_000_000:
            Image.MAX_IMAGE_PIXELS = 300_000_000

        with Image.open(origen) as imagen:
            # draft() deja que libjpeg decodifique ya reducido (1/2, 1/4, 1/8).
            # Decodificar un poster de 1000 px entero para despues achicarlo a
            # 320 es el grueso del costo: con esto una miniatura pasa de unos
            # 200 ms a unas decenas.
            if imagen.format == "JPEG":
                imagen.draft("RGB", (ancho, ancho * 3))

            imagen = ImageOps.exif_transpose(imagen)
            if imagen.mode not in ("RGB", "L"):
                imagen = imagen.convert("RGB")
            if imagen.width > ancho:
                alto = max(1, round(imagen.height * ancho / imagen.width))
                # BILINEAR tras un draft() da un resultado equivalente a
                # LANCZOS sobre el original, porque ya se redujo en el decode.
                imagen = imagen.resize((ancho, alto), Image.BILINEAR)

            carpeta_cache.mkdir(parents=True, exist_ok=True)
            temporal = destino.with_suffix(".parcial")
            imagen.save(temporal, "JPEG", quality=CALIDAD, optimize=True)
            temporal.replace(destino)
        return destino
    except Exception as error:  # noqa: BLE001 - Pillow levanta de todo
        log.debug("No se pudo generar la miniatura de %s: %s", origen, error)
        return None


def guardar_poster(datos: bytes, carpeta_destino: Path, *,
                   nombre: str = "poster.jpg", sobrescribir: bool = False) -> Path | None:
    """Guarda un poster descargado en la carpeta de la pelicula.

    Escribe primero a un temporal y recien lo promueve si el contenido es una
    imagen valida, como hacia el linker. Nunca sobrescribe salvo que se pida.
    """
    destino = carpeta_destino / nombre
    if destino.exists() and not sobrescribir:
        return destino

    validar_imagen(datos)
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    temporal = carpeta_destino / f".poster_parcial_{_clave(destino)}.tmp"
    try:
        temporal.write_bytes(datos)
        temporal.replace(destino)
        return destino
    except OSError as error:
        log.warning("No se pudo escribir el poster en %s: %s", destino, error)
        return None
    finally:
        temporal.unlink(missing_ok=True)


def limpiar_cache(carpeta_cache: Path) -> int:
    """Borra las miniaturas. Devuelve cuantas saco."""
    if not carpeta_cache.is_dir():
        return 0
    quitadas = 0
    for archivo in carpeta_cache.glob("*.jpg"):
        try:
            archivo.unlink()
            quitadas += 1
        except OSError:
            continue
    return quitadas
