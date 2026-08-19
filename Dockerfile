# syntax=docker/dockerfile:1
# numpy/pyarrow pins are load-bearing (Streamlit 1.43.2 segfaults on newer). Keep Python 3.11.
FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    AGENCY_OS_DATA_DIR=/app/data

# Fixed UID so a bind-mounted volume has predictable ownership on the host.
RUN groupadd --gid 10001 appuser \
 && useradd  --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

# Skeleton staged outside the volume; the entrypoint seeds it on boot (the volume shadows /app/data).
COPY --chown=appuser:appuser data/ /app/seed/

COPY --chown=appuser:appuser docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && mkdir -p /app/data && chown -R appuser:appuser /app/data

# No VOLUME on purpose: it would spawn an anonymous volume on a forgotten mount and lose data.

USER appuser
EXPOSE 8501

# stdlib healthcheck (slim has no curl/wget).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; b=urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4).read(); sys.exit(0 if b'ok' in b else 1)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
