"""Excepciones del dominio.

Se definen todas juntas para que cualquier capa pueda distinguir un problema
previsible (una ficha que necesita revision humana, una fuente externa caida)
de un error de programacion. El linker original atrapaba toda excepcion y
devolvia vacio, con lo cual una caida de red era indistinguible de "no hay
coincidencia"; estas clases existen para que eso no vuelva a pasar.
"""


class ErrorDominio(Exception):
    """Base de todos los errores previsibles del gestor."""


class ErrorConfiguracion(ErrorDominio):
    """Falta un ajuste imprescindible, por ejemplo la credencial de TMDb."""


class ErrorAlmacenamiento(ErrorDominio):
    """La base de datos no se pudo abrir, migrar o escribir."""


class ErrorFuenteExterna(ErrorDominio):
    """Una fuente externa (TMDb, IMDb, Wikidata, Wikipedia) no respondio bien.

    Attributes:
        fuente: nombre legible de la fuente.
        estado: codigo HTTP si lo hubo.
        detener_lote: True cuando no tiene sentido seguir con las demas
            peliculas (401, 403, 429 o 5xx), como ya hacia la app original.
    """

    def __init__(self, mensaje: str, *, fuente: str = "", estado: int | None = None,
                 detener_lote: bool = False) -> None:
        super().__init__(mensaje)
        self.fuente = fuente
        self.estado = estado
        self.detener_lote = detener_lote


class RequiereRevision(ErrorDominio):
    """Hay candidatos pero ninguno es concluyente: decide la persona.

    No es un fallo. Es el resultado legitimo de una busqueda ambigua, y el
    motivo por el que existe la pantalla de revision.
    """

    def __init__(self, mensaje: str, candidatos: list | None = None) -> None:
        super().__init__(mensaje)
        self.candidatos = candidatos or []


class RutaFueraDeUbicacion(ErrorDominio):
    """Se intento acceder a un archivo que no esta dentro de la ubicacion.

    Equivale a la comprobacion de ResolveVideo en Mi_Cinemateca_VLC.cs: la ruta
    resuelta tiene que seguir empezando con la raiz de la ubicacion.
    """


class ErrorReproduccion(ErrorDominio):
    """No se pudo reproducir: falta VLC o el archivo ya no esta."""


class OperacionCancelada(ErrorDominio):
    """La persona pulso Detener."""
