"""The MCP server's own image carries only part of the repo: what the server imports has to be in it."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "services" / "mcp_server" / "Dockerfile"


def _copied_modules() -> list[str]:
    """The first-party modules the Dockerfile COPYs, as dotted names."""
    modules = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("COPY ") or "requirements" in line:
            continue
        sources = [part for part in line.split()[1:-1] if not part.startswith("--")]
        for source in sources:
            name = re.sub(r"(/__init__)?\.py$", "", source.rstrip("/")).replace("/", ".")
            modules.append(name)
    return modules


_PROBE = """
import importlib.abc, sys
COPIED = {copied!r}

class OutsideTheImage(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        top = name.split(".")[0]
        if top in ("modules", "streamlit"):
            raise ImportError("not in the MCP image: " + name)
        if top in ("ai", "core", "services") and name not in ("ai", "core", "services") and not any(
                name == module or name.startswith(module + ".") for module in COPIED):
            raise ImportError("not in the MCP image: " + name)
        return None

sys.meta_path.insert(0, OutsideTheImage())
from services.mcp_server import http_app, server
http_app.build_server(server.build_tools(object()))
print("ok")
"""


def test_the_dockerfile_copies_the_read_layer_the_tools_use():
    assert {"core.amazon_ads", "core.ai_analysis", "services.mcp_server"} <= set(_copied_modules())


def test_the_image_carries_how_rows_are_named_but_not_the_agents():
    copied = set(_copied_modules())

    assert {"ai", "ai.agents", "ai.agents.row_annotation"} <= copied
    assert not any(module.startswith(("ai.agents.str", "ai.agents.bid_optimizer", "ai.runtime", "ai.client"))
                   for module in copied)


def test_the_server_starts_with_only_what_its_image_carries():
    """A tool that reaches for the chat machinery or Streamlit breaks the container, not a unit test."""
    done = subprocess.run([sys.executable, "-c", _PROBE.format(copied=_copied_modules())],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)

    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().endswith("ok")
