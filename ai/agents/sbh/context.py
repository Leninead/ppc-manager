"""What the SBH Recommendation agent receives and the shape it must answer in.

Serialization only: every keyword's priority, its cluster, the module's headline and whether the keyword already runs
in Sponsored Products were computed by the module (core/sbh/targets.py). The AI judges which clusters to launch.
"""
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids

ROW_PREFIX = "G"
MAX_CLUSTERS = 30
KEYWORDS_PER_CLUSTER = 8
MAX_KEYWORDS = 120
MAX_HEADLINE_CHARS = 50
VERDICTS = ("LANZAR", "PROBAR", "DESCARTAR")
_CLUSTER_CAP = ("Viajaron todos los clusters: {total}.",
                "De {total} clusters viajaron {sent}; los {left} restantes no existen para vos.")
_KEYWORD_CAP = ("Viajaron todas las keywords: {total}.",
                "De {total} keywords viajaron {sent}; las {left} restantes no existen para vos.")


@dataclass
class SbhData:
    brand: str        # the brand the SQP names, "" when it names none
    sp_account: str   # the Amazon Ads account the en_sp column comes from, "" when that column is unknown
    counts: dict      # the module's figures over the whole MKL, not only the rows below
    clusters: list    # records, most search volume first
    keywords: list    # records, priority first and then search volume
    idioma: str = "es"


# razon before veredicto on purpose: autoregressive generation conditions the verdict on the reasoning.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "maxItems": 10,
            "description": "el orden del array ES el orden de lanzamiento: clusters[0] es la primera campaña SBH que "
                           "armaría el AM. Vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string", "description": "id exacto del cluster en el documento"},
                    "razon": {"type": "string",
                              "description": "una oración: por qué este cluster va en esta posición, citando la cifra "
                                             "del documento que lo sostiene"},
                    "veredicto": {"enum": list(VERDICTS),
                                  "description": "LANZAR = armar la campaña SBH ahora; PROBAR = una campaña chica con "
                                                 "sus mejores keywords para validar; DESCARTAR = no vale una campaña "
                                                 "SBH"},
                    "confianza": {"enum": ["alta", "media", "baja"],
                                  "description": "baja obliga a formular la razón como algo a verificar"},
                    "headline": {"type": ["string", "null"],
                                 "description": f"headline propuesto para la campaña SBH del cluster: "
                                                f"{MAX_HEADLINE_CHARS} caracteres como máximo contando los espacios; "
                                                f"null si el veredicto es DESCARTAR o el cluster no tiene un tema"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto antes de lanzar, o null"},
                },
                "required": ["row_id", "razon", "veredicto", "confianza", "headline", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: qué oportunidad de Sponsored Brands tiene la marca en "
                                             "este MKL, anclado en una cifra del documento"},
                "week_actions": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                                 "description": "acciones de esta semana: verbo + row_ids + una cifra + qué se "
                                                "decide"},
                "mid_term": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                             "description": "oportunidades de 2 a 4 semanas"},
                "risks": {
                    "type": "array",
                    "maxItems": 4,
                    "description": "solo riesgos que se sostengan con una fila concreta del documento",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "detail": {"type": "string"},
                            "urgency": {"enum": ["alta", "media", "baja"]},
                        },
                        "required": ["type", "detail", "urgency"],
                        "additionalProperties": False,
                    },
                },
                "executive_summary": {"type": "string",
                                      "description": "2 oraciones copiables a Slack: cifras primero, cero adjetivos "
                                                     "sin número"},
            },
            "required": ["situation", "week_actions", "mid_term", "risks", "executive_summary"],
            "additionalProperties": False,
        },
    },
    "required": ["clusters", "synthesis"],
    "additionalProperties": False,
}


def records_of(d: SbhData) -> list:
    """The clusters the documents carry, in row_id order."""
    return d.clusters[:MAX_CLUSTERS]


def build_context(d: SbhData) -> tuple[str, list, dict]:
    clusters, keywords = d.clusters[:MAX_CLUSTERS], d.keywords[:MAX_KEYWORDS]
    counts = "\n".join(f"- {label}: {_number(value)}" for label, value in d.counts.items())
    sp_account = (d.sp_account if d.sp_account
                  else "ninguna, así que en_sp está sin dato en todas las filas")
    params = (
        f"Marca del SQP: {d.brand or 'no detectada'}\n"
        f"Cuenta de Amazon Ads de la columna en_sp: {sp_account}\n"
        f"Cifras del módulo sobre todo el MKL:\n{counts}\n"
        + _cap_line(_CLUSTER_CAP, len(d.clusters), len(clusters))
        + _cap_line(_KEYWORD_CAP, len(d.keywords), len(keywords))
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Clusters ({len(clusters)} filas)", "content": _csv(clusters, make_ids(ROW_PREFIX, len(clusters)))},
        {"title": f"Keywords ({len(keywords)} filas)", "content": _csv(keywords)},
    ]
    input_text = (
        "Analizá los clusters según tu rol: decidí cuáles convertir en campañas SBH y en qué orden, dictá el "
        "veredicto sobre lo que ya calculó el módulo, proponé el headline y cerrá con la síntesis ejecutiva. "
        "Citá row_ids exactos del documento."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _cap_line(sentences: tuple[str, str], total: int, sent: int) -> str:
    everything, some = sentences
    if total <= sent:
        return everything.format(total=total) + "\n"
    return some.format(total=total, sent=sent, left=total - sent) + "\n"


def _csv(rows: list, row_ids: list | None = None) -> str:
    frame = pd.DataFrame(rows)
    if row_ids is not None:
        frame.insert(0, "row_id", row_ids)
    # A fixed line ending: the default is the OS's, and Windows and Linux would fingerprint differently.
    return frame.to_csv(index=False, lineterminator="\n")


def _number(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
