"""Objetos de dominio.

Son dataclasses sin comportamiento de infraestructura: no saben de SQL, de HTTP
ni de Flask. Los repositorios los construyen desde filas y los servicios los
devuelven a la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class EstadoRevision(StrEnum):
    """Estado del enlazado de una pelicula con su ficha externa.

    Reemplaza los estados sueltos del linker ('Pendiente', 'Buscando',
    'Revisar', 'Completada', 'Sin poster', 'No encontrada', 'Rechazada',
    'Error'), unificando los que significaban lo mismo.
    """

    PENDIENTE = "pendiente"
    REVISAR = "revisar"
    COMPLETADA = "completada"
    SIN_COINCIDENCIA = "sin_coincidencia"
    ERROR = "error"

    @property
    def etiqueta(self) -> str:
        return {
            "pendiente": "Pendiente",
            "revisar": "Para revisar",
            "completada": "Completada",
            "sin_coincidencia": "Sin coincidencia",
            "error": "Error",
        }[self.value]


@dataclass(slots=True)
class Ubicacion:
    """Una carpeta raiz de la coleccion. Equivale a un 'source' del HTML original."""

    id: int | None = None
    nombre: str = ""
    ruta: Path = field(default_factory=Path)
    agregada_en: str = ""
    ultimo_escaneo: str | None = None
    cantidad_peliculas: int = 0

    @property
    def existe(self) -> bool:
        try:
            return self.ruta.is_dir()
        except OSError:
            return False


@dataclass(slots=True)
class Metadatos:
    """Ficha de TMDb. Los campos de lista llegan ya normalizados y deduplicados."""

    tmdb_id: int | None = None
    titulo: str = ""
    titulo_original: str = ""
    anio: str = ""
    paises: list[str] = field(default_factory=list)
    generos: list[str] = field(default_factory=list)
    idiomas: list[str] = field(default_factory=list)
    director: str = ""
    duracion_min: int | None = None
    sinopsis: str = ""
    idiomas_verificados: bool = False
    actualizado_en: str = ""

    @property
    def completos(self) -> bool:
        """True cuando no vale la pena volver a consultar TMDb.

        Replica needsMetadata() del HTML: una ficha con las tres listas vacias y
        sin la marca de idiomas verificados se considera incompleta.
        """
        if self.idiomas_verificados:
            return True
        return bool(self.paises and self.generos and self.idiomas)


@dataclass(slots=True)
class Puntaje:
    """Puntaje del dataset no comercial de IMDb."""

    imdb_id: str = ""
    puntaje: float = 0.0
    votos: int = 0

    @property
    def texto(self) -> str:
        """Formato argentino: 7,2/10."""
        return f"{self.puntaje:.1f}".replace(".", ",") + "/10"


@dataclass(slots=True)
class Pelicula:
    """Una pelicula del catalogo: una carpeta con exactamente un video."""

    id: int | None = None
    ubicacion_id: int | None = None
    ubicacion_nombre: str = ""
    ubicacion_ruta: Path | None = None
    ruta_relativa: str = ""
    archivo_video: str = ""
    titulo_carpeta: str = ""
    anio_carpeta: str = ""
    imdb_id: str = ""
    poster_relativo: str = ""
    tamanio_bytes: int = 0
    metadatos: Metadatos | None = None
    puntaje: Puntaje | None = None
    estado_revision: EstadoRevision = EstadoRevision.PENDIENTE
    detalle_revision: str = ""

    @property
    def titulo(self) -> str:
        """Titulo a mostrar: el de TMDb si hay ficha, si no el de la carpeta."""
        if self.metadatos and self.metadatos.titulo:
            return self.metadatos.titulo
        return self.titulo_carpeta

    @property
    def anio(self) -> str:
        if self.metadatos and self.metadatos.anio:
            return self.metadatos.anio
        return self.anio_carpeta

    @property
    def enlace_imdb(self) -> str:
        if self.imdb_id:
            return f"https://www.imdb.com/title/{self.imdb_id}/"
        consulta = self.titulo or self.archivo_video
        from urllib.parse import urlencode

        return "https://www.imdb.com/find/?" + urlencode({"q": consulta, "s": "tt"})

    @property
    def carpeta_absoluta(self) -> Path | None:
        if self.ubicacion_ruta is None:
            return None
        return self.ubicacion_ruta / self.ruta_relativa if self.ruta_relativa else self.ubicacion_ruta

    @property
    def video_absoluto(self) -> Path | None:
        carpeta = self.carpeta_absoluta
        return carpeta / self.archivo_video if carpeta else None

    @property
    def poster_absoluto(self) -> Path | None:
        carpeta = self.carpeta_absoluta
        if carpeta is None or not self.poster_relativo:
            return None
        return carpeta / self.poster_relativo

    @property
    def tiene_ficha(self) -> bool:
        return self.metadatos is not None

    @property
    def necesita_metadatos(self) -> bool:
        return self.metadatos is None or not self.metadatos.completos


@dataclass(slots=True)
class Candidato:
    """Una coincidencia propuesta por una fuente externa, antes de confirmarse."""

    imdb_id: str = ""
    tmdb_id: int | None = None
    titulo: str = ""
    titulo_original: str = ""
    anio: str = ""
    poster_url: str = ""
    fuente: str = ""
    nota: str = ""
    #: Titulos alternativos que trajo la fuente (los akas de IMDb, los alias de
    #: Wikidata). Permiten reconocer que "Tiburon" y "Jaws" son la misma.
    titulos_alternativos: list[str] = field(default_factory=list)

    @property
    def enlace(self) -> str:
        if self.imdb_id:
            return f"https://www.imdb.com/title/{self.imdb_id}/"
        if self.tmdb_id:
            return f"https://www.themoviedb.org/movie/{self.tmdb_id}"
        return ""


@dataclass(slots=True)
class ResumenIndexado:
    """Lo que devuelve un indexado, para informarlo en pantalla."""

    carpetas_examinadas: int = 0
    peliculas_nuevas: int = 0
    peliculas_actualizadas: int = 0
    peliculas_eliminadas: int = 0
    #: Peliculas que comparten carpeta con otra (carpetas de saga, o videos
    #: sueltos). No son duplicados: son peliculas distintas en la misma carpeta.
    en_carpeta_compartida: int = 0
    sin_video: int = 0

    @property
    def total(self) -> int:
        return self.peliculas_nuevas + self.peliculas_actualizadas

    def __str__(self) -> str:
        texto = (
            f"{self.carpetas_examinadas} carpetas examinadas; {self.total} peliculas "
            f"({self.peliculas_nuevas} nuevas, {self.peliculas_actualizadas} actualizadas, "
            f"{self.peliculas_eliminadas} dadas de baja)"
        )
        if self.en_carpeta_compartida:
            texto += f"; {self.en_carpeta_compartida} comparten carpeta con otra"
        return texto


def ahora() -> str:
    """Marca de tiempo ISO sin microsegundos, para guardar en la base."""
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")
