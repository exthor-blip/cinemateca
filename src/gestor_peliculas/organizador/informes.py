"""Informes CSV del organizador.

Mantiene los dos archivos que generaba SaveReports() del original, con los
mismos nombres, columnas y separador, para que los informes viejos y los nuevos
se puedan abrir igual y comparar:

  - Informe_Peliculas_<marca>.csv   -> Carpeta;Categoria;Estado;Detalle
  - Historial_Renombramientos_<marca>.csv -> Fecha;Accion;Origen;Destino;Estado;Detalle

Separador punto y coma y codificacion UTF-8 con BOM, que es lo que necesita
Excel en castellano para abrir el archivo con las columnas separadas y las
tildes bien.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import registro
from .analizador import CARPETA_INFORMES, Analisis
from .renombrador import Operacion

log = registro.obtener(__name__)

SEPARADOR = ";"
CODIFICACION = "utf-8-sig"

CABECERA_INFORME = ("Carpeta", "Categoria", "Estado", "Detalle")
CABECERA_HISTORIAL = ("Fecha", "Accion", "Origen", "Destino", "Estado", "Detalle")


@dataclass(slots=True)
class Asiento:
    """Una linea del historial."""

    fecha: str
    accion: str
    origen: str
    destino: str
    estado: str
    detalle: str = ""

    def como_fila(self) -> tuple[str, ...]:
        return (self.fecha, self.accion, self.origen, self.destino, self.estado, self.detalle)


@dataclass(slots=True)
class Historial:
    """Acumula lo que se fue haciendo, para volcarlo al CSV."""

    asientos: list[Asiento] = field(default_factory=list)

    def anotar(self, accion: str, origen: Path | str, destino: Path | str = "",
               estado: str = "OK", detalle: str = "") -> None:
        self.asientos.append(Asiento(
            fecha=datetime.now().replace(microsecond=0).isoformat(),
            accion=accion,
            origen=str(origen),
            destino=str(destino),
            estado=estado,
            detalle=detalle,
        ))

    def anotar_operacion(self, accion: str, operacion: Operacion) -> None:
        self.anotar(
            accion, operacion.origen, operacion.destino,
            "OK" if operacion.resultado.exitoso else "ERROR",
            operacion.detalle or operacion.resultado.etiqueta,
        )

    def __len__(self) -> int:
        return len(self.asientos)


def _marca() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def carpeta_de_informes(raiz: Path, *, alternativa: Path | None = None) -> Path:
    """La carpeta donde escribir, creandola si falta.

    Se intenta junto a la coleccion, como hacia el original. Si no se puede
    escribir ahi (un disco de solo lectura, por ejemplo) se usa la alternativa
    en la carpeta de datos de la aplicacion, en lugar de perder el informe.
    """
    destino = raiz / CARPETA_INFORMES
    try:
        destino.mkdir(parents=True, exist_ok=True)
        prueba = destino / ".escritura"
        prueba.write_text("", encoding="utf-8")
        prueba.unlink()
        return destino
    except OSError:
        if alternativa is None:
            raise
        log.info("No se puede escribir en %s; el informe va a %s", destino, alternativa)
        alternativa.mkdir(parents=True, exist_ok=True)
        return alternativa


def _escribir(ruta: Path, cabecera: tuple[str, ...], filas) -> None:
    with ruta.open("w", encoding=CODIFICACION, newline="") as salida:
        escritor = csv.writer(salida, delimiter=SEPARADOR, quoting=csv.QUOTE_MINIMAL)
        escritor.writerow(cabecera)
        escritor.writerows(filas)


def guardar(analisis: Analisis, historial: Historial, *,
            alternativa: Path | None = None) -> tuple[Path, Path]:
    """Escribe el informe y el historial. Devuelve las dos rutas."""
    carpeta = carpeta_de_informes(analisis.raiz, alternativa=alternativa)
    marca = _marca()

    ruta_informe = carpeta / f"Informe_Peliculas_{marca}.csv"
    filas = []
    for par in analisis.pares:
        filas.append((str(par.carpeta), "Par", par.estado,
                      f"{par.video.name} | {par.texto_subtitulos}"))
    for suelto in analisis.sueltos:
        filas.append((str(suelto.carpeta), "Solo video", suelto.estado, suelto.video.name))
    for incidencia in analisis.incidencias:
        filas.append((str(incidencia.carpeta), "Incidencia", "REVISAR", incidencia.motivo))
    for grupo in analisis.extras:
        filas.append((str(analisis.raiz), "Archivos sueltos", "REVISAR",
                      f"{grupo.extension}: {grupo.cantidad} archivos, {grupo.megabytes} MB"))
    _escribir(ruta_informe, CABECERA_INFORME, filas)

    ruta_historial = carpeta / f"Historial_Renombramientos_{marca}.csv"
    _escribir(ruta_historial, CABECERA_HISTORIAL,
              (a.como_fila() for a in historial.asientos))

    log.info("Informes guardados en %s", carpeta)
    return ruta_informe, ruta_historial


def listar(raiz: Path) -> list[dict]:
    """Los informes ya existentes de una coleccion, del mas nuevo al mas viejo."""
    carpeta = raiz / CARPETA_INFORMES
    if not carpeta.is_dir():
        return []
    encontrados = []
    for archivo in carpeta.glob("*.csv"):
        try:
            estado = archivo.stat()
        except OSError:
            continue
        encontrados.append({
            "nombre": archivo.name,
            "ruta": str(archivo),
            "bytes": estado.st_size,
            "modificado": datetime.fromtimestamp(estado.st_mtime).isoformat(sep=" ", timespec="seconds"),
        })
    return sorted(encontrados, key=lambda i: i["modificado"], reverse=True)
