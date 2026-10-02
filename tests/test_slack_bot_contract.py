"""What the Slack bot takes from ppc-manager: the app's components, drawn in Slack, and nothing more.

The bot asks the chat API and holds neither the database key nor the provider secret; the last test fails the day
an import drags either side of that line into the bot's process.
"""
import json
import subprocess
import sys
from pathlib import Path

from core.chat import components
from services.slack_bot import charts, to_slack

# The kinds to_slack converts itself; a new component lands in neither set and fails here first.
SLACK_NATIVE_KINDS = {"text", "kpis", "table", "alert", "action"}

# Modules that read the database, call the provider or need the app's Streamlit session.
CHAT_SIDE_PACKAGES = {"ai", "streamlit", "pandas", "supabase", "postgrest"}
CHAT_SIDE_MODULES = ("core.integrations", "core.persistence", "core.chat.panel", "core.chat.turns",
                     "core.chat.account_directory", "core.chat.ads_scope", "core.chat.app_chat", "services.chat_api")
REPO = Path(__file__).resolve().parents[1]


def test_every_component_of_the_catalog_has_a_slack_rendering():
    assert {component.kind for component in components.CATALOG} == SLACK_NATIVE_KINDS | charts.KINDS


def test_the_rendering_offers_one_converter_per_native_kind():
    for component in components.CATALOG:
        if component.kind in charts.KINDS:
            continue
        converted, _ = to_slack._blocks(components.normalize({"blocks": [component.example]})[0])
        assert converted, component.kind


def test_the_bot_loads_nothing_that_reaches_the_database_or_the_provider():
    script = ("import json, sys\n"
              "import services.slack_bot.__main__, services.slack_bot.bot\n"
              "print(json.dumps(sorted(sys.modules)))")
    loaded = json.loads(subprocess.run([sys.executable, "-c", script], cwd=REPO, capture_output=True, text=True,
                                       check=True).stdout)
    crossed = [name for name in loaded
               if name.split(".")[0] in CHAT_SIDE_PACKAGES or name.startswith(CHAT_SIDE_MODULES)]
    assert crossed == []
