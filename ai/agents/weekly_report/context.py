"""What the Weekly Client Report agent receives and the shape it must answer in.

Serialization only: the account's week against the prior one, the per-product figures, the ads by ASIN of Atom 11 and
the account's advertising from the synced campaign reports were computed by the module. The AI reads the week, says
whether each topic calls for action, and drafts the summary the AM sends to the client.
"""
from dataclasses import dataclass

import pandas as pd

MAX_PRODUCTS = 40
TOPICS = {"VENTAS": "Ventas", "TRAFICO": "Tráfico y conversión", "PUBLICIDAD": "Publicidad", "BUYBOX": "Buy Box"}
VERDICTS = ("ACTUAR", "VIGILAR", "OK")


@dataclass
class WeeklyData:
    client: str          # the client's name the AM wrote, "" when none
    account: str         # the Amazon Ads account the AM chose, "" when none
    ads_note: str        # why there is no account advertising, "" when there is
    currency_code: str   # the account's, "" when the module does not know the report's currency
    figures: dict        # the module's figures, in the order the report shows them
    products: list       # one record per ASIN of the BR by Child, most sales first
    campaigns: list      # the Advertising sheet's top campaigns, most spend first
    portfolios: list     # the Advertising sheet's portfolios, most spend first
    changelog: str       # the technical changes the AM wrote for the week, "" when none
    idioma: str = "es"


_SYNTHESIS = {
    "type": "object",
    "properties": {
        "situation": {"type": "string",
                      "description": "2-3 oraciones para el AM: cómo viene la cuenta esta semana contra la anterior, "
                                     "anclado en una cifra del documento"},
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
                              "description": "2 oraciones copiables a Slack: cifras primero, cero adjetivos sin número"},
    },
    "required": ["situation", "week_actions", "mid_term", "risks", "executive_summary"],
    "additionalProperties": False,
}

# razon before veredicto, and the client's summary last, on purpose: autoregressive generation conditions each part on
# what it already wrote.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "lecturas": {
            "type": "array",
            "maxItems": 4,
            "description": "una lectura por tema: VENTAS y TRAFICO siempre; PUBLICIDAD sólo si Parámetros trae datos "
                           "de ads; BUYBOX sólo si Parámetros trae datos de Buy Box",
            "items": {
                "type": "object",
                "properties": {
                    "tema": {"enum": list(TOPICS),
                             "description": "VENTAS = ventas y unidades; TRAFICO = sesiones y conversión; PUBLICIDAD "
                                            "= spend, ventas de ads, ACoS y TACoS; BUYBOX = la Buy Box"},
                    "razon": {"type": "string",
                              "description": "una o dos oraciones: qué cambió esta semana contra la anterior y qué lo "
                                             "explica, citando la cifra de los documentos que lo sostiene"},
                    "veredicto": {"enum": list(VERDICTS),
                                  "description": "ACTUAR = pide una acción esta semana; VIGILAR = un cambio que "
                                                 "todavía no alcanza para actuar; OK = nada que pida acción"},
                    "advertencia": {"type": ["string", "null"],
                                    "description": "riesgo concreto o dato que falta antes de actuar, o null"},
                },
                "required": ["tema", "razon", "veredicto", "advertencia"],
                "additionalProperties": False,
            },
        },
        "synthesis": _SYNTHESIS,
        "resumen_cliente": {
            "type": "object",
            "description": "el resumen semanal que el AM le manda al cliente, en el idioma de salida",
            "properties": {
                "situacion": {"type": "string",
                              "description": "2-3 oraciones: si fue una buena o una mala semana y qué la movió, con "
                                             "una cifra"},
                "highlights": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                               "description": "los logros de la semana, cada uno con su cifra"},
                "atencion": {"type": "array", "items": {"type": "string"}, "maxItems": 2,
                             "description": "lo que el cliente tiene que saber: una alerta con su cifra"},
                "proximos_pasos": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                                   "description": "lo que el equipo va a hacer la semana que viene"},
            },
            "required": ["situacion", "highlights", "atencion", "proximos_pasos"],
            "additionalProperties": False,
        },
    },
    "required": ["lecturas", "synthesis", "resumen_cliente"],
    "additionalProperties": False,
}


def build_context(d: WeeklyData) -> tuple[str, list, dict]:
    products = d.products[:MAX_PRODUCTS]
    caps = _cap_line("productos del BR by Child", "los de más ventas", len(d.products), len(products))
    figures = "\n".join(f"- {label}: {_figure_text(figure)}" for label, figure in d.figures.items())
    ads = f"ninguna: {d.ads_note}\n" if d.ads_note else "la de la cuenta de arriba\n"
    params = (
        f"Cliente: {d.client or 'sin nombre'}\n"
        f"Cuenta de Amazon Ads del Business Report: {d.account or 'ninguna'}\n"
        f"Publicidad de la cuenta: {ads}"
        f"Moneda: {d.currency_code or 'la del Business Report, que el módulo no conoce'}\n"
        f"Cifras del módulo:\n{figures}\n"
        + caps
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Productos ({len(products)} filas)",
         "content": _csv(products) if products else "no se subió el BR by Child"},
    ]
    if not d.ads_note:
        docs.append({"title": f"Campañas de más spend ({len(d.campaigns)} filas)",
                     "content": _csv(d.campaigns) if d.campaigns else "ninguna campaña tuvo actividad en esos días"})
        docs.append({"title": f"Portfolios ({len(d.portfolios)} filas)",
                     "content": _csv(d.portfolios) if d.portfolios else "ninguno"})
    if d.changelog:
        docs.append({"title": "Cambios de la semana, escritos por el AM", "content": d.changelog})
    input_text = (
        "Analizá la semana según tu rol: una lectura por tema de qué cambió contra la anterior y si pide actuar, la "
        "síntesis ejecutiva para el AM y el resumen para el cliente."
    )
    return input_text, docs, OUTPUT_SCHEMA


def _cap_line(what: str, which: str, total: int, sent: int) -> str:
    if total <= sent:
        return f"Viajaron todos los {what}: {total}.\n"
    return f"De {total} {what} viajaron {sent}, {which}; el resto ({total - sent}) no existe para vos.\n"


def _csv(rows: list) -> str:
    # A fixed line ending: the default is the OS's, and Windows and Linux would fingerprint differently.
    return pd.DataFrame(rows).to_csv(index=False, lineterminator="\n")


def _figure_text(figure) -> str:
    if isinstance(figure, str):
        return figure
    number = float(figure)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
