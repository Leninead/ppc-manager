# syntax=docker/dockerfile:1
# Imagen propia, como el receiver: sin streamlit ni el resto de la app, así el build es rápido
# y la superficie chica. Un servidor que expone datos de clientes no lleva nada de más.
FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN groupadd --gid 10003 mcp \
 && useradd  --uid 10003 --gid 10003 --create-home --shell /usr/sbin/nologin mcp

WORKDIR /app

COPY services/mcp_server/requirements.txt ./requirements.mcp.txt
RUN pip install --no-cache-dir -r requirements.mcp.txt

# Sólo la capa de lectura que las herramientas usan. Nada de modules/ (Streamlit), nada de data/.
COPY --chown=mcp:mcp core/__init__.py core/
COPY --chown=mcp:mcp core/integrations/ core/integrations/
COPY --chown=mcp:mcp core/amazon_ads/ core/amazon_ads/
COPY --chown=mcp:mcp core/ai_analysis/ core/ai_analysis/
COPY --chown=mcp:mcp core/date_labels.py core/
COPY --chown=mcp:mcp core/search_term/__init__.py core/search_term/frame.py core/search_term/analysis.py core/search_term/
# The rules the module tools run: the same files the pages import, never a copy of their logic.
COPY --chown=mcp:mcp core/search_term/candidates.py core/search_term/negatives.py core/search_term/
COPY --chown=mcp:mcp core/bulk/__init__.py core/bulk/keyword_text.py core/bulk/
COPY --chown=mcp:mcp core/funnel/__init__.py core/funnel/coverage.py core/funnel/
COPY --chown=mcp:mcp core/bid_optimizer/__init__.py core/bid_optimizer/bids.py core/bid_optimizer/
COPY --chown=mcp:mcp core/ppc_insights/__init__.py core/ppc_insights/asin_health.py core/ppc_insights/
COPY --chown=mcp:mcp services/mcp_server/ services/mcp_server/
# Sólo el nombre de las filas (N03 -> su término), no los agentes: row_annotation es Python puro.
COPY --chown=mcp:mcp ai/__init__.py ai/
COPY --chown=mcp:mcp ai/agents/__init__.py ai/agents/row_annotation.py ai/agents/

USER mcp

# Un worker: cada herramienta es una lectura corta y el estado vive en PostgREST, no acá.
CMD ["python", "-m", "services.mcp_server.server"]
