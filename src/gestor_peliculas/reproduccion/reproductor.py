"""Abre el video original en VLC.

Reemplaza las tres piezas que el proyecto viejo necesitaba para esto: el
protocolo `micinemateca-vlc:`, las claves de registro con el SHA-256 de cada
ubicacion, y el ejecutable `Mi_Cinemateca_VLC.exe`. Con el backend corriendo en
la misma computadora, lanzar el proceso es una llamada directa.

Lo que SI se conserva del C# es la validacion de ruta, que era lo importante de
aquel codigo: la ruta resuelta tiene que seguir estando dentro de la raiz de la
ubicacion. Es la defensa contra una ruta relativa con `..` que apunte a
cualquier archivo del disco. Ver ResolveVideo en Mi_Cinemateca_VLC.cs, lineas
78-85, y las comprobaciones de segmento de IsSegment, lineas 71-76.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .. import registro
from ..errores import ErrorReproduccion, RutaFueraDeUbicacion
from ..modelos import Pelicula
from ..nucleo.extensiones import VIDEO_EXT
from . import localizador_vlc

log = registro.obtener(__name__)

#: --one-instance reutiliza la ventana de VLC ya abierta, como hacia el C#.
#: El -- final evita que un nombre de archivo que empiece con guion se
#: interprete como una opcion de VLC.
ARGUMENTOS = ("--one-instance", "--")


def resolver_video(raiz: Path, ruta_relativa: str, nombre_archivo: str) -> Path:
    """Resuelve la ruta del video y verifica que no se escape de la ubicacion.

    Raises:
        RutaFueraDeUbicacion: la ruta resuelta queda fuera de la raiz, el
            archivo no existe, o la extension no es de video.
    """
    if not raiz or not Path(raiz).is_absolute():
        raise RutaFueraDeUbicacion("La ubicacion no tiene una ruta absoluta valida.")

    nombre = Path(nombre_archivo).name
    if not nombre or nombre != nombre_archivo:
        raise RutaFueraDeUbicacion("El nombre del archivo de video no es valido.")
    if Path(nombre).suffix.lower() not in VIDEO_EXT:
        raise RutaFueraDeUbicacion(f"{nombre} no tiene una extension de video reconocida.")

    base = Path(raiz).resolve()
    candidata = (base / (ruta_relativa or "") / nombre).resolve()

    # La comparacion se hace sobre las rutas ya resueltas: asi un '..' en medio
    # de ruta_relativa no puede sacarnos de la ubicacion.
    try:
        candidata.relative_to(base)
    except ValueError as error:
        raise RutaFueraDeUbicacion(
            "La ruta del video queda fuera de la carpeta de la ubicacion."
        ) from error

    if not candidata.is_file():
        raise RutaFueraDeUbicacion(f"El archivo {candidata} ya no esta en el disco.")

    return candidata


def reproducir(pelicula: Pelicula, *, ruta_vlc: str = "") -> Path:
    """Abre la pelicula en VLC y devuelve la ruta que se abrio.

    Raises:
        ErrorReproduccion: falta VLC o el proceso no arranco.
        RutaFueraDeUbicacion: la ruta no es valida.
    """
    if pelicula.ubicacion_ruta is None:
        raise ErrorReproduccion("La pelicula no tiene una ubicacion asociada.")

    destino = resolver_video(
        pelicula.ubicacion_ruta, pelicula.ruta_relativa, pelicula.archivo_video
    )

    ejecutable = localizador_vlc.localizar(ruta_vlc)
    if ejecutable is None:
        raise ErrorReproduccion(
            "No se encontro VLC en esta computadora. Se puede instalar desde "
            "videolan.org, o indicar su ruta en el archivo .env (VLC_RUTA)."
        )

    comando = [str(ejecutable), *ARGUMENTOS, str(destino)]
    try:
        # No se espera a que VLC termine: la peticion web tiene que responder ya.
        creacion = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen(
            comando,
            cwd=str(ejecutable.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creacion,
        )
    except OSError as error:
        raise ErrorReproduccion(f"No se pudo iniciar VLC: {error}") from error

    log.info("Reproduciendo en VLC: %s", destino)
    return destino


def abrir_carpeta(pelicula: Pelicula) -> Path:
    """Abre en el Explorador la carpeta de la pelicula, con el video elegido.

    Es el equivalente del boton "Abrir carpeta" que tenian las dos GUI de
    PowerShell.
    """
    if pelicula.ubicacion_ruta is None:
        raise ErrorReproduccion("La pelicula no tiene una ubicacion asociada.")

    destino = resolver_video(
        pelicula.ubicacion_ruta, pelicula.ruta_relativa, pelicula.archivo_video
    )
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(destino)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(destino)])
        else:
            subprocess.Popen(["xdg-open", str(destino.parent)])
    except OSError as error:
        raise ErrorReproduccion(f"No se pudo abrir la carpeta: {error}") from error
    return destino.parent
