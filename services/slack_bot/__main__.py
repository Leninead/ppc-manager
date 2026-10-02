"""`python -m services.slack_bot`: runs the bot, or idles when its Slack or chat API tokens are not configured."""
from __future__ import annotations

import logging
import time

log = logging.getLogger("services.slack_bot")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from services.slack_bot.settings import BotSettings

    settings = BotSettings.from_env()
    if not settings.configured:
        # Same soft default as the workers: the service can be deployed before the Slack app exists.
        log.warning("SLACK_BOT_TOKEN, SLACK_APP_TOKEN or CHAT_API_TOKEN is not set: the Slack bot idles")
        while True:
            time.sleep(3600)
    from services.slack_bot import bot

    bot.run(settings)


if __name__ == "__main__":
    main()
