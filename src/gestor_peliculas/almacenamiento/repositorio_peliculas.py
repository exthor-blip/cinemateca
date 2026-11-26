"""Acceso a la tabla de peliculas, con su ficha, puntaje y estado de revision.

Es el unico lugar que sabe armar un modelos.Pelicula completo desde la base, y
el unico que sincroniza el indice de texto peliculas_fts.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..modelos import EstadoRevision, Metadatos, Pelicula, Puntaje, ahora

#: SELECT que trae la pelicula con todo lo que cuelga de ella.
SELECT_COMPLETO = """
SELECT
    p.id, p.ubicacion_id, p.ruta_relativa, p.archivo_video, p.titulo_carpeta,
    p.anio_carpeta, p.imdb_id, p.poster_relativo, p.tamanio_bytes,
    u.nombre AS ubicacion_nombre, u.ruta AS ubicacion_ruta,
    m.tmdb_id, m.titulo AS meta_titulo, m.titulo_original, m.anio AS meta_anio,
    m.director, m.duracion_min, m.sinopsis, m.idiomas_verificados, m.actualizado_en,
    r.estado AS revision_estado, r.detalle AS revision_detalle,
    s.puntaje, s.votos
FROM peliculas p
JOIN ubicaciones u ON u.id = p.ubicacion_id
LEFT JOIN metadatos m ON m.pelicula_id = p.id
LEFT JOIN revisiones r ON r.pelicula_id = p.id
LEFT JOIN puntajes_imdb s ON s.imdb_id = p.imdb_id AND p.imdb_id <> ''
"""

_TIPOS_ETIQUETA = ("pais", "genero", "idioma")


def fila_a_pelicula(fila: sqlite3.Row, etiquetas: dict[str, list[str]] | None = None) -> Pelicula:
    """Construye una Pelicula desde una fila de SELECT_COMPLETO."""
    claves = fila.keys()
    metadatos = None
    if "meta_titulo" in claves and fila["actualizado_en"] is not None:
        etiq = etiquetas or {}
        metadatos = Metadatos(
            tmdb_id=fila["tmdb_id"],
            titulo=fila["meta_titulo"] or "",
            titulo_original=fila["titulo_original"] or "",
            anio=fila["meta_anio"] or "",
            paises=etiq.get("pais", []),
            generos=etiq.get("genero", []),
            idiomas=etiq.get("idioma", []),
            director=fila["director"] or "",
            duracion_min=fila["duracion_min"],
            sinopsis=fila["sinopsis"] or "",
            idiomas_verificados=bool(fila["idiomas_verificados"]),
            actualizado_en=fila["actualizado_en"] or "",
        )

    puntaje = None
    if "puntaje" in claves and fila["puntaje"] is not None:
        puntaje = Puntaje(imdb_id=fila["imdb_id"], puntaje=fila["puntaje"], votos=fila["votos"] or 0)

    # Si no hay fila de revision, el estado se deduce de los datos: una
    # pelicula con ficha y enlace esta completa, aunque nadie lo haya anotado.
    # Asi el estado no puede quedar desfasado de la realidad.
    estado = (EstadoRevision.COMPLETADA
              if metadatos is not None and (fila["imdb_id"] or "")
              else EstadoRevision.PENDIENTE)
    if "revision_estado" in claves and fila["revision_estado"]:
        try:
            estado = EstadoRevision(fila["revision_estado"])
        except ValueError:
            pass

    return Pelicula(
        id=fila["id"],
        ubicacion_id=fila["ubicacion_id"],
        ubicacion_nombre=fila["ubicacion_nombre"],
        ubicacion_ruta=Path(fila["ubicacion_ruta"]),
        ruta_relativa=fila["ruta_relativa"],
        archivo_video=fila["archivo_video"],
        titulo_carpeta=fila["titulo_carpeta"],
        anio_carpeta=fila["anio_carpeta"] or "",
        imdb_id=fila["imdb_id"] or "",
        poster_relativo=fila["poster_relativo"] or "",
        tamanio_bytes=fila["tamanio_bytes"] or 0,
        metadatos=metadatos,
        puntaje=puntaje,
        estado_revision=estado,
        detalle_revision=(fila["revision_detalle"] or "") if "revision_detalle" in claves else "",
    )


class RepositorioPeliculas:
    def __init__(self, conexion: sqlite3.Connection) -> None:
        self.conexion = conexion

    # ------------------------------------------------------------------ lectura

    def obtener(self, pelicula_id: int) -> Pelicula | None:
        fila = self.conexion.execute(f"{SELECT_COMPLETO} WHERE p.id = ?", (pelicula_id,)).fetchone()
        if not fila:
            return None
        return fila_a_pelicula(fila, self.etiquetas_de(pelicula_id))

    def obtener_por_ruta(self, ubicacion_id: int, ruta_relativa: str,
                         archivo_video: str = "") -> Pelicula | None:
        """La pelicula de una carpeta.

        Una carpeta puede tener varios videos, y entonces hay varias peliculas:
        `archivo_video` elige cual. Sin ese dato devuelve la primera, que es lo
        util cuando la carpeta tiene un solo video (el caso habitual).
        """
        consulta = f"{SELECT_COMPLETO} WHERE p.ubicacion_id = ? AND p.ruta_relativa = ?"
        valores: tuple = (ubicacion_id, ruta_relativa)
        if archivo_video:
            consulta += " AND p.archivo_video = ?"
            valores = (*valores, archivo_video)
        fila = self.conexion.execute(
            consulta + " ORDER BY p.archivo_video LIMIT 1", valores
        ).fetchone()
        if not fila:
            return None
        return fila_a_pelicula(fila, self.etiquetas_de(fila["id"]))

    def listar_por_ubicacion(self, ubicacion_id: int) -> list[Pelicula]:
        filas = self.conexion.execute(
            f"{SELECT_COMPLETO} WHERE p.ubicacion_id = ? ORDER BY p.ruta_relativa", (ubicacion_id,)
        ).fetchall()
        return self._hidratar(filas)

    def listar_todas(self) -> list[Pelicula]:
        filas = self.conexion.execute(
            f"{SELECT_COMPLETO} ORDER BY p.titulo_carpeta COLLATE NOCASE"
        ).fetchall()
        return self._hidratar(filas)

    def contar(self) -> int:
        return self.conexion.execute("SELECT COUNT(*) FROM peliculas").fetchone()[0]

    def contar_sin_imdb(self) -> int:
        return self.conexion.execute(
            "SELECT COUNT(*) FROM peliculas WHERE imdb_id = ''"
        ).fetchone()[0]

    def contar_con_ficha(self) -> int:
        return self.conexion.execute("SELECT COUNT(*) FROM metadatos").fetchone()[0]

    def ids_con_imdb(self) -> set[str]:
        filas = self.conexion.execute(
            "SELECT DISTINCT imdb_id FROM peliculas WHERE imdb_id <> ''"
        ).fetchall()
        return {f[0] for f in filas}

    def pendientes_de_metadatos(self, limite: int | None = None) -> list[Pelicula]:
        """Peliculas sin ficha o con ficha incompleta, en orden de titulo.

        Replica el filtro de enrich() del HTML: hace falta un ID IMDb o un
        titulo y anio con los que poder buscar.
        """
        consulta = f"""
            {SELECT_COMPLETO}
            WHERE m.pelicula_id IS NULL OR m.idiomas_verificados = 0
            ORDER BY p.titulo_carpeta COLLATE NOCASE
        """
        if limite:
            consulta += f" LIMIT {int(limite)}"
        filas = self.conexion.execute(consulta).fetchall()
        return [p for p in self._hidratar(filas) if p.necesita_metadatos]

    def _hidratar(self, filas: Sequence[sqlite3.Row]) -> list[Pelicula]:
        """Convierte filas a Peliculas trayendo las etiquetas en una sola consulta."""
        if not filas:
            return []
        ids = [f["id"] for f in filas]
        etiquetas = self.etiquetas_de_varias(ids)
        return [fila_a_pelicula(f, etiquetas.get(f["id"], {})) for f in filas]

    # ---------------------------------------------------------------- etiquetas

    def etiquetas_de(self, pelicula_id: int) -> dict[str, list[str]]:
        return self.etiquetas_de_varias([pelicula_id]).get(pelicula_id, {})

    def etiquetas_de_varias(self, ids: Sequence[int]) -> dict[int, dict[str, list[str]]]:
        if not ids:
            return {}
        marcas = ",".join("?" * len(ids))
        filas = self.conexion.execute(
            f"""
            SELECT pe.pelicula_id, e.tipo, e.valor
            FROM pelicula_etiquetas pe
            JOIN etiquetas e ON e.id = pe.etiqueta_id
            WHERE pe.pelicula_id IN ({marcas})
            ORDER BY e.valor COLLATE NOCASE
            """,
            tuple(ids),
        ).fetchall()
        resultado: dict[int, dict[str, list[str]]] = {}
        for fila in filas:
            resultado.setdefault(fila["pelicula_id"], {}).setdefault(fila["tipo"], []).append(
                fila["valor"]
            )
        return resultado

    def _id_etiqueta(self, tipo: str, valor: str) -> int:
        self.conexion.execute(
            "INSERT OR IGNORE INTO etiquetas (tipo, valor) VALUES (?, ?)", (tipo, valor)
        )
        fila = self.conexion.execute(
            "SELECT id FROM etiquetas WHERE tipo = ? AND valor = ?", (tipo, valor)
        ).fetchone()
        return fila["id"]

    def reemplazar_etiquetas(self, pelicula_id: int, etiquetas: dict[str, Iterable[str]]) -> None:
        self.conexion.execute("DELETE FROM pelicula_etiquetas WHERE pelicula_id = ?", (pelicula_id,))
        for tipo in _TIPOS_ETIQUETA:
            for valor in etiquetas.get(tipo, ()) or ():
                limpio = str(valor).strip()
                if limpio:
                    self.conexion.execute(
                        "INSERT OR IGNORE INTO pelicula_etiquetas (pelicula_id, etiqueta_id) "
                        "VALUES (?, ?)",
                        (pelicula_id, self._id_etiqueta(tipo, limpio)),
                    )

    # ------------------------------------------------------------------ escritura

    def alta_o_actualizacion(self, ubicacion_id: int, ruta_relativa: str, *,
                             archivo_video: str, titulo_carpeta: str, anio_carpeta: str = "",
                             imdb_id: str = "", poster_relativo: str = "",
                             tamanio_bytes: int = 0) -> tuple[int, bool]:
        """Inserta o actualiza una pelicula. Devuelve (id, era_nueva).

        Un re-indexado no debe perder el ID IMDb ya conocido: si el escaneo no
        encuentra sidecar pero la base ya tenia un ID, se conserva.
        """
        fila = self.conexion.execute(
            "SELECT id, imdb_id, poster_relativo FROM peliculas "
            "WHERE ubicacion_id = ? AND ruta_relativa = ? AND archivo_video = ?",
            (ubicacion_id, ruta_relativa, archivo_video),
        ).fetchone()

        if fila is None:
            cursor = self.conexion.execute(
                """
                INSERT INTO peliculas
                    (ubicacion_id, ruta_relativa, archivo_video, titulo_carpeta,
                     anio_carpeta, imdb_id, poster_relativo, tamanio_bytes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ubicacion_id, ruta_relativa, archivo_video, titulo_carpeta,
                 anio_carpeta, imdb_id, poster_relativo, tamanio_bytes),
            )
            nuevo_id = int(cursor.lastrowid)
            self._sincronizar_fts(nuevo_id)
            return nuevo_id, True

        pelicula_id = int(fila["id"])
        self.conexion.execute(
            """
            UPDATE peliculas
               SET archivo_video = ?, titulo_carpeta = ?, anio_carpeta = ?,
                   imdb_id = ?, poster_relativo = ?, tamanio_bytes = ?
             WHERE id = ?
            """,
            (archivo_video, titulo_carpeta, anio_carpeta,
             imdb_id or fila["imdb_id"] or "",
             poster_relativo or fila["poster_relativo"] or "",
             tamanio_bytes, pelicula_id),
        )
        self._sincronizar_fts(pelicula_id)
        return pelicula_id, False

    def fijar_imdb_id(self, pelicula_id: int, imdb_id: str) -> None:
        self.conexion.execute(
            "UPDATE peliculas SET imdb_id = ? WHERE id = ?", (imdb_id or "", pelicula_id)
        )
        self.conexion.commit()

    def fijar_poster(self, pelicula_id: int, poster_relativo: str) -> None:
        self.conexion.execute(
            "UPDATE peliculas SET poster_relativo = ? WHERE id = ?",
            (poster_relativo or "", pelicula_id),
        )
        self.conexion.commit()

    def baja_varias(self, ids: Sequence[int]) -> int:
        """Da de baja peliculas del indice. No borra nada del disco."""
        if not ids:
            return 0
        for pelicula_id in ids:
            self.conexion.execute("DELETE FROM peliculas_fts WHERE pelicula_id = ?", (pelicula_id,))
        marcas = ",".join("?" * len(ids))
        self.conexion.execute(f"DELETE FROM peliculas WHERE id IN ({marcas})", tuple(ids))
        self.conexion.commit()
        return len(ids)

    # ------------------------------------------------------------------- revision

    def estado_revision(self, pelicula_id: int) -> dict:
        fila = self.conexion.execute(
            "SELECT * FROM revisiones WHERE pelicula_id = ?", (pelicula_id,)
        ).fetchone()
        if not fila:
            return {"estado": EstadoRevision.PENDIENTE.value, "detalle": "", "rechazados": []}
        datos = dict(fila)
        try:
            datos["rechazados"] = json.loads(datos.pop("candidatos_rechazados") or "[]")
        except (ValueError, TypeError):
            datos["rechazados"] = []
        return datos

    def guardar_revision(self, pelicula_id: int, estado: EstadoRevision, *, detalle: str = "",
                         candidato_id: str = "", candidato_titulo: str = "",
                         candidato_anio: str = "", candidato_poster: str = "",
                         rechazados: Iterable[str] | None = None) -> None:
        anteriores = self.estado_revision(pelicula_id).get("rechazados", [])
        lista = list(dict.fromkeys([*anteriores, *(rechazados or [])]))
        self.conexion.execute(
            """
            INSERT INTO revisiones
                (pelicula_id, estado, detalle, candidato_id, candidato_titulo,
                 candidato_anio, candidato_poster, candidatos_rechazados, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pelicula_id) DO UPDATE SET
                estado = excluded.estado,
                detalle = excluded.detalle,
                candidato_id = excluded.candidato_id,
                candidato_titulo = excluded.candidato_titulo,
                candidato_anio = excluded.candidato_anio,
                candidato_poster = excluded.candidato_poster,
                candidatos_rechazados = excluded.candidatos_rechazados,
                actualizado_en = excluded.actualizado_en
            """,
            (pelicula_id, estado.value, detalle, candidato_id, candidato_titulo,
             candidato_anio, candidato_poster, json.dumps(lista), ahora()),
        )
        self.conexion.commit()

    def rechazar_candidato(self, pelicula_id: int, imdb_id: str) -> None:
        """Recuerda un candidato descartado para no volver a ofrecerlo."""
        if not imdb_id:
            return
        estado = self.estado_revision(pelicula_id)
        self.guardar_revision(
            pelicula_id,
            EstadoRevision.PENDIENTE,
            detalle="Candidato rechazado; se volvera a buscar.",
            rechazados=[*estado.get("rechazados", []), imdb_id],
        )

    # ------------------------------------------------------------------------ fts

    def _sincronizar_fts(self, pelicula_id: int) -> None:
        """Rehace la fila del indice de texto de una pelicula.

        Se llama tras cualquier cambio de titulo, ruta o ficha. Junta el titulo
        de la carpeta y el de TMDb, asi buscar "Jaws" encuentra "1975 - Tiburon".
        """
        fila = self.conexion.execute(
            """
            SELECT p.titulo_carpeta, p.ruta_relativa, p.archivo_video, p.anio_carpeta,
                   COALESCE(m.titulo, '') AS meta_titulo,
                   COALESCE(m.titulo_original, '') AS meta_original
            FROM peliculas p
            LEFT JOIN metadatos m ON m.pelicula_id = p.id
            WHERE p.id = ?
            """,
            (pelicula_id,),
        ).fetchone()
        if fila is None:
            return

        titulos = " ".join(dict.fromkeys(
            t for t in (fila["titulo_carpeta"], fila["meta_titulo"]) if t
        ))
        self.conexion.execute("DELETE FROM peliculas_fts WHERE pelicula_id = ?", (pelicula_id,))
        self.conexion.execute(
            "INSERT INTO peliculas_fts (pelicula_id, titulo, titulo_original, ruta) "
            "VALUES (?, ?, ?, ?)",
            (
                pelicula_id,
                f"{titulos} {fila['anio_carpeta']}".strip(),
                fila["meta_original"],
                f"{fila['ruta_relativa']} {fila['archivo_video']}".strip(),
            ),
        )

    def reconstruir_fts(self) -> int:
        """Rehace el indice de texto completo. Util tras una importacion masiva."""
        self.conexion.execute("DELETE FROM peliculas_fts")
        ids = [f[0] for f in self.conexion.execute("SELECT id FROM peliculas").fetchall()]
        for pelicula_id in ids:
            self._sincronizar_fts(pelicula_id)
        self.conexion.commit()
        return len(ids)
