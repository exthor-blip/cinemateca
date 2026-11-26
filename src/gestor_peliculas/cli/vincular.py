"""Comando vincular: busca el identificador IMDb de cada carpeta.

Es el lote que corria "IMDB linker 4.3.ps1". Igual que el organizador, el modo
por defecto es simular: hay que pasar --escribir para que se creen los archivos
imdb.url y poster.jpg.

Y como en el original, solo se escribe sin preguntar cuando la coincidencia es
exacta. El resto queda marcado para revisar desde la pagina.
"""

from __future__ import annotations

import argparse
import time

from ..almacenamiento.bd import BaseDatos
from ..config import cargar_ajustes
from ..errores import ErrorDominio
from ..metadatos import escritor_sidecars
from ..metadatos.vinculador import Vinculador
from ..modelos import EstadoRevision
from ..nucleo.coincidencias import Veredicto


def registrar(comandos) -> None:
    orden = comandos.add_parser("vincular", help="busca el identificador IMDb de cada carpeta")
    orden.add_argument("--ubicacion", type=int, default=0,
                       help="limita el lote a una ubicacion del catalogo")
    orden.add_argument("--escribir", action="store_true",
                       help="crea imdb.url y poster.jpg de verdad (sin esto, solo simula)")
    orden.add_argument("--limite", type=int, default=0, help="procesa como maximo N peliculas")
    orden.add_argument("--solo-exactas", action="store_true",
                       help="informa unicamente las coincidencias exactas")
    orden.add_argument("--pausa", type=float, default=0.4,
                       help="segundos de espera entre peliculas")
    orden.set_defaults(funcion=ejecutar)


def ejecutar(argumentos: argparse.Namespace) -> int:
    ajustes = cargar_ajustes()
    simular = not argumentos.escribir

    with BaseDatos(ajustes.ruta_bd) as bd:
        if argumentos.ubicacion:
            ubicacion = bd.ubicaciones.obtener(argumentos.ubicacion)
            if ubicacion is None:
                raise ErrorDominio(
                    f"No hay ninguna ubicacion con el numero {argumentos.ubicacion}."
                )
            candidatas = bd.peliculas.listar_por_ubicacion(argumentos.ubicacion)
        else:
            candidatas = bd.peliculas.listar_todas()

        # Una carpeta que ya tiene enlace no se vuelve a buscar: es la
        # proteccion del original contra reemparejar una pelicula ya resuelta.
        pendientes = [p for p in candidatas if not p.imdb_id]
        if argumentos.limite:
            pendientes = pendientes[: argumentos.limite]

        if not pendientes:
            print("Todas las peliculas del catalogo ya tienen enlace de IMDb.")
            return 0

        print(f"Peliculas sin enlace de IMDb: {len(pendientes)}")
        if simular:
            print("*** MODO SIMULACION: no se escribe ningun archivo. "
                  "Agrega --escribir para aplicar. ***")
        if not ajustes.tiene_credencial_tmdb:
            print("Sin clave de TMDb: se consultan IMDb, Wikidata y Wikipedia.")
        print()

        vinculador = Vinculador(credencial_tmdb=ajustes.credencial_tmdb,
                                idioma_tmdb=ajustes.idioma_tmdb)
        exactas = revisar = sin_nada = incompletas = 0

        for indice, pelicula in enumerate(pendientes, start=1):
            etiqueta = f"[{indice}/{len(pendientes)}] {pelicula.titulo_carpeta}"

            if not pelicula.anio_carpeta:
                print(f"{etiqueta}: sin anio, no se puede buscar con seguridad")
                sin_nada += 1
                continue

            resultado = vinculador.vincular_pelicula(pelicula)
            if not resultado.busqueda_completa:
                incompletas += 1

            if resultado.veredicto is Veredicto.EXACTA:
                exactas += 1
                elegido = resultado.elegido
                print(f"{etiqueta}: EXACTA -> {elegido.imdb_id} "
                      f"({elegido.titulo}, {elegido.anio})")
                if not simular:
                    _guardar(bd, pelicula, elegido)

            elif resultado.veredicto is Veredicto.REVISAR:
                revisar += 1
                if not argumentos.solo_exactas:
                    print(f"{etiqueta}: REVISAR -> {resultado.nota}")
                    elegido = resultado.elegido
                    if elegido:
                        print(f"    propuesta: {elegido.imdb_id or elegido.tmdb_id} "
                              f"{elegido.titulo} ({elegido.anio})")
                if not simular:
                    _marcar(bd, pelicula, resultado)

            else:
                sin_nada += 1
                if not argumentos.solo_exactas:
                    print(f"{etiqueta}: sin coincidencia. {resultado.nota}")
                if not simular:
                    bd.peliculas.guardar_revision(
                        pelicula.id, EstadoRevision.SIN_COINCIDENCIA, detalle=resultado.nota
                    )

            if indice < len(pendientes):
                time.sleep(max(0.0, argumentos.pausa))

        print()
        print(f"Exactas: {exactas}   Para revisar: {revisar}   Sin coincidencia: {sin_nada}")
        if incompletas:
            print(f"Atencion: en {incompletas} peliculas alguna fuente no respondio, "
                  "asi que 'sin coincidencia' no es concluyente. Conviene reintentar.")
        if simular:
            print("\nNo se escribio nada. Agrega --escribir para crear imdb.url y poster.jpg.")
    return 0


def _guardar(bd, pelicula, candidato) -> None:
    """Escribe el sidecar en el disco y anota el enlace en la base."""
    carpeta = pelicula.carpeta_absoluta
    if carpeta is None or not carpeta.is_dir():
        print(f"    la carpeta {carpeta} no esta disponible: no se escribe")
        return

    resultado = escritor_sidecars.escribir_imdb(
        carpeta, candidato.imdb_id, poster_url=candidato.poster_url
    )
    bd.peliculas.fijar_imdb_id(pelicula.id, candidato.imdb_id)
    if resultado.poster_escrito:
        bd.peliculas.fijar_poster(pelicula.id, escritor_sidecars.NOMBRE_POSTER)
    bd.peliculas.guardar_revision(
        pelicula.id, EstadoRevision.COMPLETADA,
        detalle=f"Enlace de IMDb confirmado automaticamente ({resultado}).",
    )
    print(f"    {resultado}")


def _marcar(bd, pelicula, resultado) -> None:
    elegido = resultado.elegido
    bd.peliculas.guardar_revision(
        pelicula.id, EstadoRevision.REVISAR, detalle=resultado.nota,
        candidato_id=(elegido.imdb_id if elegido else ""),
        candidato_titulo=(elegido.titulo if elegido else ""),
        candidato_anio=(elegido.anio if elegido else ""),
        candidato_poster=(elegido.poster_url if elegido else ""),
    )
