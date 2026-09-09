# syntax=docker/dockerfile:1
# Receiver runs its own tiny image, not the full app one — no numpy/pyarrow,
# no streamlit, so builds fast and the attack surface stays small.
FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN groupadd --gid 10002 receiver \
 && useradd  --uid 10002 --gid 10002 --create-home --shell /usr/sbin/nologin receiver

WORKDIR /app

# Pinned to match the app: fastapi + uvicorn are stable on the same Python
# 3.11 track; cryptography version follows the app requirement to reuse the
# same seal function.
COPY services/integrations_receiver/requirements.txt ./requirements.receiver.txt
RUN pip install --no-cache-dir -r requirements.receiver.txt

# Only what the receiver actually needs — no data/, no notes/, no _design/.
COPY --chown=receiver:receiver core/__init__.py core/
COPY --chown=receiver:receiver core/integrations/ core/integrations/
COPY --chown=receiver:receiver services/integrations_receiver/ services/integrations_receiver/

USER receiver

# One worker on purpose: each write is a single roundtrip, and a horizontal
# scale-out would need a shared rate limiter that today doesn't exist.
CMD ["uvicorn", "services.integrations_receiver.app:app", \
     "--host", "0.0.0.0", "--port", "8600", "--workers", "1", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
