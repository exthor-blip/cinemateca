"""Clasifica las carpetas de una coleccion en las cuatro categorias del original.

Es Analyze() de Organizador_Peliculas.ps1 (lineas 130-193), que llenaba las
cuatro pestanas de la ventana:

  1. **Pares**: un video y uno o dos subtitulos. Se renombran los tres al
     nombre de la carpeta; el segundo subtitulo lleva el sufijo 1.
  2. **Sueltos**: un video y ningun subtitulo.
  3. **Incidencias**: cualquier otra combinacion. No se toca nada: son las
     carpetas ambiguas, y el original tambien las dejaba quietas.
  4. **Extras**: archivos que no son video ni subtitulo, agrupados por
     extension, candidatos a la papelera.

Esta capa solo mira y propone. No renombra ni borra nada.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import registro
from ..catalogo import sidecars
from ..nucleo.extensiones import es_sidecar, es_video
from . import deteccion_subtitulos, renombrador
from .renombrador import misma_ruta_exacta

log = registro.obtener(__name__)

#: Archivos que nunca se tocan ni se ofrecen para borrar.
NOMBRES_PROTEGIDOS = frozenset({
    "organizador_peliculas.ps1", "organizador_peliculas.bat",
    "imdb linker 4.3.ps1", "imdb linker 4.3.bat",
    "imdb.url", "tmdb.url", "poster.jpg", "poster.png", "poster.webp", "folder.jpg",
    "desktop.ini", "thumbs.db", ".ds_store",
    ".imdb_linker_estado.json",
})

#: Carpetas que no se recorren.
CARPETAS_PROTEGIDAS = frozenset({"_informes_organizador", "_informes"})

CARPETA_INFORMES = "_Informes_Organizador"


def esta_protegido(ruta: Path) -> bool:
    """Un archivo protegido no se renombra ni se manda a la papelera."""
    nombre = ruta.name.lower()
    if nombre in NOMBRES_PROTEGIDOS:
        return True
    if nombre.startswith("informe_peliculas_") and nombre.endswith(".csv"):
        return True
    if nombre.startswith("historial_renombramientos_") and nombre.endswith(".csv"):
        return True
    if nombre.startswith(".__organizador_tmp_"):
        return True

    # Cualquier archivo que contenga un identificador IMDb se protege, aunque
    # no se llame imdb.url: un .nfo de Kodi o un acceso directo con otro nombre
    # son la unica copia de ese dato, y el catalogo los lee al indexar.
    # El original no contemplaba esto y los ofrecia para borrar.
    if es_sidecar(ruta.name) and sidecars.leer_imdb_de_archivo(ruta):
        return True
    try:
        atributos = ruta.stat().st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return False
    # FILE_ATTRIBUTE_HIDDEN = 2, FILE_ATTRIBUTE_SYSTEM = 4
    return bool(atributos & 0x2 or atributos & 0x4)


@dataclass(slots=True)
class Par:
    """Una carpeta con un video y uno o dos subtitulos."""

    carpeta: Path
    video: Path
    subtitulos: list[Path]
    destino_video: Path
    destinos_subtitulos: list[Path]
    correcto: bool = False

    @property
    def nombre_carpeta(self) -> str:
        return self.carpeta.name

    @property
    def texto_subtitulos(self) -> str:
        return " | ".join(s.name for s in self.subtitulos)

    @property
    def texto_destinos(self) -> str:
        return " | ".join(d.name for d in self.destinos_subtitulos)

    @property
    def estado(self) -> str:
        return "Correcto" if self.correcto else "Pendiente"

    @property
    def origenes(self) -> list[Path]:
        return [self.video, *self.subtitulos]

    @property
    def destinos(self) -> list[Path]:
        return [self.destino_video, *self.destinos_subtitulos]


@dataclass(slots=True)
class Suelto:
    """Una carpeta con un video y sin subtitulos."""

    carpeta: Path
    video: Path
    destino: Path
    correcto: bool = False

    @property
    def nombre_carpeta(self) -> str:
        return self.carpeta.name

    @property
    def estado(self) -> str:
        return "Correcto" if self.correcto else "Pendiente"


@dataclass(slots=True)
class Incidencia:
    """Una carpeta que no se puede organizar sola."""

    carpeta: Path
    motivo: str
    #: True cuando la carpeta tiene varias peliculas (una saga). No es un
    #: problema: el catalogo las indexa por separado y el organizador las deja
    #: quietas a proposito, porque no se pueden llamar todas igual que su
    #: carpeta. Se marca aparte para no confundirla con una carpeta rota.
    es_saga: bool = False

    @property
    def nombre_carpeta(self) -> str:
        return self.carpeta.name

    @property
    def gravedad(self) -> str:
        return "normal" if self.es_saga else "revisar"


@dataclass(slots=True)
class GrupoExtras:
    """Los archivos sobrantes de una extension, con su peso total."""

    extension: str
    archivos: list[Path] = field(default_factory=list)

    @property
    def cantidad(self) -> int:
        return len(self.archivos)

    @property
    def bytes(self) -> int:
        total = 0
        for archivo in self.archivos:
            try:
                total += archivo.stat().st_size
            except OSError:
                continue
        return total

    @property
    def megabytes(self) -> float:
        return round(self.bytes / (1024 * 1024), 3)


@dataclass(slots=True)
class Analisis:
    """El resultado completo: lo que mostraban las cuatro pestanas."""

    raiz: Path
    carpetas: int = 0
    pares: list[Par] = field(default_factory=list)
    sueltos: list[Suelto] = field(default_factory=list)
    incidencias: list[Incidencia] = field(default_factory=list)
    extras: list[GrupoExtras] = field(default_factory=list)

    @property
    def pares_pendientes(self) -> list[Par]:
        return [p for p in self.pares if not p.correcto]

    @property
    def sueltos_pendientes(self) -> list[Suelto]:
        return [s for s in self.sueltos if not s.correcto]

    @property
    def sagas(self) -> list[Incidencia]:
        """Carpetas con varias peliculas. No son problemas."""
        return [i for i in self.incidencias if i.es_saga]

    @property
    def problemas(self) -> list[Incidencia]:
        """Incidencias de verdad: carpetas que conviene mirar a mano."""
        return [i for i in self.incidencias if not i.es_saga]

    @property
    def total_extras(self) -> int:
        return sum(g.cantidad for g in self.extras)

    @property
    def megabytes_extras(self) -> float:
        return round(sum(g.bytes for g in self.extras) / (1024 * 1024), 2)

    def __str__(self) -> str:
        texto = (f"{self.carpetas} carpetas: {len(self.pares)} pares, "
                 f"{len(self.sueltos)} solo video, {len(self.problemas)} incidencias, "
                 f"{self.total_extras} archivos sueltos")
        if self.sagas:
            texto += f", {len(self.sagas)} carpetas con varias peliculas"
        return texto


def analizar(raiz: Path | str, *, cancelado: Callable[[], bool] | None = None,
             progreso: Callable[[int, str], None] | None = None) -> Analisis:
    """Recorre la coleccion y clasifica cada carpeta. No modifica nada."""
    base = Path(raiz).expanduser()
    analisis = Analisis(raiz=base)
    if not base.is_dir():
        return analisis

    extras_por_extension: dict[str, list[Path]] = {}

    for carpeta in _carpetas(base, cancelado):
        analisis.carpetas += 1
        if progreso and analisis.carpetas % 10 == 0:
            progreso(analisis.carpetas, carpeta.name)

        try:
            archivos = [a for a in carpeta.iterdir() if a.is_file()]
        except (OSError, PermissionError) as error:
            analisis.incidencias.append(
                Incidencia(carpeta, f"No se pudo leer la carpeta: {error}")
            )
            continue

        videos = sorted((a for a in archivos if es_video(a.name)), key=lambda a: a.name.lower())
        subtitulos = sorted(
            (a for a in archivos if deteccion_subtitulos.es_subtitulo(a)),
            key=lambda a: a.name.lower(),
        )

        for archivo in archivos:
            if archivo in videos or archivo in subtitulos or esta_protegido(archivo):
                continue
            clave = archivo.suffix.upper() if archivo.suffix else "(SIN EXTENSION)"
            extras_por_extension.setdefault(clave, []).append(archivo)

        if not videos and not subtitulos:
            continue

        if len(videos) == 1 and 1 <= len(subtitulos) <= 2:
            par = _armar_par(carpeta, videos[0], subtitulos)
            if par is None:
                analisis.incidencias.append(Incidencia(
                    carpeta, "El nombre de destino esta ocupado o se repite entre archivos"
                ))
            else:
                analisis.pares.append(par)
        elif len(videos) == 1 and not subtitulos:
            suelto = _armar_suelto(carpeta, videos[0])
            if suelto is None:
                analisis.incidencias.append(
                    Incidencia(carpeta, "El nombre de destino ya esta ocupado")
                )
            else:
                analisis.sueltos.append(suelto)
        elif len(videos) > 1:
            # Carpeta de saga: son varias peliculas, no una carpeta rota.
            analisis.incidencias.append(Incidencia(
                carpeta,
                f"Carpeta con {len(videos)} peliculas y {len(subtitulos)} subtitulos. "
                "El catalogo las indexa por separado; el organizador no las "
                "renombra porque no pueden llamarse todas igual que la carpeta.",
                es_saga=True,
            ))
        else:
            analisis.incidencias.append(Incidencia(
                carpeta, f"Videos: {len(videos)}; subtitulos: {len(subtitulos)}"
            ))

    analisis.extras = [
        GrupoExtras(extension, archivos)
        for extension, archivos in sorted(extras_por_extension.items())
    ]
    if progreso:
        progreso(analisis.carpetas, "")
    log.info("Analisis de %s: %s", base, analisis)
    return analisis


def _carpetas(base: Path, cancelado: Callable[[], bool] | None) -> list[Path]:
    """La raiz y todas sus subcarpetas, salteando enlaces y carpetas de informes."""
    encontradas = [base]
    pendientes = [base]
    while pendientes:
        if cancelado and cancelado():
            break
        actual = pendientes.pop()
        try:
            with os.scandir(actual) as entradas:
                for entrada in entradas:
                    try:
                        if not entrada.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    if entrada.name.lower() in CARPETAS_PROTEGIDAS:
                        continue
                    hija = Path(entrada.path)
                    encontradas.append(hija)
                    pendientes.append(hija)
        except (OSError, PermissionError) as error:
            log.warning("No se pudo recorrer %s: %s", actual, error)
    return encontradas


def _armar_par(carpeta: Path, video: Path, subtitulos: list[Path]) -> Par | None:
    destino_video = renombrador.nombre_destino(carpeta, video.suffix)
    destinos_subtitulos = []
    for indice, subtitulo in enumerate(subtitulos):
        sufijo = "" if indice == 0 else "1"
        extension = deteccion_subtitulos.extension_para(subtitulo)
        destinos_subtitulos.append(renombrador.nombre_destino(carpeta, extension, sufijo))

    origenes = [video, *subtitulos]
    destinos = [destino_video, *destinos_subtitulos]

    # Dos archivos no pueden terminar con el mismo nombre.
    if len({str(d).lower() for d in destinos}) != len(destinos):
        return None
    if any(renombrador.destino_ocupado(d, origenes) for d in destinos):
        return None

    correcto = all(misma_ruta_exacta(o, d) for o, d in zip(origenes, destinos, strict=True))
    return Par(carpeta, video, subtitulos, destino_video, destinos_subtitulos, correcto)


def _armar_suelto(carpeta: Path, video: Path) -> Suelto | None:
    destino = renombrador.nombre_destino(carpeta, video.suffix)
    if renombrador.destino_ocupado(destino, [video]):
        return None
    return Suelto(carpeta, video, destino, correcto=misma_ruta_exacta(video, destino))
