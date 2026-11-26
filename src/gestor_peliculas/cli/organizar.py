"""Comando organizar: analiza y organiza los archivos de una coleccion.

El modo por defecto es simular. Para escribir en el disco hay que pasar
--escribir, y cada operacion se pide por separado. Es a proposito: equivale a
los cuadros de confirmacion de la ventana original, y hace que distraerse no
tenga consecuencias.
"""

from __future__ import annotations

import argparse

from ..almacenamiento.bd import BaseDatos
from ..config import cargar_ajustes
from ..organizador import minusculas as modulo_minusculas
from ..servicios.servicio_organizador import ServicioOrganizador


def registrar(comandos) -> None:
    orden = comandos.add_parser("organizar", help="analiza y organiza los archivos")
    orden.add_argument("ruta", help="carpeta principal de peliculas")
    orden.add_argument("--escribir", action="store_true",
                       help="aplica los cambios de verdad (sin esto, solo simula)")
    orden.add_argument("--renombrar-pares", action="store_true",
                       help="renombra video y subtitulos al nombre de su carpeta")
    orden.add_argument("--renombrar-sueltos", action="store_true",
                       help="renombra los videos que no tienen subtitulos")
    orden.add_argument("--minusculas", action="store_true",
                       help="pasa todos los nombres a minusculas")
    orden.add_argument("--limpiar", nargs="+", metavar="EXT", default=[],
                       help="envia a la Papelera los archivos de estas extensiones")
    orden.set_defaults(funcion=ejecutar)


def ejecutar(argumentos: argparse.Namespace) -> int:
    ajustes = cargar_ajustes()
    simular = not argumentos.escribir

    with BaseDatos(ajustes.ruta_bd) as bd:
        servicio = ServicioOrganizador(bd, ajustes)
        analisis = servicio.analizar(argumentos.ruta)
        _mostrar_analisis(analisis)

        pidio_algo = (argumentos.renombrar_pares or argumentos.renombrar_sueltos
                      or argumentos.minusculas or argumentos.limpiar)
        if not pidio_algo:
            print("\nNo se pidio ninguna operacion. Opciones disponibles:")
            print("  --renombrar-pares     --renombrar-sueltos")
            print("  --minusculas          --limpiar .TMP .NFO ...")
            print("\nAgrega --escribir para aplicar los cambios de verdad.")
            return 0

        if simular:
            print("\n*** MODO SIMULACION: no se modifica ningun archivo. "
                  "Agrega --escribir para aplicar. ***")

        if argumentos.renombrar_pares:
            print("\nRenombrando pares...")
            print("  ", servicio.renombrar_pares(argumentos.ruta, simular=simular))

        if argumentos.renombrar_sueltos:
            print("\nRenombrando videos sin subtitulos...")
            print("  ", servicio.renombrar_sueltos(argumentos.ruta, simular=simular))

        if argumentos.minusculas:
            archivos, carpetas = modulo_minusculas.contar_pendientes(argumentos.ruta)
            print(f"\nPasando a minusculas: {archivos} archivos y {carpetas} carpetas...")
            print("  ", servicio.minusculas(argumentos.ruta, simular=simular).get("texto"))

        if argumentos.limpiar:
            print(f"\nEnviando a la Papelera: {', '.join(argumentos.limpiar)}")
            print("   Nada se borra de forma definitiva.")
            print("  ", servicio.limpiar(argumentos.ruta, argumentos.limpiar,
                                         simular=simular).get("texto"))
    return 0


def _mostrar_analisis(analisis) -> None:
    print(f"Coleccion: {analisis.raiz}")
    print(f"  Carpetas examinadas: {analisis.carpetas}")
    print(f"  Pares validos:       {len(analisis.pares)} "
          f"({len(analisis.pares_pendientes)} por renombrar)")
    print(f"  Solo video:          {len(analisis.sueltos)} "
          f"({len(analisis.sueltos_pendientes)} por renombrar)")
    print(f"  Incidencias:         {len(analisis.problemas)}")
    if analisis.sagas:
        print(f"  Con varias peliculas: {len(analisis.sagas)}  "
              "(no son problemas: el catalogo las indexa por separado)")
    print(f"  Archivos sueltos:    {analisis.total_extras} "
          f"({analisis.megabytes_extras} MB)")

    if analisis.extras:
        print("\n  Extensiones sueltas:")
        for grupo in analisis.extras:
            print(f"    {grupo.extension:<18} {grupo.cantidad:>5} archivos  "
                  f"{grupo.megabytes:>10} MB")

    if analisis.problemas:
        print("\n  Incidencias (no se tocan):")
        for incidencia in analisis.problemas[:10]:
            print(f"    {incidencia.nombre_carpeta}: {incidencia.motivo}")
        if len(analisis.problemas) > 10:
            print(f"    ... y {len(analisis.problemas) - 10} mas (ver el informe CSV)")
