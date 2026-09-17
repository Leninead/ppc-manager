"""El transporte HTTP del servidor MCP: streamable HTTP, detrás de un Bearer.

La autenticación va como middleware y no como TokenVerifier del SDK a propósito: el chequeo es un
token de servicio, no un OAuth con scopes, y así la misma función que lo decide (server.authorize)
es la que está cubierta por tests, en vez de quedar enterrada en un hook del framework.

El SDK valida el header Host contra una lista blanca (protección anti DNS-rebinding). Está bien que
lo haga, así que no se apaga: la lista se declara por entorno, y un host que no esté recibe 421.
"""
from __future__ import annotations

import logging
import os

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from services.mcp_server.server import authorize

log = logging.getLogger(__name__)

SERVER_NAME = "ppc-manager"
MCP_PATH = "/mcp"
HEALTH_PATH = "/health"
ALLOWED_HOSTS_ENV = "MCP_ALLOWED_HOSTS"
# Con qué host se le habla al servidor cuando nadie lo configuró: el contenedor y la loopback.
DEFAULT_ALLOWED_HOSTS = ("mcp-server", "mcp-server:8790", "localhost", "localhost:8790",
                         "127.0.0.1", "127.0.0.1:8790")

INSTRUCTIONS = (
    "Datos de la agencia Capybaras sobre cuentas de Amazon Ads: qué cuentas hay, qué análisis de IA "
    "tienen guardados y sus search terms.\n\n"
    "Empezá por list_accounts para saber qué profile_id existe. Para hablar de una cuenta, mirá "
    "list_analyses (el índice de qué hay) y recién después get_analysis del módulo que te interese: "
    "no hace falta bajar todo.\n\n"
    "Las respuestas vienen paginadas. Cuando una trae el campo `note` diciendo que hay más filas, "
    "hay más: pedí la página siguiente con el offset que te indica o acotá la consulta. Nunca "
    "respondas como si la página que ves fueran todos los datos.\n\n"
    "Todo es de sólo lectura: acá no se modifica ninguna campaña ni ningún bid."
)


def allowed_hosts() -> list[str]:
    """Los Host que el servidor acepta. Coma-separados en el entorno, o el default de contenedor."""
    configured = [host.strip() for host in os.environ.get(ALLOWED_HOSTS_ENV, "").split(",") if host.strip()]
    return configured or list(DEFAULT_ALLOWED_HOSTS)


def build_server(tools: list) -> MCPServer:
    server = MCPServer(name=SERVER_NAME, instructions=INSTRUCTIONS)
    for tool in tools:
        server.add_tool(tool["fn"], name=tool["name"], description=tool["description"])

    @server.custom_route(HEALTH_PATH, methods=["GET"])
    async def health(_request):
        return JSONResponse({"service": SERVER_NAME, "tools": [tool["name"] for tool in tools]})

    return server


class BearerMiddleware(BaseHTTPMiddleware):
    """Todo pasa por el token menos /health, que existe para que Docker sepa si el proceso vive."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token

    async def dispatch(self, request, call_next):
        if request.url.path == HEALTH_PATH:
            return await call_next(request)
        if not authorize(request.headers.get("authorization"), self._token):
            # Sin detalle: a quien no tiene el token no se le explica qué le faltó.
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def build_app(tools: list, token: str, *, hosts: list[str] | None = None):
    """La app ASGI: /mcp autenticado y /health abierto, en una sola app y sin redirecciones."""
    security = TransportSecuritySettings(allowed_hosts=hosts or allowed_hosts())
    app = build_server(tools).streamable_http_app(streamable_http_path=MCP_PATH, stateless_http=True,
                                                 transport_security=security)
    app.add_middleware(BearerMiddleware, token=token)
    return app


def serve(*, tools: list, token: str, port: int, host: str = "0.0.0.0") -> None:
    import uvicorn

    hosts = allowed_hosts()
    log.info("mcp-server acepta Host: %s", ", ".join(hosts))
    uvicorn.run(build_app(tools, token, hosts=hosts), host=host, port=port, log_level="info")
