"""Comando enriquecer: completa las fichas pendientes consultando TMDb."""

from __future__ import annotations

import argparse

from ..almacenamiento.bd import BaseDatos
from ..config import cargar_ajustes
from ..servicios.servicio_metadatos import ServicioMetadatos


def registrar(comandos) -> None:
    orden = comandos.add_parser("enriquecer", help="completa las fichas consultando TMDb")
    orden.add_argument("--limite", type=int, default=0,
                       help="consulta como maximo esta cantidad de peliculas")
    orden.add_argument("--solo-contar", action="store_true",
                       help="informa cuantas quedan pendientes y no consulta nada")
    orden.set_defaults(funcion=ejecutar)


def ejecutar(argumentos: argparse.Namespace) -> int:
    ajustes = cargar_ajustes()

    with BaseDatos(ajustes.ruta_bd) as bd:
        servicio = ServicioMetadatos(bd, ajustes)

        if argumentos.solo_contar:
            pendientes = servicio.pendientes()
            con_imdb = sum(1 for p in pendientes if p.imdb_id)
            print(f"Pendientes de ficha: {len(pendientes)}")
            print(f"  con enlace IMDb (consulta exacta): {con_imdb}")
            print(f"  solo por titulo y anio:            {len(pendientes) - con_imdb}")
            return 0

        servicio.exigir_credencial()
        limite = argumentos.limite or None
        pendientes = servicio.pendientes(limite)
        if not pendientes:
            print("No hay peliculas pendientes de ficha.")
            return 0

        print(f"Consultando TMDb para {len(pendientes)} peliculas...")
        resultado = servicio.completar_lote(limite=limite)
        print()
        print(resultado)
        for mensaje in resultado.mensajes[:10]:
            print(f"  {mensaje}")
        if resultado.interrumpido:
            print("\nEl lote se interrumpio. Revisa la clave de TMDb o espera un rato.")
            return 1
        if resultado.para_revisar:
            print(f"\n{resultado.para_revisar} peliculas quedaron para revisar a mano: "
                  "abrilas desde la pagina para elegir la ficha correcta.")
    return 0
