"""What the Radar Amazon agent receives and the shape it must answer in.

Serialization only: which items passed the date and link checks, and each topic's confidence label, are decided
in core/radar. The AI groups items into topics and writes them.
"""
import json
from dataclasses import dataclass

from ai.agents import make_ids

ROW_PREFIX = "R"
MAX_TOPICS = 8


@dataclass
class RadarData:
    week_label: str   # "semana del 2026-09-21"
    items: list       # dicts with source, person, is_official, published, title, text; newest first


# item_ids first on purpose: the topic is written from the items it already committed to.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "maxItems": MAX_TOPICS,
            "description": "los temas elegidos; vacío es una respuesta válida",
            "items": {
                "type": "object",
                "properties": {
                    "item_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                 "description": "ids exactos del documento que respaldan el tema"},
                    "title_es": {"type": "string", "description": "titular en español, hasta 90 caracteres"},
                    "summary_es": {"type": "string",
                                   "description": "2 a 4 oraciones, sólo con lo que dicen los textos citados"},
                    "implications_es": {"type": "string",
                                        "description": "qué significa para la agencia, 1 o 2 oraciones"},
                    "rank": {"type": "integer", "minimum": 1, "description": "1 = el más importante"},
                },
                "required": ["item_ids", "title_es", "summary_es", "implications_es", "rank"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["topics"],
    "additionalProperties": False,
}


def item_ids(n: int) -> list:
    return make_ids(ROW_PREFIX, n)


def build_context(d: RadarData) -> tuple[str, list, dict]:
    ids = item_ids(len(d.items))
    rows = [{"id": row_id, "fuente": item["source"], "referente": item["person"],
             "es_oficial": item["is_official"], "publicado": item["published"],
             "titulo": item["title"], "texto": item["text"]}
            for row_id, item in zip(ids, d.items)]
    docs = [
        {"title": "Semana", "content": f"Radar de la {d.week_label}. Viajaron {len(rows)} items verificados."},
        # JSON, not delimited text: a feed's text cannot close its own item and open a fake one.
        {"title": f"Items ({len(rows)})", "content": json.dumps(rows, ensure_ascii=False, indent=1)},
    ]
    input_text = ("Armá el Radar de esta semana según tu rol: agrupá los items por tema, elegí hasta "
                  f"{MAX_TOPICS} y citá los ids exactos que respaldan cada uno.")
    return input_text, docs, OUTPUT_SCHEMA
