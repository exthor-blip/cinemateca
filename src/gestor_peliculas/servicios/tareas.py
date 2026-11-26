"""Tareas largas en segundo plano con progreso y cancelacion.

El HTML original hacia esto con un bucle async y un AbortController: la barra
de progreso y el boton Detener vivian en la misma pagina que el trabajo. Con
backend el trabajo ocurre en el servidor, asi que hace falta un registro de
tareas que la pagina pueda consultar.

Es deliberadamente simple: un diccionario en memoria y un hilo por tarea. No
hay Celery ni Redis porque la aplicacion corre en la computadora de una sola
persona y nunca hay mas de una tarea de cada tipo a la vez. Si el servidor se
reinicia las tareas se pierden, que es lo correcto: lo que ya se escribio en la
base queda, y la tarea se vuelve a lanzar.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .. import registro
from ..errores import OperacionCancelada

log = registro.obtener(__name__)

#: Cuantas tareas terminadas se recuerdan, para que la pagina alcance a leer
#: el resultado de la ultima aunque se recargue.
MAXIMO_HISTORIAL = 20


class EstadoTarea(StrEnum):
    EN_CURSO = "en_curso"
    TERMINADA = "terminada"
    CANCELADA = "cancelada"
    FALLIDA = "fallida"

    @property
    def etiqueta(self) -> str:
        return {
            "en_curso": "En curso",
            "terminada": "Finalizada",
            "cancelada": "Detenida",
            "fallida": "Interrumpida",
        }[self.value]

    @property
    def viva(self) -> bool:
        return self is EstadoTarea.EN_CURSO


@dataclass
class Tarea:
    """Una operacion larga, consultable mientras corre."""

    id: str
    tipo: str
    titulo: str
    estado: EstadoTarea = EstadoTarea.EN_CURSO
    total: int = 0
    hechos: int = 0
    mensaje: str = ""
    detalle: list[str] = field(default_factory=list)
    resultado: dict = field(default_factory=dict)
    error: str = ""
    iniciada_en: datetime = field(default_factory=datetime.now)
    terminada_en: datetime | None = None
    _cancelar: threading.Event = field(default_factory=threading.Event, repr=False)
    _candado: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ------------------------------------------------------- desde el trabajo

    def fijar_total(self, total: int) -> None:
        with self._candado:
            self.total = max(0, int(total))

    def avanzar(self, cantidad: int = 1, mensaje: str = "") -> None:
        with self._candado:
            self.hechos += cantidad
            if mensaje:
                self.mensaje = mensaje

    def informar(self, mensaje: str) -> None:
        with self._candado:
            self.mensaje = mensaje

    def anotar(self, linea: str) -> None:
        """Agrega una linea al detalle, acotando el tamanio."""
        with self._candado:
            if len(self.detalle) < 200:
                self.detalle.append(linea)

    @property
    def cancelada(self) -> bool:
        return self._cancelar.is_set()

    def verificar_cancelacion(self) -> None:
        if self.cancelada:
            raise OperacionCancelada("La persona detuvo la operacion.")

    # ------------------------------------------------------- desde la interfaz

    def cancelar(self) -> None:
        self._cancelar.set()
        with self._candado:
            if self.estado.viva:
                self.mensaje = "Se detendra en cuanto termine el paso actual."

    @property
    def porcentaje(self) -> int:
        with self._candado:
            if self.total <= 0:
                return 0 if self.estado.viva else 100
            return min(100, round(100 * self.hechos / self.total))

    @property
    def segundos(self) -> float:
        fin = self.terminada_en or datetime.now()
        return (fin - self.iniciada_en).total_seconds()

    def como_json(self) -> dict:
        """Lo que consume progreso.js."""
        with self._candado:
            return {
                "id": self.id,
                "tipo": self.tipo,
                "titulo": self.titulo,
                "estado": self.estado.value,
                "estado_etiqueta": self.estado.etiqueta,
                "viva": self.estado.viva,
                "total": self.total,
                "hechos": self.hechos,
                "porcentaje": self.porcentaje,
                "mensaje": self.mensaje,
                "detalle": list(self.detalle[-8:]),
                "resultado": dict(self.resultado),
                "error": self.error,
                "segundos": round(self.segundos, 1),
            }


class RegistroTareas:
    """Lanza y recuerda las tareas del proceso."""

    def __init__(self) -> None:
        self._tareas: dict[str, Tarea] = {}
        self._orden: list[str] = []
        self._candado = threading.Lock()

    def lanzar(self, tipo: str, titulo: str, trabajo: Callable[[Tarea], dict | None]) -> Tarea:
        """Arranca `trabajo` en un hilo y devuelve la tarea para consultarla.

        Si ya hay una tarea viva del mismo tipo, devuelve esa en lugar de
        lanzar otra: dos indexados simultaneos sobre la misma base solo se
        estorbarian.
        """
        with self._candado:
            viva = self._viva_de_tipo(tipo)
            if viva is not None:
                return viva

            tarea = Tarea(id=uuid.uuid4().hex[:12], tipo=tipo, titulo=titulo)
            self._tareas[tarea.id] = tarea
            self._orden.append(tarea.id)
            self._podar()

        def envoltura() -> None:
            try:
                resultado = trabajo(tarea)
                with tarea._candado:
                    tarea.resultado = resultado or {}
                    tarea.estado = (EstadoTarea.CANCELADA if tarea.cancelada
                                    else EstadoTarea.TERMINADA)
            except OperacionCancelada:
                with tarea._candado:
                    tarea.estado = EstadoTarea.CANCELADA
                    tarea.mensaje = "Detenida."
            except Exception as error:  # noqa: BLE001 - el hilo no puede morir callado
                log.error("La tarea %s (%s) fallo: %s", tarea.id, tipo, error)
                log.debug("%s", traceback.format_exc())
                with tarea._candado:
                    tarea.estado = EstadoTarea.FALLIDA
                    tarea.error = str(error)
                    tarea.mensaje = f"Se interrumpio: {error}"
            finally:
                tarea.terminada_en = datetime.now()

        hilo = threading.Thread(target=envoltura, name=f"tarea-{tipo}-{tarea.id}", daemon=True)
        hilo.start()
        return tarea

    def obtener(self, tarea_id: str) -> Tarea | None:
        with self._candado:
            return self._tareas.get(tarea_id)

    def viva_de_tipo(self, tipo: str) -> Tarea | None:
        with self._candado:
            return self._viva_de_tipo(tipo)

    def ultima_de_tipo(self, tipo: str) -> Tarea | None:
        with self._candado:
            for tarea_id in reversed(self._orden):
                tarea = self._tareas.get(tarea_id)
                if tarea and tarea.tipo == tipo:
                    return tarea
        return None

    def listar(self) -> list[Tarea]:
        with self._candado:
            return [self._tareas[i] for i in reversed(self._orden) if i in self._tareas]

    def cancelar(self, tarea_id: str) -> bool:
        tarea = self.obtener(tarea_id)
        if tarea is None or not tarea.estado.viva:
            return False
        tarea.cancelar()
        return True

    def cancelar_tipo(self, tipo: str) -> bool:
        tarea = self.viva_de_tipo(tipo)
        if tarea is None:
            return False
        tarea.cancelar()
        return True

    # ------------------------------------------------------------- internos

    def _viva_de_tipo(self, tipo: str) -> Tarea | None:
        for tarea_id in reversed(self._orden):
            tarea = self._tareas.get(tarea_id)
            if tarea and tarea.tipo == tipo and tarea.estado.viva:
                return tarea
        return None

    def _podar(self) -> None:
        terminadas = [i for i in self._orden
                      if i in self._tareas and not self._tareas[i].estado.viva]
        while len(terminadas) > MAXIMO_HISTORIAL:
            viejo = terminadas.pop(0)
            self._tareas.pop(viejo, None)
            if viejo in self._orden:
                self._orden.remove(viejo)


#: Registro del proceso. La aplicacion web y la CLI comparten este.
registro_tareas = RegistroTareas()
