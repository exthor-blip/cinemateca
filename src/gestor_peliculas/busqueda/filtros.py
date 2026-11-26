"""El filtro de busqueda como un objeto, no como seis parametros sueltos.

Los filtros del HTML original vivian en el DOM: refreshFilters() y
matchesFilters() leian el valor de cada <select> directamente. Aca el filtro es
un dato que viaja de la query string al SQL, lo que permite que una busqueda
sea enlazable y quede en el historial del navegador.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from urllib.parse import urlencode


class Orden(StrEnum):
    TITULO = "titulo"
    ANIO_DESC = "anio_desc"
    ANIO_ASC = "anio_asc"
    PUNTAJE = "puntaje"
    AGREGADAS = "agregadas"

    @property
    def etiqueta(self) -> str:
        return {
            "titulo": "Titulo",
            "anio_desc": "Mas nuevas primero",
            "anio_asc": "Mas viejas primero",
            "puntaje": "Mejor puntuadas",
            "agregadas": "Ultimas agregadas",
        }[self.value]


class EstadoFicha(StrEnum):
    TODAS = ""
    PENDIENTES = "pendientes"
    CON_FICHA = "con_ficha"

    @property
    def etiqueta(self) -> str:
        return {
            "": "Todas las fichas",
            "pendientes": "Pendientes",
            "con_ficha": "Con metadatos",
        }[self.value]


@dataclass(frozen=True, slots=True)
class FiltroBusqueda:
    """Todo lo que la persona puede pedirle al catalogo."""

    texto: str = ""
    pais: str = ""
    anio: str = ""
    genero: str = ""
    idioma: str = ""
    ficha: EstadoFicha = EstadoFicha.TODAS
    sin_imdb: bool = False
    ubicacion_id: int | None = None
    orden: Orden = Orden.TITULO
    pagina: int = 1
    por_pagina: int = 60
    agrupar_copias: bool = True

    @property
    def activo(self) -> bool:
        """True si hay algun filtro puesto, para saber si mostrar 'Limpiar'."""
        return bool(
            self.texto or self.pais or self.anio or self.genero or self.idioma
            or self.ficha is not EstadoFicha.TODAS or self.sin_imdb or self.ubicacion_id
        )

    @property
    def desplazamiento(self) -> int:
        return max(0, (max(1, self.pagina) - 1) * self.por_pagina)

    def en_pagina(self, pagina: int) -> FiltroBusqueda:
        return replace(self, pagina=max(1, pagina))

    def limpio(self) -> FiltroBusqueda:
        """El mismo filtro sin ninguna condicion, conservando orden y paginado."""
        return FiltroBusqueda(orden=self.orden, por_pagina=self.por_pagina,
                              agrupar_copias=self.agrupar_copias)

    def como_parametros(self, **cambios: object) -> str:
        """Query string para construir enlaces de paginacion y de filtros."""
        datos = {
            "q": self.texto,
            "pais": self.pais,
            "anio": self.anio,
            "genero": self.genero,
            "idioma": self.idioma,
            "ficha": self.ficha.value,
            "sin_imdb": "1" if self.sin_imdb else "",
            "ubicacion": self.ubicacion_id or "",
            "orden": self.orden.value,
            "pagina": self.pagina,
        }
        datos.update({k: ("" if v is None else v) for k, v in cambios.items()})
        if str(datos.get("pagina")) == "1":
            datos.pop("pagina", None)
        return urlencode({k: v for k, v in datos.items() if v not in ("", None)})

    @classmethod
    def desde_parametros(cls, obtener, *, por_pagina: int = 60) -> FiltroBusqueda:
        """Arma el filtro desde algo con interfaz de dict (request.args de Flask).

        Nunca lanza por un valor raro: un parametro invalido se ignora, que es lo
        que corresponde cuando viene de una URL que alguien pudo editar a mano.
        """
        def texto(clave: str, por_defecto: str = "") -> str:
            return str(obtener(clave, por_defecto) or "").strip()

        def entero(clave: str, por_defecto: int) -> int:
            try:
                return int(texto(clave) or por_defecto)
            except ValueError:
                return por_defecto

        try:
            ficha = EstadoFicha(texto("ficha"))
        except ValueError:
            ficha = EstadoFicha.TODAS
        try:
            orden = Orden(texto("orden") or Orden.TITULO.value)
        except ValueError:
            orden = Orden.TITULO

        ubicacion = entero("ubicacion", 0)
        anio = texto("anio")

        return cls(
            texto=texto("q")[:200],
            pais=texto("pais")[:120],
            anio=anio if anio.isdigit() and len(anio) == 4 else "",
            genero=texto("genero")[:120],
            idioma=texto("idioma")[:120],
            ficha=ficha,
            sin_imdb=texto("sin_imdb") in {"1", "si", "true", "on"},
            ubicacion_id=ubicacion or None,
            orden=orden,
            pagina=max(1, entero("pagina", 1)),
            por_pagina=por_pagina,
        )


@dataclass(slots=True)
class Pagina:
    """Un tramo de resultados mas lo que hace falta para dibujar la paginacion."""

    peliculas: list = field(default_factory=list)
    total: int = 0
    pagina: int = 1
    por_pagina: int = 60

    @property
    def total_paginas(self) -> int:
        if self.por_pagina <= 0:
            return 1
        return max(1, -(-self.total // self.por_pagina))

    @property
    def tiene_anterior(self) -> bool:
        return self.pagina > 1

    @property
    def tiene_siguiente(self) -> bool:
        return self.pagina < self.total_paginas

    @property
    def desde(self) -> int:
        return 0 if not self.total else (self.pagina - 1) * self.por_pagina + 1

    @property
    def hasta(self) -> int:
        return min(self.total, self.pagina * self.por_pagina)

    def ventana(self, radio: int = 2) -> list[int]:
        """Numeros de pagina a mostrar alrededor de la actual."""
        inicio = max(1, self.pagina - radio)
        fin = min(self.total_paginas, self.pagina + radio)
        return list(range(inicio, fin + 1))
