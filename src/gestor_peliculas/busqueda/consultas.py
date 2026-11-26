"""Traduce un FiltroBusqueda a SQL y devuelve una Pagina de peliculas.

La busqueda de texto usa FTS5 cuando esta disponible, que es el caso en esta
maquina (SQLite 3.45.3). Si faltara, cae a LIKE sobre los mismos campos: mas
lento, pero el catalogo sigue siendo usable.

Nota sobre el original: el HTML filtraba en JavaScript recorriendo todo el
catalogo en cada tecleo. Aca filtra SQLite con indices, asi que la busqueda no
se degrada con el tamanio de la coleccion.
"""

from __future__ import annotations

import re
import sqlite3

from .. import registro
from ..almacenamiento.repositorio_peliculas import SELECT_COMPLETO, RepositorioPeliculas
from ..catalogo import duplicados
from .filtros import EstadoFicha, FiltroBusqueda, Orden, Pagina

log = registro.obtener(__name__)

_RE_PALABRA = re.compile(r"[^\w\s]", re.UNICODE)

_ORDEN_SQL = {
    Orden.TITULO: "COALESCE(NULLIF(m.titulo, ''), p.titulo_carpeta) COLLATE NOCASE ASC",
    Orden.ANIO_DESC: "COALESCE(NULLIF(m.anio, ''), p.anio_carpeta) DESC, p.titulo_carpeta COLLATE NOCASE",
    Orden.ANIO_ASC: "COALESCE(NULLIF(m.anio, ''), p.anio_carpeta) ASC, p.titulo_carpeta COLLATE NOCASE",
    Orden.PUNTAJE: "s.puntaje DESC NULLS LAST, p.titulo_carpeta COLLATE NOCASE",
    Orden.AGREGADAS: "p.id DESC",
}


def preparar_consulta_fts(texto: str) -> str:
    """Convierte lo que escribio la persona en una consulta FTS5 segura.

    FTS5 tiene sintaxis propia (comillas, NEAR, OR, asteriscos) y un texto
    cualquiera puede ser sintaxis invalida y hacer fallar la consulta. Asi que
    se parte en palabras, se descarta la puntuacion y cada palabra se cita y se
    le agrega * para que busque por prefijo: escribir "tibu" encuentra
    "Tiburon", igual que el includes() del HTML.
    """
    limpio = _RE_PALABRA.sub(" ", texto or "")
    palabras = [p for p in limpio.split() if p]
    if not palabras:
        return ""
    return " AND ".join(f'"{p}"*' for p in palabras)


class ConsultaCatalogo:
    """Ejecuta busquedas sobre el catalogo."""

    def __init__(self, conexion: sqlite3.Connection, *, usar_fts: bool = True) -> None:
        self.conexion = conexion
        self.usar_fts = usar_fts
        self._peliculas = RepositorioPeliculas(conexion)

    # ------------------------------------------------------------------ armado

    def _condiciones(self, filtro: FiltroBusqueda) -> tuple[list[str], list[object]]:
        condiciones: list[str] = []
        valores: list[object] = []

        if filtro.texto:
            consulta = preparar_consulta_fts(filtro.texto) if self.usar_fts else ""
            if consulta:
                condiciones.append(
                    "p.id IN (SELECT pelicula_id FROM peliculas_fts "
                    "WHERE peliculas_fts MATCH ?)"
                )
                valores.append(consulta)
            else:
                patron = f"%{filtro.texto}%"
                condiciones.append(
                    "(p.titulo_carpeta LIKE ? OR p.ruta_relativa LIKE ? "
                    "OR COALESCE(m.titulo, '') LIKE ? OR COALESCE(m.titulo_original, '') LIKE ?)"
                )
                valores.extend([patron] * 4)

        for tipo, valor in (("pais", filtro.pais), ("genero", filtro.genero),
                            ("idioma", filtro.idioma)):
            if valor:
                condiciones.append(
                    "p.id IN (SELECT pe.pelicula_id FROM pelicula_etiquetas pe "
                    "JOIN etiquetas e ON e.id = pe.etiqueta_id "
                    "WHERE e.tipo = ? AND e.valor = ?)"
                )
                valores.extend([tipo, valor])

        if filtro.anio:
            condiciones.append("COALESCE(NULLIF(m.anio, ''), p.anio_carpeta) = ?")
            valores.append(filtro.anio)

        if filtro.ficha is EstadoFicha.PENDIENTES:
            condiciones.append("m.pelicula_id IS NULL")
        elif filtro.ficha is EstadoFicha.CON_FICHA:
            condiciones.append("m.pelicula_id IS NOT NULL")

        if filtro.sin_imdb:
            condiciones.append("p.imdb_id = ''")

        if filtro.ubicacion_id:
            condiciones.append("p.ubicacion_id = ?")
            valores.append(filtro.ubicacion_id)

        return condiciones, valores

    @staticmethod
    def _donde(condiciones: list[str]) -> str:
        return (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

    # ---------------------------------------------------------------- consultas

    def contar(self, filtro: FiltroBusqueda) -> int:
        condiciones, valores = self._condiciones(filtro)
        consulta = f"""
            SELECT COUNT(*)
            FROM peliculas p
            JOIN ubicaciones u ON u.id = p.ubicacion_id
            LEFT JOIN metadatos m ON m.pelicula_id = p.id
            LEFT JOIN puntajes_imdb s ON s.imdb_id = p.imdb_id AND p.imdb_id <> ''
            {self._donde(condiciones)}
        """
        return self.conexion.execute(consulta, tuple(valores)).fetchone()[0]

    def buscar(self, filtro: FiltroBusqueda) -> Pagina:
        """Devuelve la pagina de resultados que pide el filtro."""
        condiciones, valores = self._condiciones(filtro)
        orden = _ORDEN_SQL.get(filtro.orden, _ORDEN_SQL[Orden.TITULO])

        if filtro.agrupar_copias:
            # Con agrupado hay que traer todo lo que matchea para poder colapsar
            # copias antes de paginar. Un catalogo personal entra de sobra en
            # memoria; si algun dia no entrara, se agruparia en SQL por imdb_id.
            filas = self.conexion.execute(
                f"{SELECT_COMPLETO}{self._donde(condiciones)} ORDER BY {orden}",
                tuple(valores),
            ).fetchall()
            todas = self._peliculas._hidratar(filas)
            agrupadas = duplicados.unicas(todas)
            total = len(agrupadas)
            inicio = filtro.desplazamiento
            recorte = agrupadas[inicio:inicio + filtro.por_pagina]
            return Pagina(recorte, total, filtro.pagina, filtro.por_pagina)

        total = self.contar(filtro)
        filas = self.conexion.execute(
            f"{SELECT_COMPLETO}{self._donde(condiciones)} ORDER BY {orden} LIMIT ? OFFSET ?",
            (*valores, filtro.por_pagina, filtro.desplazamiento),
        ).fetchall()
        return Pagina(self._peliculas._hidratar(filas), total, filtro.pagina, filtro.por_pagina)

    def ids_que_coinciden(self, filtro: FiltroBusqueda) -> list[int]:
        """Solo los identificadores, para operaciones en lote sobre el resultado."""
        condiciones, valores = self._condiciones(filtro)
        filas = self.conexion.execute(
            f"""
            SELECT p.id
            FROM peliculas p
            JOIN ubicaciones u ON u.id = p.ubicacion_id
            LEFT JOIN metadatos m ON m.pelicula_id = p.id
            LEFT JOIN puntajes_imdb s ON s.imdb_id = p.imdb_id AND p.imdb_id <> ''
            {self._donde(condiciones)}
            """,
            tuple(valores),
        ).fetchall()
        return [f[0] for f in filas]
