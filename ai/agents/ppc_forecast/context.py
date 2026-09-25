"""What the PPC Forecast agent receives and the shape it must answer in.

Serialization only: the projection, the growth target, the split between ad and organic sales and the spend estimate
were computed by the module (core/ppc_forecast/). The AI judges how far each figure can be trusted.
"""
from dataclasses import dataclass

import pandas as pd

MAX_HISTORY_DAYS = 180
TOPICS = {"PROYECCION": "Proyección de ventas", "PRESUPUESTO": "Spend estimado para el objetivo"}
CONFIDENCE_LEVELS = ("alta", "media", "baja")
_HISTORY_CAP = ("Viajaron todos los días del Business Report: {total}.",
                "De {total} días del Business Report viajaron los {sent} más recientes; los {left} anteriores no "
                "existen para vos.")


@dataclass
class ForecastData:
    account: str        # the Amazon Ads account the AM chose, "" when none
    ads_note: str       # why there are no ads figures, "" when there are
    currency_code: str  # the account's, "" when the module does not know the report's currency
    figures: dict       # the module's figures, in the order the page shows them
    history: list       # one record per Business Report day, oldest first
    projection: list    # one record per projected day
    idioma: str = "es"


# razon before confianza on purpose: autoregressive generation conditions the confidence on the reasoning.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "lecturas": {
            "type": "array",
            "maxItems": 2,
            "description": "una lectura por cifra del módulo: PROYECCION siempre; PRESUPUESTO sólo si Parámetros trae "
                           "el spend estimado para el objetivo",
            "items": {
                "type": "object",
                "properties": {
                    "tema": {"enum": list(TOPICS),
                             "description": "PROYECCION = las ventas proyectadas del horizonte; PRESUPUESTO = el "
                                            "spend estimado para el objetivo"},
                    "razon": {"type": "string",
                              "description": "una o dos oraciones: qué tanto se puede confiar en esa cifra y por qué, "
                                             "citando la cifra o el día de los documentos que lo sostiene"},
                    "confianza": {"enum": list(CONFIDENCE_LEVELS),
                                  "description": "baja obliga a formular la razón como algo a verificar"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto antes de usar la cifra, o null"},
                },
                "required": ["tema", "razon", "confianza", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: hacia dónde van las ventas y, si hay datos de ads, "
                                             "cuánto dependen de ads, anclado en una cifra del documento"},
                "week_actions": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                                 "description": "acciones de esta semana: verbo + una cifra + qué se decide"},
                "mid_term": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                             "description": "qué revisar en 2 a 4 semanas"},
                "risks": {
                    "type": "array",
                    "maxItems": 4,
                    "description": "solo riesgos que se sostengan con una cifra o un día concreto de los documentos",
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
    "required": ["lecturas", "synthesis"],
    "additionalProperties": False,
}


def build_context(d: ForecastData) -> tuple[str, list, dict]:
    history = d.history[-MAX_HISTORY_DAYS:]
    figures = "\n".join(f"- {label}: {_figure_text(figure)}" for label, figure in d.figures.items())
    ads = f"ninguno: {d.ads_note}\n" if d.ads_note else "los de la cuenta de arriba\n"
    params = (
        f"Cuenta de Amazon Ads del Business Report: {d.account or 'ninguna'}\n"
        f"Datos de ads: {ads}"
        f"Moneda: {d.currency_code or 'la del Business Report, que el módulo no conoce'}\n"
        f"Cifras del módulo:\n{figures}\n"
        + _cap_line(len(d.history), len(history))
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Historia diaria ({len(history)} filas)", "content": _csv(history)},
        {"title": f"Proyección diaria ({len(d.projection)} filas)", "content": _csv(d.projection)},
    ]
    input_text = (
        "Analizá las cifras del módulo según tu rol: juzgá qué tanto se puede confiar en la proyección y, si hay "
        "datos de ads, en el spend estimado para el objetivo, y cerrá con la síntesis ejecutiva."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _cap_line(total: int, sent: int) -> str:
    everything, some = _HISTORY_CAP
    if total <= sent:
        return everything.format(total=total) + "\n"
    return some.format(total=total, sent=sent, left=total - sent) + "\n"


def _csv(rows: list) -> str:
    # A fixed line ending: the default is the OS's, and Windows and Linux would fingerprint differently.
    return pd.DataFrame(rows).to_csv(index=False, lineterminator="\n")


def _figure_text(figure) -> str:
    if isinstance(figure, str):
        return figure
    number = float(figure)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
