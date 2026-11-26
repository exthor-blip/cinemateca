"""Casos de uso del organizador de archivos.

Regla de seguridad que atraviesa todo este servicio: **el modo por defecto es
simular**. Quien quiera escribir en el disco tiene que pedirlo explicitamente
con simular=False, que en la web significa marcar la casilla de confirmacion y
en la consola pasar --escribir. El original preguntaba con un cuadro de
dialogo; aca, al no haber dialogo modal, la red de seguridad es que no hacer
nada sea lo que pasa si uno se distrae.
"""

from __future__ import annotations

from pathlib import Path

from .. import registro
from ..almacenamiento.bd import BaseDatos
from ..config import Ajustes
from ..errores import ErrorDominio
from ..organizador import analizador, informes, limpieza, minusculas
from ..organizador.analizador import Analisis
from ..organizador.renombrador import Resultado, renombrar
from ..rutas_datos import carpeta_informes
from .tareas import Tarea, registro_tareas

log = registro.obtener(__name__)

TIPO_TAREA = "organizador"


class ServicioOrganizador:
    #: El analisis se recuerda entre peticiones: recorrer un disco entero en
    #: cada carga de pagina seria insoportable.
    _analisis: Analisis | None = None

    def __init__(self, bd: BaseDatos, ajustes: Ajustes) -> None:
        self.bd = bd
        self.ajustes = ajustes

    # ------------------------------------------------------------------ lectura

    def ubicaciones(self):
        """Las ubicaciones del catalogo, para ofrecerlas como atajo."""
        return self.bd.ubicaciones.listar()

    def _validar(self, ruta: Path | str) -> Path:
        carpeta = Path(str(ruta).strip().strip('"')).expanduser()
        if not str(carpeta).strip():
            raise ErrorDominio("Hay que indicar la carpeta de la coleccion.")
        if not carpeta.is_dir():
            raise ErrorDominio(f"La carpeta {carpeta} no esta disponible.")
        return carpeta

    def analizar(self, ruta: Path | str) -> Analisis:
        analisis = analizador.analizar(self._validar(ruta))
        ServicioOrganizador._analisis = analisis
        return analisis

    @classmethod
    def ultimo_analisis(cls) -> Analisis | None:
        return cls._analisis

    def analisis_de(self, ruta: Path | str) -> Analisis:
        """El analisis recordado si es de esta carpeta; si no, uno nuevo."""
        carpeta = self._validar(ruta)
        recordado = ServicioOrganizador._analisis
        if recordado is not None and recordado.raiz == carpeta:
            return recordado
        return self.analizar(carpeta)

    def informes_disponibles(self, ruta: Path | str | None = None) -> list[dict]:
        if ruta:
            return informes.listar(self._validar(ruta))
        recordado = ServicioOrganizador._analisis
        return informes.listar(recordado.raiz) if recordado else []

    # ------------------------------------------------------------- renombrados

    def renombrar_pares(self, ruta: Path | str, *, simular: bool = True,
                        tarea: Tarea | None = None) -> dict:
        """Renombra video y subtitulos al nombre de su carpeta."""
        analisis = self.analisis_de(ruta)
        pendientes = analisis.pares_pendientes
        historial = informes.Historial()
        conteos = {"renombrados": 0, "conflictos": 0, "errores": 0, "simulado": simular}

        if tarea:
            tarea.fijar_total(len(pendientes))

        for par in pendientes:
            if tarea and tarea.cancelada:
                break
            if tarea:
                tarea.informar(f"Renombrando {par.nombre_carpeta}...")

            for origen, destino in zip(par.origenes, par.destinos, strict=True):
                operacion = renombrar(origen, destino, simular=simular)
                historial.anotar_operacion("RENOMBRAR", operacion)
                _contar(conteos, operacion.resultado)

            if tarea:
                tarea.avanzar()

        self._cerrar(analisis, historial, simular, tarea)
        return conteos

    def renombrar_sueltos(self, ruta: Path | str, *, simular: bool = True,
                          tarea: Tarea | None = None) -> dict:
        """Renombra los videos que no tienen subtitulos."""
        analisis = self.analisis_de(ruta)
        pendientes = analisis.sueltos_pendientes
        historial = informes.Historial()
        conteos = {"renombrados": 0, "conflictos": 0, "errores": 0, "simulado": simular}

        if tarea:
            tarea.fijar_total(len(pendientes))

        for suelto in pendientes:
            if tarea and tarea.cancelada:
                break
            if tarea:
                tarea.informar(f"Renombrando {suelto.video.name}...")
            operacion = renombrar(suelto.video, suelto.destino, simular=simular)
            historial.anotar_operacion("RENOMBRAR", operacion)
            _contar(conteos, operacion.resultado)
            if tarea:
                tarea.avanzar()

        self._cerrar(analisis, historial, simular, tarea)
        return conteos

    def minusculas(self, ruta: Path | str, *, simular: bool = True,
                   tarea: Tarea | None = None) -> dict:
        """Pasa a minusculas todos los nombres bajo la carpeta."""
        carpeta = self._validar(ruta)

        def informar(hechos: int, total: int, nombre: str) -> None:
            if tarea:
                tarea.fijar_total(total)
                tarea.avanzar(0, f"Convirtiendo {nombre}...")
                with tarea._candado:
                    tarea.hechos = hechos

        resultado = minusculas.convertir(
            carpeta, simular=simular,
            cancelado=(lambda: bool(tarea and tarea.cancelada)),
            progreso=informar,
        )

        historial = informes.Historial()
        for operacion in resultado.operaciones:
            if operacion.resultado is not Resultado.SIN_CAMBIOS:
                historial.anotar_operacion("MINUSCULAS", operacion)

        analisis = self.analizar(carpeta) if not simular else self.analisis_de(carpeta)
        self._cerrar(analisis, historial, simular, tarea)
        return {
            "convertidos": resultado.convertidos,
            "sin_cambios": resultado.sin_cambios,
            "conflictos": resultado.conflictos,
            "errores": resultado.errores,
            "simulado": simular,
            "texto": str(resultado),
        }

    def limpiar(self, ruta: Path | str, extensiones: list[str], *, simular: bool = True,
                tarea: Tarea | None = None) -> dict:
        """Manda a la Papelera los archivos de las extensiones elegidas."""
        if not extensiones:
            raise ErrorDominio("Hay que elegir al menos una extension.")

        analisis = self.analisis_de(ruta)
        elegidos = limpieza.archivos_de_extensiones(analisis.extras, extensiones)
        if not elegidos:
            raise ErrorDominio("No hay archivos de esas extensiones en la coleccion.")

        if tarea:
            tarea.fijar_total(len(elegidos))

        def informar(indice: int, nombre: str) -> None:
            if tarea:
                with tarea._candado:
                    tarea.hechos = indice
                    tarea.mensaje = f"Enviando {nombre} a la Papelera..."

        resultado = limpieza.a_papelera(
            elegidos, simular=simular,
            cancelado=(lambda: bool(tarea and tarea.cancelada)),
            progreso=informar,
        )

        historial = informes.Historial()
        for archivo in elegidos[: resultado.enviados]:
            historial.anotar("PAPELERA", archivo, "", "OK" if not simular else "SIMULADO")
        for error in resultado.errores:
            historial.anotar("PAPELERA", error, "", "ERROR", error)

        if not simular:
            analisis = self.analizar(analisis.raiz)
        self._cerrar(analisis, historial, simular, tarea)
        return {
            "enviados": resultado.enviados,
            "fallidos": resultado.fallidos,
            "protegidos": resultado.protegidos,
            "megabytes": resultado.megabytes,
            "simulado": simular,
            "texto": str(resultado),
        }

    # -------------------------------------------------------- en segundo plano

    def renombrar_pares_en_segundo_plano(self, ruta: Path | str, *, simular: bool = True) -> Tarea:
        return self._lanzar(
            "Renombrando pares",
            lambda tarea: self.renombrar_pares(ruta, simular=simular, tarea=tarea),
        )

    def renombrar_sueltos_en_segundo_plano(self, ruta: Path | str, *,
                                           simular: bool = True) -> Tarea:
        return self._lanzar(
            "Renombrando videos sin subtitulos",
            lambda tarea: self.renombrar_sueltos(ruta, simular=simular, tarea=tarea),
        )

    def minusculas_en_segundo_plano(self, ruta: Path | str, *, simular: bool = True) -> Tarea:
        return self._lanzar(
            "Pasando nombres a minusculas",
            lambda tarea: self.minusculas(ruta, simular=simular, tarea=tarea),
        )

    def limpiar_en_segundo_plano(self, ruta: Path | str, extensiones: list[str], *,
                                 simular: bool = True) -> Tarea:
        return self._lanzar(
            "Enviando archivos a la Papelera",
            lambda tarea: self.limpiar(ruta, extensiones, simular=simular, tarea=tarea),
        )

    def analizar_en_segundo_plano(self, ruta: Path | str) -> Tarea:
        def trabajo(tarea: Tarea) -> dict:
            carpeta = self._validar(ruta)
            tarea.informar("Analizando carpetas...")
            analisis = analizador.analizar(
                carpeta,
                cancelado=lambda: tarea.cancelada,
                progreso=lambda n, nombre: _informar_analisis(tarea, n, nombre),
            )
            ServicioOrganizador._analisis = analisis
            tarea.informar(str(analisis))
            return {"texto": str(analisis), "carpetas": analisis.carpetas}

        return self._lanzar("Analizando la coleccion", trabajo, usar_trabajo=True)

    def _lanzar(self, titulo: str, trabajo, *, usar_trabajo: bool = False) -> Tarea:
        if usar_trabajo:
            return registro_tareas.lanzar(TIPO_TAREA, titulo, trabajo)
        return registro_tareas.lanzar(TIPO_TAREA, titulo, lambda tarea: trabajo(tarea))

    @staticmethod
    def tarea_actual() -> Tarea | None:
        return registro_tareas.ultima_de_tipo(TIPO_TAREA)

    @staticmethod
    def detener() -> bool:
        return registro_tareas.cancelar_tipo(TIPO_TAREA)

    # --------------------------------------------------------------- internos

    def _cerrar(self, analisis: Analisis, historial: informes.Historial,
                simular: bool, tarea: Tarea | None) -> None:
        """Guarda los informes y vuelve a analizar si se escribio en el disco."""
        if simular or not len(historial):
            return
        try:
            ruta_informe, _ = informes.guardar(
                analisis, historial, alternativa=carpeta_informes(self.ajustes.carpeta_datos)
            )
            if tarea:
                tarea.anotar(f"Informe guardado en {ruta_informe}")
        except OSError as error:
            log.warning("No se pudo guardar el informe: %s", error)
            if tarea:
                tarea.anotar(f"No se pudo guardar el informe: {error}")
        ServicioOrganizador._analisis = analizador.analizar(analisis.raiz)


def _contar(conteos: dict, resultado: Resultado) -> None:
    if resultado in (Resultado.RENOMBRADO, Resultado.SIMULADO):
        conteos["renombrados"] += 1
    elif resultado is Resultado.CONFLICTO:
        conteos["conflictos"] += 1
    elif resultado is Resultado.ERROR:
        conteos["errores"] += 1


def _informar_analisis(tarea: Tarea, examinadas: int, nombre: str) -> None:
    tarea.fijar_total(max(tarea.total, examinadas))
    with tarea._candado:
        tarea.hechos = examinadas
        tarea.mensaje = f"Analizando {nombre}..." if nombre else f"{examinadas} carpetas."
