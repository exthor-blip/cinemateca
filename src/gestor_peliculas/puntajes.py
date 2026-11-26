"""Importacion de los puntajes del dataset no comercial de IMDb.

Lo que hacia la version anterior: `title.ratings.tsv.gz` (unos 25 MB) venia
codificado en base64 dentro de `Mi_Cinemateca_Puntajes_IMDb.js`, un archivo de
11,7 MB que el navegador cargaba entero, descomprimia con DecompressionStream y
recorria linea por linea para sacar unos pocos puntajes. Y lo volvia a recorrer
cada vez que aparecian identificadores nuevos en el catalogo.

Lo que hace esta version: el .tsv.gz se lee UNA vez en streaming, sin cargarlo
en memoria, y las filas van a la tabla `puntajes_imdb`. Despues cada consulta
es un indice de SQLite. La estrella de la tarjeta sale de un JOIN.

Se respetan los filtros del original: solo se acepta la cabecera oficial, y una
fila cuenta si el puntaje esta entre 1 y 10 y tiene al menos un voto.
"""

from __future__ import annotations

import csv
import gzip
import io
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from . import registro
from .almacenamiento.bd import BaseDatos
from .errores import ErrorDominio
from .nucleo.identificadores import RE_IMDB_ID

log = registro.obtener(__name__)

URL_DATASET = "https://datasets.imdbws.com/title.ratings.tsv.gz"
CABECERA = ("tconst", "averageRating", "numVotes")
NOMBRE_ARCHIVO = "title.ratings.tsv.gz"

#: Cuantas filas se escriben por transaccion. 20.000 va holgado de memoria y
#: hace que el millon y medio de filas entre en pocos segundos.
TAMANIO_LOTE = 20_000


@dataclass(slots=True)
class ResultadoImportacion:
    leidas: int = 0
    guardadas: int = 0
    descartadas: int = 0

    def __str__(self) -> str:
        return (f"{self.leidas} filas leidas, {self.guardadas} puntajes guardados, "
                f"{self.descartadas} descartadas por puntaje o votos invalidos")


def _abrir(ruta: Path) -> io.TextIOWrapper:
    """Abre el .tsv.gz o el .tsv como texto, en streaming."""
    if ruta.suffix.lower() == ".gz":
        return io.TextIOWrapper(gzip.open(ruta, "rb"), encoding="utf-8", newline="")
    return ruta.open("r", encoding="utf-8", newline="")


def _filas(ruta: Path) -> Iterator[tuple[str, float, int]]:
    """Recorre el archivo devolviendo las filas validas.

    Exige la cabecera exacta del archivo oficial, igual que importRatings() del
    HTML: si alguien elige otro de los datasets de IMDb por error, conviene
    decirselo en lugar de importar basura.
    """
    with _abrir(ruta) as entrada:
        lector = csv.reader(entrada, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            cabecera = next(lector)
        except StopIteration:
            raise ErrorDominio("El archivo de puntajes esta vacio.") from None

        if tuple(c.strip() for c in cabecera[:3]) != CABECERA:
            raise ErrorDominio(
                "Ese no es el archivo title.ratings.tsv.gz de IMDb. "
                "Se descarga de https://datasets.imdbws.com/title.ratings.tsv.gz"
            )

        for fila in lector:
            if len(fila) < 3:
                continue
            imdb_id = fila[0].strip().lower()
            if not RE_IMDB_ID.match(imdb_id):
                continue
            try:
                puntaje = float(fila[1])
                votos = int(fila[2])
            except ValueError:
                continue
            yield imdb_id, puntaje, votos


def importar(bd: BaseDatos, archivo: Path | str, *,
             solo_estos: set[str] | None = None,
             cancelado: Callable[[], bool] | None = None,
             progreso: Callable[[int, int], None] | None = None) -> ResultadoImportacion:
    """Carga los puntajes del archivo en la base.

    Args:
        bd: base abierta.
        archivo: ruta al title.ratings.tsv.gz (o al .tsv descomprimido).
        solo_estos: si se pasa, guarda unicamente los identificadores de ese
            conjunto. Sirve para una base chica; por defecto se importa todo,
            asi las peliculas que se agreguen despues ya tienen su puntaje.
        cancelado: funcion que devuelve True para abandonar.
        progreso: recibe (filas_leidas, filas_guardadas) cada lote.

    Returns:
        ResultadoImportacion con los conteos.
    """
    ruta = Path(archivo).expanduser()
    if not ruta.is_file():
        raise ErrorDominio(f"No existe el archivo {ruta}.")

    resultado = ResultadoImportacion()
    lote: list[tuple[str, float, int]] = []

    for imdb_id, puntaje, votos in _filas(ruta):
        if cancelado and cancelado():
            break
        resultado.leidas += 1

        if solo_estos is not None and imdb_id not in solo_estos:
            continue
        # Los mismos limites que aplicaba el original.
        if not (1.0 <= puntaje <= 10.0) or votos <= 0:
            resultado.descartadas += 1
            continue

        lote.append((imdb_id, puntaje, votos))

        if len(lote) >= TAMANIO_LOTE:
            resultado.guardadas += bd.puntajes.guardar_lote(lote)
            bd.conexion.commit()
            lote.clear()
            if progreso:
                progreso(resultado.leidas, resultado.guardadas)

    if lote:
        resultado.guardadas += bd.puntajes.guardar_lote(lote)
        bd.conexion.commit()
    if progreso:
        progreso(resultado.leidas, resultado.guardadas)

    log.info("Importacion de puntajes: %s", resultado)
    return resultado


def descargar(carpeta_destino: Path, *, url: str = URL_DATASET) -> Path:
    """Descarga el dataset oficial de IMDb a la carpeta indicada.

    Es un archivo publico de los IMDb Non-Commercial Datasets. Las condiciones
    de uso estan en https://developer.imdb.com/non-commercial-datasets/
    """
    from .metadatos.sesion_http import sesion_compartida

    carpeta_destino.mkdir(parents=True, exist_ok=True)
    destino = carpeta_destino / NOMBRE_ARCHIVO
    datos = sesion_compartida().descargar(url, fuente="IMDb Datasets",
                                         tamanio_maximo=120 * 1024 * 1024)
    temporal = destino.with_suffix(".parcial")
    temporal.write_bytes(datos)
    temporal.replace(destino)
    log.info("Dataset de puntajes descargado en %s (%s bytes)", destino, len(datos))
    return destino


def archivo_local(carpeta_datos: Path) -> Path | None:
    """El dataset ya descargado, si esta."""
    candidato = carpeta_datos / NOMBRE_ARCHIVO
    return candidato if candidato.is_file() else None
