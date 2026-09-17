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
COPY --chown=mcp:mcp core/search_term_frame.py core/search_term_analysis.py core/date_labels.py core/
COPY --chown=mcp:mcp services/mcp_server/ services/mcp_server/

USER mcp

# Un worker: cada herramienta es una lectura corta y el estado vive en PostgREST, no acá.
CMD ["python", "-m", "services.mcp_server.server"]
