"""`python -m services.slack_bot`: runs the bot, or idles when its Slack tokens are not configured."""
from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("services.slack_bot")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    quiet_streamlit()
    from services.slack_bot.settings import BotSettings

    settings = BotSettings.from_env()
    if not settings.configured:
        # Same soft default as the workers: the service can be deployed before the Slack app exists.
        log.warning("SLACK_BOT_TOKEN and SLACK_APP_TOKEN are not set: the Slack bot idles")
        while True:
            time.sleep(3600)
    from services.slack_bot import bot

    bot.run(settings)


def quiet_streamlit() -> None:
    """The chat modules run outside a Streamlit app here, and each cache warns about it at import."""
    os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")
    import streamlit.logger

    streamlit.logger.set_log_level("error")


if __name__ == "__main__":
    main()
