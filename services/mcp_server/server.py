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
from functools import partial

from core.integrations.store import _Rest
from services.mcp_server.tools import amazon_ads, analyses

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
              "Las cuentas de Amazon Ads sincronizadas, con país, moneda y hasta qué día tienen datos. "
              "Empezá por acá para saber qué profile_id usar en las demás herramientas.",
              partial(amazon_ads.list_accounts, rest)),
        _tool("list_analyses",
              "Índice de análisis de IA guardados: qué cuentas y qué módulos tienen uno, de qué período "
              "y de cuándo. Dice QUÉ hay, no qué dice. Pasá profile_id para una sola cuenta.",
              partial(analyses.list_analyses, rest)),
        _tool("get_analysis",
              "El último análisis guardado de una cuenta y un módulo: su síntesis y las filas que citó. "
              "Módulos posibles: " + ", ".join(analyses.MODULES) + ".",
              partial(analyses.get_analysis, rest)),
        _tool("top_search_terms",
              "Los search terms de mayor gasto de una cuenta de Amazon Ads en los últimos días. "
              "Devuelve una página; si hay más, lo dice y da el offset siguiente.",
              partial(amazon_ads.top_search_terms, rest)),
    ]


def _tool(name: str, description: str, fn) -> dict:
    # El SDK nombra el schema de argumentos con fn.__name__, y un partial no lo trae. Se lo damos
    # sin tocar __wrapped__: si lo pusiéramos, inspect.signature volvería a mostrar el `rest` ya
    # aplicado y el modelo vería un parámetro que no puede completar.
    if not hasattr(fn, "__name__"):
        fn.__name__ = name
    return {"name": name, "description": description, "fn": fn}


def run() -> int:
    """Arranca el servidor HTTP. Falla temprano y fuerte si falta configuración."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        token = required_token()
        rest = rest_from_env()
    except ConfigurationError as exc:
        log.error("mcp-server no puede arrancar: %s", exc)
        return 2

    from services.mcp_server.http_app import serve

    port = int(os.environ.get("MCP_PORT", DEFAULT_PORT))
    log.info("mcp-server escuchando en :%d con %d herramientas", port, len(build_tools(rest)))
    serve(tools=build_tools(rest), token=token, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
