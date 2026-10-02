"""`python -m services.chat_api`: serves the chat to the Slack bot, or idles when its token is not configured."""
from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("services.chat_api")

DEFAULT_PORT = 8800


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    quiet_streamlit()
    token = os.environ.get("CHAT_API_TOKEN", "").strip()
    if not token:
        # Same soft default as the workers: deployable before the token exists, never open without it.
        log.warning("CHAT_API_TOKEN is not set: the chat API idles")
        while True:
            time.sleep(3600)
    from services.chat_api import server

    server.serve(token, int(os.environ.get("CHAT_API_PORT", "") or DEFAULT_PORT))


def quiet_streamlit() -> None:
    """The chat modules run outside a Streamlit app here, and each cache warns about it at import."""
    os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")
    import streamlit.logger

    streamlit.logger.set_log_level("error")


if __name__ == "__main__":
    main()
