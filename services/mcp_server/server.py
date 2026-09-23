"""Servidor MCP de ppc-manager: lo que la app sabe leer, para que un modelo lo consulte.

POR QUÉ EXISTE
El chat de la app recibe hoy, pegado en el prompt, el último análisis de cada cuenta. Eso no escala:
cada módulo nuevo multiplica el texto y el modelo termina respondiendo con lo que le llegó, sin saber
si algo se truncó. Acá el modelo ve QUÉ hay y baja sólo lo que necesita.

QUÉ NO HACE
- No escribe. Ninguna herramienta modifica nada: es una superficie de lectura.
- No expone credenciales. `integration_credentials` y las columnas selladas no se tocan.
- No devuelve respuestas de tamaño desconocido: todo pasa por services/mcp_server/limits.py.

IDENTIDAD
Un token de servicio, no identidad por persona. Es deliberado y espeja lo que la app ya hace: todo
empleado logueado ve todas las cuentas. El día que haga falta limitar qué cliente ve cada uno, hay
que construir esa capa en la app primero — no tiene sentido que el MCP sea más estricto que la
pantalla de la que sale el dato.

Variables de entorno:
  SUPABASE_URL   PostgREST, alcanzable desde este contenedor.
  MCP_JWT        JWT con rol web_user: sólo lectura.
  MCP_TOKEN      El secreto que el cliente presenta como Bearer. Sin esto, el servidor no arranca.
  MCP_PORT       Puerto HTTP (8790 por defecto).
"""
from __future__ import annotations

import logging
import os
import threading
from functools import partial

from core.integrations.store import _Rest
from services.mcp_server.tools import amazon_ads, analyses, module_results

log = logging.getLogger(__name__)

DEFAULT_PORT = 8790
TOKEN_ENV = "MCP_TOKEN"
JWT_ENV = "MCP_JWT"


class ConfigurationError(RuntimeError):
    """Falta algo sin lo cual arrancar sería peor que no arrancar."""


def rest_from_env() -> _Rest:
    url = os.environ.get("SUPABASE_URL", "").strip()
    jwt = os.environ.get(JWT_ENV, "").strip()
    if not (url and jwt):
        raise ConfigurationError(f"faltan SUPABASE_URL o {JWT_ENV}")
    return _Rest(url, jwt)


def required_token() -> str:
    """El Bearer que el servidor exige.

    Sin token no se arranca en vez de arrancar abierto: un MCP sin auth en la red de la VPS es una
    copia de la base al alcance de cualquier contenedor.
    """
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise ConfigurationError(f"falta {TOKEN_ENV}: el servidor no arranca sin autenticación")
    return token


def authorize(header: str | None, expected: str) -> bool:
    """True sólo con un Bearer que coincida exactamente."""
    if not header or not expected:
        return False
    scheme, _, value = header.partition(" ")
    return scheme.lower() == "bearer" and _constant_time_equals(value.strip(), expected)


def _constant_time_equals(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)


def build_tools(rest) -> list:
    """Las herramientas del servidor, cada una atada a su dominio.

    Sumar un dominio es agregar un módulo en tools/ y una entrada acá: lo que expone un dominio no
    cambia lo que devuelven los otros.
    """
    # partial y no lambda: el SDK lee la firma anotada de cada función para armar el schema que
    # ve el modelo; un lambda se la comería y las herramientas llegarían sin tipos.
    return [
        _tool("list_accounts",
              "Las cuentas de Amazon Ads sincronizadas, con país, moneda, hasta qué día tienen datos, qué día es "
              "hoy en cada una (today, en su zona horaria) y si sus datos están al día (up_to_date). Empezá "
              "por acá para saber qué profile_id usar en las demás herramientas.",
              partial(amazon_ads.list_accounts, rest)),
        _tool("accounts_overview",
              "Los totales de TODAS las cuentas de Amazon Ads en una llamada: gasto, ventas, órdenes, clicks, "
              "ACoS y CVR de cada una en sus últimos días, de sus campañas de Sponsored Products, Brands y Display. "
              "Con source=search_terms, los de Sponsored Products sumados del reporte de search terms, que sólo trae "
              "términos con clicks y por eso muchas menos impresiones. Es lo que hace falta para comparar o rankear "
              "cuentas en vivo sin consultarlas una por una.",
              partial(amazon_ads.accounts_overview, rest)),
        _tool("list_analyses",
              "Índice de análisis de IA guardados: qué cuentas y qué módulos tienen uno, de qué período, "
              "con qué target de ACoS, su situación en pocas líneas y cuándo terminó, en la hora de la cuenta "
              "(finished_at). Alcanza para comparar lo que dicen los análisis de varias cuentas en una llamada. "
              "Pasá profile_id para una sola cuenta.",
              partial(analyses.list_analyses, rest)),
        _tool("get_analysis",
              "El último análisis guardado de una cuenta y un módulo: su síntesis y las filas que citó. Las del "
              "Search Term Report traen el estado que su campaña tiene hoy (campaign_state), no si un negativo "
              "entra al bulk: eso lo da search_term_candidates. Módulos posibles: " + ", ".join(analyses.MODULES)
              + ".",
              partial(analyses.get_analysis, rest)),
        _tool("top_search_terms",
              "Los search terms de mayor gasto de una cuenta de Amazon Ads en los últimos días, cada uno con el "
              "estado actual de su campaña (Campaign Status). Devuelve una página; si hay más, lo dice y da el "
              "offset siguiente.",
              partial(amazon_ads.top_search_terms, rest)),
        _tool("daily_metrics",
              "La serie diaria de una cuenta de Amazon Ads: gasto, ventas, órdenes, clicks, ACoS y CVR por día, "
              "de sus campañas de Sponsored Products, Brands y Display. Es lo que hace falta para contestar cómo "
              "viene o cómo evolucionó una cuenta, un producto o una campaña. product acota a SP, SB o SD; campaign "
              "filtra por parte del nombre de la campaña; days, hasta 60; source=search_terms da la de Sponsored "
              "Products sumada del reporte de search terms, que sólo trae términos con clicks y por eso muchas menos "
              "impresiones.",
              partial(amazon_ads.daily_metrics, rest)),
        _tool("breakdown",
              "Los totales de una cuenta de Amazon Ads en los últimos días, agrupados por campaña, portfolio, "
              "producto (SP, SB, SD), tipo de match, search term o ASIN: gasto, ventas, órdenes, clicks, ACoS y CVR "
              "por grupo, de mayor a menor por sort_by, y el total de la cuenta en totals. Campaña, portfolio y "
              "producto salen de los reportes de campaña de los tres productos; tipo de match, search term y ASIN, del "
              "reporte de search terms, sólo Sponsored Products. El ASIN de cada término sale del producto anunciado "
              "de su ad group, o del nombre de la campaña cuando el ad group anuncia varios, y lo que no se puede "
              "atribuir queda en su propio grupo. asin deja sólo los search terms "
              "de ese ASIN, por ejemplo para ver los que gastan sin vender. Con source=search_terms, campaña, "
              "portfolio y producto (un solo grupo, SP) también salen de ese reporte. Es lo que hace falta para "
              "repartir un total entre sus partes o rankear campañas, portfolios, productos, términos o ASINs, en una "
              "sola llamada.",
              partial(amazon_ads.breakdown, rest)),
        _tool("campaign_health",
              "Las campañas habilitadas de una cuenta de Amazon Ads (Sponsored Products, Brands y Display) en sus "
              "últimos días, cada una con su producto, el diagnóstico de Bulk Campañas (FANTASMA, PAUSAR, REVISAR, "
              "ESCALAR u OK), sus señales (sólo SP: Limitada por presupuesto, Nueva, Baja visibilidad), su estrategia "
              "de puja, su presupuesto y sus métricas. Sale de la foto de campañas, así que cuenta también las que no "
              "tuvieron actividad, que breakdown no ve. Es lo que hace falta para contestar qué campañas pausar, "
              "escalar o revisar, cuáles no entregan o cuáles se quedan sin presupuesto. product acota todo a SP, SB "
              "o SD; diagnosis y signal filtran filas; counts y totals cubren todas las habilitadas del alcance; "
              "parameters.rules dice la regla y los umbrales de cada diagnóstico. "
              "date_from y date_to (AAAA-MM-DD) piden el período exacto que el AM tiene en pantalla, y target_acos, "
              "spend_to_pause y min_orders_to_scale, sus umbrales.",
              partial(amazon_ads.campaign_health, rest)),
        _tool("idle_targets",
              "Target Graduation de una cuenta de Amazon Ads: los keywords y targets habilitados, de campañas "
              "habilitadas de Sponsored Products, Brands y Display, que no tuvieron una impresión en los últimos "
              "días, con su campaña, tipo, match type y bid. El bid es el efectivo: el propio del target o, si no "
              "tiene, el default de su ad group. Los de ad groups de Sponsored Products listados como pausados no se "
              "miran. counts dice por producto cuántos se miraron y cuántos no tuvieron impresiones. Es lo que hace "
              "falta para contestar qué targets pausar o a cuáles subirles la puja. product acota a SP, SB o SD; "
              "date_from y date_to (AAAA-MM-DD), el período exacto.",
              partial(amazon_ads.idle_targets, rest)),
        _tool("campaign_structure",
              "La estructura de las campañas de Sponsored Products de una cuenta de Amazon Ads, como Amazon Ads la "
              "listó por última vez (listed_at dice cuándo): de cada campaña, su presupuesto, su estrategia de puja y "
              "sus ajustes por placement (entity=campaigns, o placements de a uno por fila); sus ad groups con su bid "
              "default (ad_groups); sus keywords y product targets con su bid efectivo, el propio o el default de su "
              "ad group (bid_source dice cuál), también los que no tuvieron tráfico (keywords, product_targets); sus "
              "product ads con ASIN y SKU (product_ads), y sus negativos de campaña y de ad group (negatives). "
              f"Más de {amazon_ads.MAX_ACCOUNT_NEGATIVES} negativos los da sólo de a una campaña: sin campaign, o con "
              "uno que abarca varias campañas, negatives vuelve con counts y sin filas. "
              "campaign filtra por parte del nombre o por el id de la campaña; state, por enabled, paused o archived. "
              "counts dice cuántos hay de cada tipo en la cuenta o en las campañas filtradas. Campañas, keywords y "
              "product targets traen sus métricas de la ventana cuando hay reportes; date_from y date_to (AAAA-MM-DD) "
              "piden el período exacto.",
              partial(amazon_ads.campaign_structure, rest)),
        _tool("funnel_coverage",
              "Análisis de Funnel de una cuenta de Amazon Ads, con las mismas reglas del módulo: las campañas "
              "activas de Sponsored Products que no tuvieron ni un search term con clicks (section=idle_campaigns), "
              "los search terms que vinieron de campañas pausadas o que ya no existen, con la campaña sugerida para "
              "cada uno (gap_terms), y los términos para cosechar como keyword, con su match type sugerido y si "
              "corren en alguna campaña activa (harvest). counts trae las tres listas y las órdenes y ventas de los "
              "search terms de campañas activas, de las pausadas o inexistentes y de todos. Para lo que el AM ve en "
              "pantalla, usá su date_from, date_to, min_orders y match_type.",
              partial(module_results.funnel_coverage, rest)),
        _tool("search_term_candidates",
              "Los candidatos del Search Term Report de una cuenta de Amazon Ads, con las mismas reglas del módulo: "
              "a negativizar, con su regla, su acción y su prioridad (section=negatives), o a harvest, con su regla, "
              "su prioridad y el bid sugerido (section=harvest), cada uno con el estado actual de su campaña y la "
              "sección sumada en totals. Cada negativo dice si entra al bulk del módulo (in_bulk) y, si no, por qué "
              "(bulk_exclusion); totals_in_bulk suma sólo los que entran. Arranca de los parámetros guardados de la "
              "cuenta, o de los valores por "
              "defecto del módulo si no guardó ninguno; price, harvest_price, harvest_target_acos, "
              "harvest_min_clicks y portfolios los reemplazan. Para lo que el AM ve en pantalla, usá sus fechas y "
              "sus valores.",
              partial(module_results.search_term_candidates, rest)),
        _tool("bid_suggestions",
              "El Bid Optimizer de una cuenta de Amazon Ads, con las mismas reglas del módulo: el bid sugerido de "
              "cada ASIN (CVR × precio × target ACoS) y su semáforo por CVR, con el precio promedio de venta del "
              "período, de mayor a menor gasto. target_acos reemplaza el guardado de la cuenta.",
              partial(module_results.bid_suggestions, rest)),
        _tool("asin_health",
              "PPC Insights de una cuenta de Amazon Ads, con las mismas reglas del módulo: el health score (0-100) de "
              "cada ASIN con sus partes, su gasto, ACoS, CVR y el gasto de sus términos que no vendieron, de mayor a "
              "menor gasto. Sin el SQP, el Business Report ni el Campaign CSV, que se suben a mano en el módulo: "
              "esas partes del score valen su punto neutro. target_acos reemplaza el guardado de la cuenta.",
              partial(module_results.asin_health, rest)),
    ]


def _tool(name: str, description: str, fn) -> dict:
    # El SDK nombra el schema de argumentos con fn.__name__, y un partial no lo trae. Se lo damos
    # sin tocar __wrapped__: si lo pusiéramos, inspect.signature volvería a mostrar el `rest` ya
    # aplicado y el modelo vería un parámetro que no puede completar.
    if not hasattr(fn, "__name__"):
        fn.__name__ = name
    return {"name": name, "description": description, "fn": fn}


def _idle_forever() -> None:
    threading.Event().wait()


def run(idle=_idle_forever) -> int:
    """Arranca el servidor HTTP. Si falta configuración, no sirve nada y lo dice una vez.

    Queda quieto en vez de salir, como los workers: con `restart: unless-stopped` un proceso que
    sale por un secreto faltante reinicia en loop, y el healthcheck ya lo muestra unhealthy.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        token = required_token()
        rest = rest_from_env()
    except ConfigurationError as exc:
        log.error("mcp-server no puede arrancar: %s", exc)
        idle()
        return 2

    from services.mcp_server.http_app import serve

    port = int(os.environ.get("MCP_PORT", DEFAULT_PORT))
    log.info("mcp-server escuchando en :%d con %d herramientas", port, len(build_tools(rest)))
    serve(tools=build_tools(rest), token=token, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
