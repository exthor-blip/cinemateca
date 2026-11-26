"""Estado de las tareas en segundo plano, para las barras de progreso."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ...servicios.tareas import registro_tareas

bp = Blueprint("tareas", __name__, url_prefix="/tareas")


@bp.get("/<tarea_id>")
def estado(tarea_id: str):
    tarea = registro_tareas.obtener(tarea_id)
    if tarea is None:
        return jsonify({"error": "La tarea ya no esta en memoria."}), 404
    return jsonify(tarea.como_json())


@bp.post("/<tarea_id>/detener")
def detener(tarea_id: str):
    if registro_tareas.cancelar(tarea_id):
        return jsonify({"detenida": True})
    return jsonify({"detenida": False, "error": "Esa tarea ya no esta en curso."}), 409


@bp.get("/tipo/<tipo>")
def ultima_de_tipo(tipo: str):
    tarea = registro_tareas.ultima_de_tipo(tipo)
    return jsonify(tarea.como_json() if tarea else {})
