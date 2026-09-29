"""What the Account Pulse agent receives and the shape it must answer in.

Serialization only: the week against the prior one, the kind of each day, each week's ACoS and TACoS over the same
days, the Buy Box losses and the campaigns were computed by the module (core/account_pulse/). The AI reads what
changed and whether it calls for action.
"""
from dataclasses import dataclass

import pandas as pd

MAX_DAYS = 120
MAX_BUYBOX_ASINS = 40
MAX_CAMPAIGNS = 40
TOPICS = {"VENTAS": "Ventas", "TRAFICO": "Tráfico y conversión", "PUBLICIDAD": "Publicidad", "BUYBOX": "Buy Box"}
VERDICTS = ("ACTUAR", "VIGILAR", "OK")


@dataclass
class PulseData:
    account: str        # the Amazon Ads account the AM chose, "" when none
    ads_note: str       # why there are no ads figures, "" when there are
    currency_code: str  # the account's, "" when the module does not know the report's currency
    figures: dict       # the module's figures, in the order the page shows them
    days: list          # one record per Business Report day, oldest first
    buybox: list | None  # ASINs below 95% Buy Box, most estimated lost sales first; None without the BR by Child
    campaigns: list     # campaigns with activity over the report's days with ads data, most spend first
    idioma: str = "es"


# razon before veredicto on purpose: autoregressive generation conditions the verdict on the reasoning.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "lecturas": {
            "type": "array",
            "maxItems": 4,
            "description": "una lectura por tema: VENTAS y TRAFICO siempre; PUBLICIDAD sólo si Parámetros trae el "
                           "ACoS y el TACoS; BUYBOX sólo si Parámetros trae datos de Buy Box",
            "items": {
                "type": "object",
                "properties": {
                    "tema": {"enum": list(TOPICS),
                             "description": "VENTAS = ventas y unidades; TRAFICO = sesiones y conversión; PUBLICIDAD "
                                            "= spend, ventas de ads, ACoS y TACoS; BUYBOX = la Buy Box"},
                    "razon": {"type": "string",
                              "description": "una o dos oraciones: qué cambió esta semana contra la anterior y qué lo "
                                             "explica, citando la cifra o el día de los documentos que lo sostiene"},
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
        "synthesis": {
            "type": "object",
            "properties": {
                "situation": {"type": "string",
                              "description": "2-3 oraciones: cómo viene la cuenta esta semana contra la anterior, "
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


def build_context(d: PulseData) -> tuple[str, list, dict]:
    days = d.days[-MAX_DAYS:]
    buybox = d.buybox[:MAX_BUYBOX_ASINS] if d.buybox is not None else None
    campaigns = d.campaigns[:MAX_CAMPAIGNS] if not d.ads_note else None
    caps = _cap_line("días del Business Report", "los más recientes", len(d.days), len(days))
    if buybox is not None:
        caps += _cap_line("ASINs con Buy Box bajo 95%", "los de más ventas perdidas estimadas", len(d.buybox),
                          len(buybox))
    if campaigns is not None:
        caps += _cap_line("campañas con actividad", "las de más spend", len(d.campaigns), len(campaigns))
    figures = "\n".join(f"- {label}: {_figure_text(figure)}" for label, figure in d.figures.items())
    ads = f"ninguno: {d.ads_note}\n" if d.ads_note else "los de la cuenta de arriba\n"
    by_child = "no se subió, así que no hay Buy Box por ASIN" if d.buybox is None else "subido"
    params = (
        f"Cuenta de Amazon Ads del Business Report: {d.account or 'ninguna'}\n"
        f"Datos de ads: {ads}"
        f"Moneda: {d.currency_code or 'la del Business Report, que el módulo no conoce'}\n"
        f"BR by Child: {by_child}\n"
        f"Cifras del módulo:\n{figures}\n"
        + caps
        + f"Idioma de salida: {'en (English)' if d.idioma == 'en' else 'es (español)'}\n"
        "Estos son los únicos valores operativos válidos."
    )
    docs = [
        {"title": "Parámetros", "content": params},
        {"title": f"Días del Business Report ({len(days)} filas)", "content": _csv(days)},
    ]
    if buybox is not None:
        docs.append({"title": f"ASINs con BuyBox bajo 95% ({len(buybox)} filas)",
                     "content": _csv(buybox) if buybox else "ninguno: todos los ASINs con sesiones tienen 95% o más"})
    if campaigns is not None:
        docs.append({"title": f"Campañas con actividad ({len(campaigns)} filas)",
                     "content": _csv(campaigns) if campaigns else "ninguna campaña tuvo actividad en esos días"})
    input_text = (
        "Analizá las cifras del módulo según tu rol: una lectura por tema de qué cambió esta semana contra la anterior "
        "y si pide actuar, y cerrá con la síntesis ejecutiva."
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
