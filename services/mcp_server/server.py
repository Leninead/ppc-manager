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
from services.mcp_server.tools import (
    amazon_ads,
    analyses,
    breakdown,
    campaign_structure,
    daily_series,
    module_results,
)

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


# Every per-account tool takes the account by name as well as by id: a question names a client, not a profile_id.
ACCOUNT_HINT = (" account, en lugar de profile_id, toma la cuenta por parte de su nombre; si nombra a varias, vuelve "
                "candidates con el gasto de cada una para elegir.")


def _filters_hint(extra: str = "") -> str:
    """How filters and sort_order read, with the metrics a tool's rows add to the common ones."""
    return (" filters recibe cotas por métrica en un objeto, por ejemplo {\"min_orders\": 2, \"max_acos\": 30}: "
            "min_ y max_ de spend, sales, orders, clicks, impressions, acos, cvr, roas y cpc" + extra + ", "
            "without_sales (gastó sin vender) y combine (all, por defecto, las cumple todas; any, alguna). "
            "sort_order=asc ordena de menor a mayor; las filas sin el valor van siempre al final.")


COMPARE_HINT = (" compare=previous (o compare_from y compare_to, AAAA-MM-DD) pone cada fila al lado del período "
                "anterior del mismo largo: delta_spend_pct, delta_sales_pct, delta_orders_pct, delta_acos_pp, "
                "previous_spend, previous_sales y delta_<métrica> de la que ordena, en sus unidades; status=new o gone "
                "cuando empezó o dejó de tener actividad; totals.previous el total de antes; leaders la mayor suba y la "
                "mayor caída. order_by_change ordena por ese cambio.")
CAMPAIGNS_HINT = (" campaign nombra una campaña: su id, su nombre exacto o, si ninguna se llama así, parte del nombre; "
                  "campaigns, una lista de nombres exactos o ids; portfolio, un portfolio. matched_campaigns dice "
                  "cuáles tomó y campaign_match cómo.")


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
              "hoy en cada una (today, en su zona horaria) y si sus datos están al día (up_to_date). Para un "
              "cliente, pasá account con parte de su nombre (sin importar mayúsculas, tildes, espacios ni guiones): "
              "vienen sólo sus cuentas, de todos los países, en una llamada. Las demás herramientas aceptan el mismo "
              "account, así que para leer una cuenta no hace falta pasar antes por acá. Devuelve una página; si hay "
              "más, lo dice y da el offset siguiente.",
              partial(amazon_ads.list_accounts, rest)),
        _tool("accounts_overview",
              "Los totales de TODAS las cuentas de Amazon Ads en una llamada, o de las que llevan account en el "
              "nombre: gasto, ventas, órdenes, clicks, ACoS, CVR, ROAS y CPC de cada una en sus últimos días, de sus "
              "campañas de Sponsored Products, Brands y Display, o sólo de product (SP, SB o SD; con SB o SD, también "
              "sus órdenes y ventas de clientes nuevos para la marca, ntb_orders, ntb_sales y ntb_sales_share). Cada "
              "cuenta dice si gastó más de lo que vendió (spend_exceeds_sales) o gastó sin vender (without_sales), y "
              "counts las cuenta sobre todas las cuentas de la respuesta, no sólo la página; attribution_days, a "
              "cuántos días cuenta una venta cada producto. date_from y date_to (AAAA-MM-DD) piden el mismo período "
              "exacto para todas —un mes, el anterior, del 10 al 22—; una cuenta sin datos en esas fechas vuelve "
              "sin cifras y con window_note." + COMPARE_HINT + " Con source=search_terms, los de Sponsored Products "
              "sumados del reporte de search terms, que sólo trae términos con clicks y por eso muchas menos "
              "impresiones. Es lo que hace falta para comparar o rankear cuentas en vivo sin consultarlas una por "
              "una. Devuelve una página; si hay más, lo dice y da el offset siguiente.",
              partial(amazon_ads.accounts_overview, rest)),
        _tool("list_analyses",
              "Índice de análisis de IA guardados: qué cuentas y qué módulos tienen uno, de qué período, "
              "con qué target de ACoS, su situación en pocas líneas y cuándo terminó, en la hora de la cuenta "
              "(finished_at). Alcanza para comparar lo que dicen los análisis de varias cuentas en una llamada. "
              "Pasá profile_id para una sola cuenta, o account para las de un cliente.",
              partial(analyses.list_analyses, rest)),
        _tool("get_analysis",
              "El último análisis guardado de una cuenta y un módulo: su síntesis, row_summary (cuántas filas tiene "
              "cada grupo, cuántas toman cada valor de sus categorías —diagnóstico, estado, prioridad— y sus "
              "métricas sumadas, sobre todas las filas) y una página de las filas que citó; group elige un grupo y "
              "offset/limit su página. where deja sólo las filas cuyos campos de categoría tienen esos valores, por "
              "ejemplo {\"Prioridad\": \"Alta\"}: rows y row_summary pasan a ser de ese subconjunto y matched_rows "
              "dice cuántas son, con sus row_id de siempre. Las del Search Term Report traen el estado que su campaña "
              "tiene hoy (campaign_state), no si un negativo entra al bulk: eso lo da search_term_candidates. "
              "Módulos posibles: " + ", ".join(analyses.MODULES) + "." + ACCOUNT_HINT,
              partial(analyses.get_analysis, rest)),
        _tool("top_search_terms",
              "Los search terms de mayor gasto de una cuenta de Amazon Ads en los últimos días, cada uno con el "
              "estado actual de su campaña (Campaign Status). Devuelve una página; si hay más, lo dice y da el "
              "offset siguiente." + ACCOUNT_HINT,
              partial(amazon_ads.top_search_terms, rest)),
        _tool("daily_metrics",
              "La serie de una cuenta de Amazon Ads por día, semana o mes: gasto, ventas, órdenes, clicks, ACoS, CVR, "
              "ROAS y CPC de sus campañas de Sponsored Products, Brands y Display. Es lo que hace falta para "
              "contestar cómo viene o cómo evolucionó una cuenta, un producto o una campaña. granularity=week o month "
              "suma de a semanas (de lunes a domingo) o meses de calendario: periods pide cuántos, hasta 26 semanas o "
              "12 meses, y cada fila trae period_start, period_end, days_with_data y complete (false en el período "
              "en curso o cortado por el inicio de los datos, data_since). Por día, days (hasta 60) o date_from y "
              "date_to (AAAA-MM-DD); cada día trae su weekday. product acota a SP, SB o SD (con SB o SD, también "
              "ntb_orders, ntb_sales y ntb_sales_share)." + CAMPAIGNS_HINT + " Cuando suma varias campañas, "
              "by_campaign trae lo de cada una. activity dice el primer día con clicks y con gasto y desde cuándo "
              "viene la racha actual; before_window, los extremos de cada métrica en los días anteriores a la "
              "ventana. source=search_terms da la de Sponsored Products sumada del reporte de search terms, que sólo "
              "trae términos con clicks y por eso muchas menos impresiones." + ACCOUNT_HINT,
              partial(daily_series.daily_metrics, rest)),
        _tool("breakdown",
              "Los totales de una cuenta de Amazon Ads en los últimos días, o en un período exacto con date_from y "
              "date_to (AAAA-MM-DD, hasta 60 días), agrupados por campaña, portfolio, producto (SP, SB, SD), tipo de "
              "match, search term o ASIN: gasto, ventas, órdenes, clicks, ACoS, CVR, ROAS y CPC por grupo, ordenados "
              "por sort_by (también ctr o aov, que entonces viajan en la fila), en totals la suma de todos los grupos "
              "con su CTR y su ticket promedio (aov), y en leaders, sobre todos los grupos, el de más gasto, ventas, "
              "órdenes y clicks, el de ACoS más bajo y más alto entre los que vendieron, y cuántos gastaron sin "
              "vender. Cada grupo trae su parte del total en spend_share, sales_share, orders_share y clicks_share "
              "(%). Por campaña, cada fila es una campaña con su campaign_id, producto, portfolio, estado y "
              "presupuesto diario; los grupos que suman varias campañas dicen cuántas en campaigns. Los que salen de "
              "search terms traen spend_without_sales: lo que gastaron sus términos que no vendieron nada en su "
              "campaña. campaign_search_term agrupa cada término dentro de su campaña y su ad group, y other_campaigns "
              "dice en cuántas otras corrió y cuánto gastó ahí; search_term suma el término en todas sus campañas. "
              "Tipo de match separa exact, phrase, broad, la automática y el product targeting por ASIN y por "
              "categoría. Campaña, portfolio y producto salen de los reportes de campaña de los tres productos, y su "
              "totals es el total de la cuenta en el período (con SB y SD, ntb_orders, ntb_sales y "
              "ntb_sales_share); tipo de match, search term y ASIN salen del reporte de search terms, sólo Sponsored "
              "Products: su totals es el de Sponsored Products, no el de la cuenta. El ASIN de cada término sale del producto anunciado "
              "de su ad group, o del nombre de la campaña cuando el ad group anuncia varios: cada ASIN dice por cuál "
              "de los dos se le atribuyó la mayor parte de su gasto (attributed_by) y en cuántas campañas tiene un "
              "anuncio propio (advertised_in), y totals lo que no se pudo atribuir (unattributed_spend y "
              "unattributed_sales). asin deja sólo los search terms de ese ASIN y match_type (exact, phrase, broad, "
              "auto, asin o category) los de ese tipo." + CAMPAIGNS_HINT + " state acota a las campañas en ese "
              "estado." + _filters_hint() + COMPARE_HINT + " by_period=week o month agrega a los "
              "primeros series_groups grupos su gasto y su ACoS en cada semana o mes de la ventana (series) y si "
              "subieron entre los dos últimos períodos completos (trend). Con source=search_terms, campaña, portfolio "
              "y producto (un solo grupo, SP) también salen de ese reporte. Es lo que hace falta para repartir un "
              "total entre sus partes o rankear campañas, portfolios, productos, términos o ASINs, en una sola "
              "llamada." + ACCOUNT_HINT,
              partial(breakdown.breakdown, rest)),
        _tool("campaign_health",
              "Las campañas habilitadas de una cuenta de Amazon Ads (Sponsored Products, Brands y Display) en sus "
              "últimos días, cada una con su producto, el diagnóstico de Bulk Campañas (FANTASMA, PAUSAR, REVISAR, "
              "ESCALAR u OK), sus señales (sólo SP: Limitada por presupuesto, Nueva, Baja visibilidad), su estrategia "
              "de puja, su presupuesto y sus métricas, con ROAS y CPC; las de SB y SD, también ntb_orders, ntb_sales "
              "y ntb_sales_share. Sale de la foto de campañas, así que cuenta también las que no "
              "tuvieron actividad, que breakdown no ve. Es lo que hace falta para contestar qué campañas pausar, "
              "escalar o revisar, cuáles no entregan o cuáles se quedan sin presupuesto. No da el total de la cuenta: "
              "deja afuera las campañas pausadas o archivadas, que también gastaron en el período; ese total sale de "
              "breakdown o daily_metrics. product acota todo a SP, SB "
              "o SD; diagnosis y signal filtran filas; counts y totals cubren todas las habilitadas del alcance; "
              "parameters.rules dice la regla y los umbrales de cada diagnóstico, y parameters.signal_rules los de "
              "cada señal. Cada fila de SP trae budget_capped_days: los días en que gastó al menos el 95% de su "
              "presupuesto del día, esté o no dentro del target; min_budget_capped_days deja las que lo tocaron al "
              "menos esos días. budget_capped cuenta y lista todas las que lo tocaron algún día, con su diagnóstico, "
              "sus días y su ACoS; signal_counts cuenta cada señal por diagnóstico, y diagnosis_by_product cada "
              "diagnóstico por producto, todo antes de cualquier filtro. "
              "date_from y date_to (AAAA-MM-DD) piden el período exacto que el AM tiene en pantalla, y target_acos, "
              "spend_to_pause y min_orders_to_scale, sus umbrales." + CAMPAIGNS_HINT + _filters_hint()
              + COMPARE_HINT + ACCOUNT_HINT,
              partial(amazon_ads.campaign_health, rest)),
        _tool("idle_targets",
              "Target Graduation de una cuenta de Amazon Ads: los keywords y targets habilitados, de campañas "
              "habilitadas de Sponsored Products, Brands y Display, que no tuvieron una impresión en los últimos "
              "días, con su campaña, tipo, match type y bid. El bid es el efectivo: el propio del target o, si no "
              "tiene, el default de su ad group. Los de ad groups de Sponsored Products listados como pausados no se "
              "miran. counts dice por producto cuántos se miraron y cuántos no tuvieron impresiones. Es lo que hace "
              "falta para contestar qué targets pausar o a cuáles subirles la puja. product acota a SP, SB o SD; "
              "date_from y date_to (AAAA-MM-DD), el período exacto." + ACCOUNT_HINT,
              partial(amazon_ads.idle_targets, rest)),
        _tool("campaign_structure",
              "La estructura de las campañas de una cuenta de Amazon Ads, como Amazon Ads la listó por última vez "
              "(listed_at dice cuándo). De Sponsored Products: de cada campaña, su presupuesto, su estrategia de puja "
              "y sus ajustes por placement (entity=campaigns, o placements de a uno por fila); sus ad groups con su "
              "bid default (ad_groups); sus keywords y product targets con su bid efectivo, el propio o el default de "
              "su ad group (bid_source dice cuál), también los que no tuvieron tráfico (keywords, product_targets); "
              "sus product ads con ASIN y SKU (product_ads: cada fila es un anuncio, y distinct cuenta los ASINs y "
              "SKUs distintos), y sus negativos de campaña y de ad group (negatives). De Sponsored Brands o Display, "
              "con product=SB o SD, sus keywords y product targets, con las ventas de Campaign Manager y cost_type: "
              "en una campaña VCPM el bid es por mil impresiones visibles, no por click. "
              f"Más de {campaign_structure.MAX_ACCOUNT_NEGATIVES} negativos los da sólo de a una campaña: sin "
              "campaign, o con uno que abarca varias campañas, negatives vuelve con counts y sin filas."
              + CAMPAIGNS_HINT + " state filtra las filas por enabled, paused o archived. target deja los keywords, "
              "product targets o negativos que contienen ese texto, o los product ads con ese ASIN o SKU, en "
              "cualquier campaña, primero los que son exactamente ese texto (exact_matches dice cuántos son). "
              "targets pregunta por una lista de hasta 50 keywords o ASINs en una llamada y devuelve una fila por "
              "término: found, running, sus match types, en qué campañas está con su bid, y sus métricas; con "
              "match=exact el keyword es exactamente el término y el product target apunta exactamente a ese ASIN, "
              "con match=contains lo contiene. Es lo que hace falta para saber si la cuenta ya pauta una o varias "
              "keywords, o si un ASIN es suyo sin recorrer todos sus anuncios. Ad groups, keywords, targets, anuncios y negativos traen el "
              "estado de su campaña (campaign_state): corren sólo si ellos y su campaña están habilitados. counts "
              "dice cuántos hay de cada tipo en la cuenta o en las campañas pedidas. Keywords y product targets "
              "traen cpc, bid_gap (el bid menos el cpc, sólo con clicks y bid por click) y top_of_search_share. "
              "En campañas, "
              "keywords y product targets, running_only deja lo que corre, match_type (exact, phrase, broad, o asin "
              "y category para product targets) acota el tipo y sort_by ordena por una métrica o por bid_gap: «las 10 "
              "peores keywords» o «las que gastan sin vender» salen enteras y contadas en total, en una llamada."
              + _filters_hint(" (y bid_gap en keywords y product targets)") + " Las métricas son de la "
              "ventana cuando hay reportes; date_from y date_to (AAAA-MM-DD) piden el período exacto." + ACCOUNT_HINT,
              partial(campaign_structure.campaign_structure, rest)),
        _tool("funnel_coverage",
              "Análisis de Funnel de una cuenta de Amazon Ads, con las mismas reglas del módulo: las campañas "
              "activas de Sponsored Products que no tuvieron ni un search term con clicks (section=idle_campaigns), "
              "los search terms que vinieron de campañas pausadas o que ya no existen, con la campaña sugerida para "
              "cada uno (gap_terms), y los términos para cosechar como keyword, con su match type sugerido y si "
              "corren en alguna campaña activa (harvest). counts trae las tres listas y las órdenes y ventas de los "
              "search terms de campañas activas, de las pausadas o inexistentes y de todos. Para lo que el AM ve en "
              "pantalla, usá su date_from, date_to, min_orders y match_type." + ACCOUNT_HINT,
              partial(module_results.funnel_coverage, rest)),
        _tool("search_term_candidates",
              "Los candidatos del Search Term Report de una cuenta de Amazon Ads, con las mismas reglas del módulo: "
              "a negativizar, con su regla, su acción y su prioridad (section=negatives), o a harvest, con su regla, "
              "su prioridad y el bid sugerido (section=harvest), cada uno con el estado actual de su campaña y la "
              "sección sumada en totals. Cada negativo dice si entra al bulk del módulo (in_bulk) y, si no, por qué "
              "(bulk_exclusion); totals_in_bulk suma sólo los que entran. Cada harvest dice si la cuenta ya tiene ese "
              "término en exact —una keyword exact o, si el término es un ASIN, un product target asin=\"…\"— "
              "(exact_in_account: corre, no corre —ella o su campaña están pausadas— o no está) y en qué campañas "
              "corre, y "
              "cada candidato dice si su término es un ASIN que la cuenta anuncia (own_asin: producto propio, no de "
              "la competencia), y "
              "counts lo cuenta; without_running_exact deja sólo los harvest sin una exact que corra, con counts "
              "de todos. Arranca de los parámetros guardados de la "
              "cuenta, o de los valores por "
              "defecto del módulo si no guardó ninguno; price, harvest_price, harvest_target_acos, "
              "harvest_min_clicks y portfolios los reemplazan. Para lo que el AM ve en pantalla, usá sus fechas y "
              "sus valores." + ACCOUNT_HINT,
              partial(module_results.search_term_candidates, rest)),
        _tool("bid_suggestions",
              "El Bid Optimizer de una cuenta de Amazon Ads, con las mismas reglas del módulo: el bid sugerido de "
              "cada ASIN (CVR × precio × target ACoS) y su semáforo por CVR, con el precio promedio de venta del "
              "período, de mayor a menor gasto. target_acos reemplaza el guardado de la cuenta. compare_previous "
              "agrega a cada ASIN sus cifras del tramo anterior del mismo largo (*_previo, también el precio y el bid "
              "sugerido) y si subieron o bajaron (*_vs_previo): el bid se explica por cuál de CVR, precio o target "
              "cambió." + ACCOUNT_HINT,
              partial(module_results.bid_suggestions, rest)),
        _tool("asin_health",
              "PPC Insights de una cuenta de Amazon Ads, con las mismas reglas del módulo: el health score (0-100) de "
              "cada ASIN con sus partes, su gasto, ACoS, CVR, lo que gastaron todos sus términos sin órdenes "
              "(spend_without_sales) y la parte de sus 10 términos sin órdenes más caros (top_unsold_terms_spend), de "
              "mayor a menor gasto. Cada ASIN dice de dónde salió la mayor parte de su gasto (attributed_by: de ad "
              "groups de ese solo ASIN o del ASIN en el nombre de la campaña) y en cuántas campañas tiene un anuncio "
              "propio (advertised_in), y totals lo que no se pudo atribuir a ningún ASIN. Sin el SQP, el Business "
              "Report ni el Campaign CSV, que se suben a mano en el módulo: esas partes del score valen su punto "
              "neutro. target_acos reemplaza el guardado de la cuenta." + ACCOUNT_HINT,
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
