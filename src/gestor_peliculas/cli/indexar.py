"""Comando indexar: agrega una carpeta al catalogo y la recorre."""

from __future__ import annotations

import argparse

from ..almacenamiento.bd import BaseDatos
from ..catalogo import indexador
from ..config import cargar_ajustes


def registrar(comandos) -> None:
    orden = comandos.add_parser("indexar", help="agrega una carpeta al catalogo y la indexa")
    orden.add_argument("ruta", nargs="?", help="carpeta de peliculas")
    orden.add_argument("--nombre", default="", help="nombre para la ubicacion")
    orden.add_argument("--todas", action="store_true",
                       help="vuelve a indexar todas las ubicaciones ya dadas de alta")
    orden.set_defaults(funcion=ejecutar)


def ejecutar(argumentos: argparse.Namespace) -> int:
    ajustes = cargar_ajustes()

    with BaseDatos(ajustes.ruta_bd) as bd:
        if argumentos.todas:
            resultados = indexador.reindexar_todo(bd, progreso=_mostrar)
            print()
            for nombre, resumen in resultados.items():
                print(f"{nombre}: {resumen}")
            if not resultados:
                print("No hay ubicaciones disponibles para indexar.")
            return 0

        if not argumentos.ruta:
            print("Hay que indicar la carpeta, o usar --todas.")
            return 1

        ubicacion, resumen = indexador.indexar_carpeta(
            bd, argumentos.ruta, nombre=argumentos.nombre, progreso=_mostrar
        )
        print()
        print(f"Ubicacion: {ubicacion.nombre}  ({ubicacion.ruta})")
        print(resumen)
        print(f"Total en el catalogo: {bd.peliculas.contar()} peliculas")
    return 0


def _mostrar(examinadas: int, actual: str) -> None:
    texto = f"  {examinadas} carpetas examinadas"
    if actual:
        texto += f" - {actual[:48]}"
    print(f"\r{texto:<90}", end="", flush=True)
