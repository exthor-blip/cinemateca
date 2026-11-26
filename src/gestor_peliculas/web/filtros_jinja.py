"""Filtros de plantilla: formateo para mostrar, nada de logica de negocio.

Reemplazan los Intl.NumberFormat y las concatenaciones que el HTML hacia en
JavaScript. Al estar del lado del servidor, la pagina sale ya formateada y no
depende de la configuracion regional del navegador.
"""

from __future__ import annotations

from datetime import datetime

from flask import Flask


def puntaje_es(valor: float | None) -> str:
    """7.2 -> '7,2/10'. Es el Intl.NumberFormat('es-AR') del original."""
    if valor is None:
        return ""
    return f"{float(valor):.1f}".replace(".", ",") + "/10"


def duracion_es(minutos: int | None) -> str:
    """124 -> '2 h 4 min'. Mas legible que '124 min' para una pelicula."""
    if not minutos or minutos <= 0:
        return ""
    horas, resto = divmod(int(minutos), 60)
    if not horas:
        return f"{resto} min"
    if not resto:
        return f"{horas} h"
    return f"{horas} h {resto} min"


def tamanio_es(bytes_: int | None) -> str:
    """Tamanio de archivo con separador decimal de coma."""
    if not bytes_:
        return ""
    unidades = ("bytes", "KB", "MB", "GB", "TB")
    valor = float(bytes_)
    indice = 0
    while valor >= 1024 and indice < len(unidades) - 1:
        valor /= 1024
        indice += 1
    if indice == 0:
        return f"{int(valor)} {unidades[0]}"
    return f"{valor:.1f}".replace(".", ",") + f" {unidades[indice]}"


def lista_es(valores: list[str] | None, vacio: str = "Sin datos") -> str:
    """['Terror', 'Aventura'] -> 'Terror, Aventura'."""
    utiles = [str(v).strip() for v in (valores or []) if str(v).strip()]
    return ", ".join(utiles) if utiles else vacio


def miles_es(numero: int | None) -> str:
    """1234567 -> '1.234.567', con punto como separador de miles."""
    if numero is None:
        return ""
    return f"{int(numero):,}".replace(",", ".")


def fecha_es(texto: str | None) -> str:
    """'2026-11-26 17:40:00' -> '26/11/2026 17:40'."""
    if not texto:
        return ""
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            momento = datetime.strptime(texto, formato)
        except ValueError:
            continue
        return momento.strftime("%d/%m/%Y %H:%M") if "%H" in formato else momento.strftime("%d/%m/%Y")
    return texto


def registrar(app: Flask) -> None:
    app.jinja_env.filters.update({
        "puntaje_es": puntaje_es,
        "duracion_es": duracion_es,
        "tamanio_es": tamanio_es,
        "lista_es": lista_es,
        "miles_es": miles_es,
        "fecha_es": fecha_es,
    })
