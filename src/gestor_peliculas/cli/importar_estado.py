"""Comando importar-estado: lee un .imdb_linker_estado.json del linker original.

Es lo unico que vale la pena migrar del proyecto viejo. El resto de los datos se
reconstruye re-indexando, porque la verdad esta en el disco: los nombres de
carpeta, imdb.url y poster.jpg. Pero el JSON de estado guarda algo que NO esta
en ningun otro lado: que candidatos rechazo la persona a mano, para no volver a
ofrecerselos, y que carpetas quedaron marcadas para revisar.

El JSON indexa por ruta ABSOLUTA, asi que si la coleccion se movio de lugar hay
que indicar la raiz vieja con --raiz-original.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..almacenamiento.bd import BaseDatos
from ..config import cargar_ajustes
from ..errores import ErrorDominio
from ..modelos import EstadoRevision
from ..nucleo import identificadores as ident

NOMBRE_ESTADO = ".imdb_linker_estado.json"

#: Los estados del linker original, traducidos a los de esta version.
TRADUCCION = {
    "completada": EstadoRevision.COMPLETADA,
    "revisar": EstadoRevision.REVISAR,
    "pendiente": EstadoRevision.PENDIENTE,
    "no encontrada": EstadoRevision.SIN_COINCIDENCIA,
    "rechazada": EstadoRevision.PENDIENTE,
    "sin poster": EstadoRevision.COMPLETADA,
    "error": EstadoRevision.ERROR,
}


def registrar(comandos) -> None:
    orden = comandos.add_parser(
        "importar-estado",
        help="lee un .imdb_linker_estado.json del IMDB linker original",
    )
    orden.add_argument("archivo", nargs="?",
                       help="ruta al .imdb_linker_estado.json, o la carpeta que lo contiene")
    orden.add_argument("--ubicacion", type=int, default=0,
                       help="ubicacion del catalogo a la que corresponde")
    orden.add_argument("--raiz-original", default="",
                       help="raiz que tenia la coleccion cuando se genero el JSON, "
                            "si despues se movio de lugar")
    orden.set_defaults(funcion=ejecutar)


def ejecutar(argumentos: argparse.Namespace) -> int:
    ajustes = cargar_ajustes()

    with BaseDatos(ajustes.ruta_bd) as bd:
        ubicaciones = bd.ubicaciones.listar()
        if not ubicaciones:
            raise ErrorDominio("Todavia no hay ubicaciones en el catalogo. Indexa una primero.")

        if argumentos.ubicacion:
            ubicacion = bd.ubicaciones.obtener(argumentos.ubicacion)
            if ubicacion is None:
                raise ErrorDominio(f"No hay ubicacion con el numero {argumentos.ubicacion}.")
        elif len(ubicaciones) == 1:
            ubicacion = ubicaciones[0]
        else:
            print("Hay varias ubicaciones; indica cual con --ubicacion:")
            for una in ubicaciones:
                print(f"  {una.id}: {una.nombre}  ({una.ruta})")
            return 1

        archivo = _resolver_archivo(argumentos.archivo, ubicacion.ruta)
        print(f"Leyendo {archivo}")
        datos = _leer(archivo)
        print(f"  {len(datos)} carpetas en el archivo de estado")

        raiz_vieja = None
        if argumentos.raiz_original:
            raiz_vieja = Path(argumentos.raiz_original).expanduser()

        aplicados = rechazos = no_encontradas = 0

        for ruta_absoluta, guardado in datos.items():
            relativa = _relativizar(ruta_absoluta, ubicacion.ruta, raiz_vieja)
            if relativa is None:
                no_encontradas += 1
                continue

            pelicula = bd.peliculas.obtener_por_ruta(ubicacion.id, relativa)
            if pelicula is None:
                no_encontradas += 1
                continue

            estado = TRADUCCION.get(
                str(guardado.get("Status", "")).strip().lower(), EstadoRevision.PENDIENTE
            )
            rechazados = [
                ident.normalizar_imdb_id(str(r))
                for r in (guardado.get("RejectedIds") or [])
                if ident.normalizar_imdb_id(str(r))
            ]
            rechazos += len(rechazados)

            bd.peliculas.guardar_revision(
                pelicula.id, estado,
                detalle=str(guardado.get("Detail") or "Importado del IMDB linker original."),
                candidato_id=ident.normalizar_imdb_id(str(guardado.get("CandidateId") or "")),
                candidato_titulo=str(guardado.get("CandidateTitle") or ""),
                candidato_anio=str(guardado.get("CandidateYear") or ""),
                candidato_poster=str(guardado.get("Poster") or ""),
                rechazados=rechazados,
            )

            # Si el JSON guardaba el enlace y la base no lo tiene, se aprovecha.
            enlace = ident.extraer_imdb_id(str(guardado.get("Imdb") or ""))
            if enlace and not pelicula.imdb_id:
                bd.peliculas.fijar_imdb_id(pelicula.id, enlace)

            aplicados += 1

        print()
        print(f"Estados aplicados:        {aplicados}")
        print(f"Candidatos rechazados:    {rechazos} (no se volveran a ofrecer)")
        print(f"Carpetas sin equivalente: {no_encontradas}")
        if no_encontradas:
            print("\nSi la coleccion cambio de lugar, usa --raiz-original con la ruta vieja.")
    return 0


def _resolver_archivo(indicado: str | None, raiz_ubicacion: Path) -> Path:
    if indicado:
        candidato = Path(indicado).expanduser()
        if candidato.is_dir():
            candidato = candidato / NOMBRE_ESTADO
    else:
        candidato = raiz_ubicacion / NOMBRE_ESTADO
    if not candidato.is_file():
        raise ErrorDominio(f"No existe el archivo {candidato}.")
    return candidato


def _leer(archivo: Path) -> dict:
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ErrorDominio(f"No se pudo leer el archivo de estado: {error}") from error
    if not isinstance(datos, dict):
        raise ErrorDominio("El archivo de estado no tiene el formato esperado.")
    return {k: v for k, v in datos.items() if isinstance(v, dict)}


def _relativizar(ruta_absoluta: str, raiz_nueva: Path, raiz_vieja: Path | None) -> str | None:
    """Convierte la ruta absoluta del JSON en una ruta relativa a la ubicacion."""
    ruta = Path(ruta_absoluta)
    for raiz in (raiz_vieja, raiz_nueva):
        if raiz is None:
            continue
        try:
            return ruta.relative_to(raiz).as_posix()
        except ValueError:
            continue
    # Ultimo recurso: el nombre de la carpeta suele alcanzar, porque el linker
    # solo miraba subcarpetas directas de la raiz.
    return ruta.name or None
