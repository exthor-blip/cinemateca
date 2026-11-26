"""Decision de cuando una coincidencia externa es segura.

Es la regla mas importante del proyecto y en el original estaba repartida por
dentro de Search-Imdb, Get-WikidataCandidates, Search-Tmdb y searchMovie().
Aca queda en un solo lugar, sin red y sin disco, para poder probarla.

El criterio que se conserva del original, porque es bueno: solo se guarda sin
preguntar cuando hay UNA sola ficha cuyo titulo principal y anio coinciden
exactamente. Todo lo demas va a revision humana. Mas vale una pelicula
pendiente que una ficha equivocada guardada en silencio.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .titulos import normalizar_titulo


class Veredicto(StrEnum):
    EXACTA = "exacta"                  # se puede guardar sin preguntar
    REVISAR = "revisar"                # hay candidatos, decide la persona
    SIN_COINCIDENCIA = "sin_coincidencia"

    @property
    def etiqueta(self) -> str:
        return {
            "exacta": "Coincidencia exacta",
            "revisar": "Para revisar",
            "sin_coincidencia": "Sin coincidencia",
        }[self.value]


@dataclass(frozen=True, slots=True)
class Coincidencia:
    """Resultado de evaluar los candidatos de una fuente externa."""

    veredicto: Veredicto
    candidatos: tuple = ()
    nota: str = ""

    @property
    def elegido(self):
        """El mejor candidato, o None si no hay ninguno."""
        return self.candidatos[0] if self.candidatos else None

    @property
    def es_exacta(self) -> bool:
        return self.veredicto is Veredicto.EXACTA


def _anio(valor: object) -> str:
    texto = str(valor or "").strip()
    return texto[:4] if len(texto) >= 4 and texto[:4].isdigit() else ""


def _distancia_anio(candidato, anio: str) -> int:
    """Diferencia absoluta de anios, o un numero grande si no se puede comparar."""
    propio = _anio(getattr(candidato, "anio", ""))
    if not propio or not anio:
        return 999
    try:
        return abs(int(propio) - int(anio))
    except ValueError:
        return 999


def _titulos_del_candidato(candidato) -> list[str]:
    alternativos = getattr(candidato, "titulos_alternativos", None) or ()
    valores = [
        getattr(candidato, "titulo", ""),
        getattr(candidato, "titulo_original", ""),
        *alternativos,
    ]
    return [v for v in valores if v]


def coincide_titulo(candidato, titulos_buscados: set[str]) -> bool:
    """True si algun titulo del candidato normaliza igual que alguno buscado."""
    return any(normalizar_titulo(t) in titulos_buscados for t in _titulos_del_candidato(candidato))


def clasificar(candidatos, titulo: str, anio: str, *,
               titulos_extra: list[str] | None = None) -> Coincidencia:
    """Clasifica una lista de candidatos frente al titulo y anio de la carpeta.

    Args:
        candidatos: objetos con atributos titulo, titulo_original y anio
            (normalmente modelos.Candidato).
        titulo: titulo salido del nombre de carpeta.
        anio: anio de cuatro digitos, o cadena vacia.
        titulos_extra: variantes adicionales a aceptar como el mismo titulo
            (por ejemplo las que devolvio Wikipedia o Wikidata).

    Returns:
        Coincidencia con el veredicto y los candidatos ordenados de mejor a peor.
    """
    lista = [c for c in candidatos if c is not None]
    if not lista:
        return Coincidencia(Veredicto.SIN_COINCIDENCIA, (), "Ninguna fuente devolvio candidatos.")

    buscados = {normalizar_titulo(t) for t in [titulo, *(titulos_extra or [])] if t}
    buscados.discard("")
    anio_normal = _anio(anio)

    mismo_titulo = [c for c in lista if coincide_titulo(c, buscados)]
    mismo_anio = [c for c in lista if anio_normal and _anio(getattr(c, "anio", "")) == anio_normal]
    ids_mismo_anio = {id(c) for c in mismo_anio}
    exactos = [c for c in mismo_titulo if id(c) in ids_mismo_anio]

    if len(exactos) == 1:
        return Coincidencia(Veredicto.EXACTA, (exactos[0],),
                            "El titulo principal y el anio coinciden, y es la unica ficha.")

    if len(exactos) > 1:
        return Coincidencia(Veredicto.REVISAR, tuple(exactos),
                            f"Hay {len(exactos)} fichas con el mismo titulo y anio: hay que elegir.")

    if mismo_titulo:
        # Un anio distinto puede ser legitimo (fecha de estreno por pais), pero
        # nunca se aprueba solo. Se ordena por cercania de anio.
        ordenados = sorted(mismo_titulo, key=lambda c: _distancia_anio(c, anio_normal))
        mejor = ordenados[0]
        return Coincidencia(
            Veredicto.REVISAR, tuple(ordenados),
            f"Mismo titulo pero otro anio (carpeta {anio_normal or 'sin anio'}, "
            f"ficha {_anio(getattr(mejor, 'anio', '')) or 'sin anio'}): hay que verificar.",
        )

    if mismo_anio:
        # Coincidir solo el anio no alcanza para proponer una pelicula distinta,
        # pero se ofrece como material de revision.
        return Coincidencia(Veredicto.REVISAR, tuple(mismo_anio),
                            "Solo coincide el anio, no el titulo: hay que verificar.")

    ordenados = sorted(lista, key=lambda c: _distancia_anio(c, anio_normal))
    return Coincidencia(Veredicto.REVISAR, tuple(ordenados[:8]),
                        "Ninguna ficha coincide en titulo ni anio: hay que verificar.")


def ordenar_para_revision(candidatos, titulo: str, anio: str,
                          rechazados: set[str] | None = None) -> list:
    """Ordena candidatos para mostrarlos en la pantalla de revision.

    Primero los de titulo exacto, despues por cercania de anio. Descarta los
    que la persona ya rechazo, que es Get-ReviewOptions del linker.
    """
    descartados = {r.lower() for r in (rechazados or set())}
    buscado = normalizar_titulo(titulo)
    anio_normal = _anio(anio)

    utiles = [
        c for c in candidatos
        if c is not None and (getattr(c, "imdb_id", "") or "").lower() not in descartados
    ]

    def clave(candidato) -> tuple[int, int]:
        exacto = 0 if normalizar_titulo(getattr(candidato, "titulo", "")) == buscado else 1
        return (exacto, _distancia_anio(candidato, anio_normal))

    return sorted(utiles, key=clave)
