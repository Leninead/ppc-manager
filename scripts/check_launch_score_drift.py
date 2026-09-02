"""Is DataDive's Launch Score replica still valid?

The Launch Score is absent from the v1 API, so core/datadive.py replicates the
formula from DataDive's frontend. A replica breaks silently when the original
changes, and this detects that WITHOUT credentials — both the frontend bundle
and the OpenAPI spec are public — which is why CI runs it (see the
"Launch Score drift" stage of the Jenkinsfile: every build plus a weekly cron).

Exit codes:
  0 = the formula still holds and the official field does not exist yet.
  1 = something changed and needs action (details are printed).
  2 = nothing could be verified (no network); it asserts nothing.
"""
import re
import sys

import requests

SPEC_URL = "https://developer.datadive.tools/docs-json"
APP_URL = "https://2.datadive.tools"
TIMEOUT = 30

# The formula as it lives in the minified bundle, plus its threshold.
_FORMULA = re.compile(r"searchVolume\s*\*\s*\(1\s*/\s*\w+\.relevancy\)\s*\*\s*\.003")
_GATE = re.compile(r"relevancy\s*<\s*\.4")


def official_field_exists() -> bool | None:
    """True once `launchScore` is in the official spec, which means migrate."""
    try:
        spec = requests.get(SPEC_URL, timeout=TIMEOUT).text
    except Exception as e:
        print(f"  spec oficial no verificable: {e}")
        return None
    return "launchScore" in spec or "launch_score" in spec


def formula_still_in_bundle() -> tuple[bool | None, str]:
    """True while the replicated formula is still in the public frontend bundle."""
    try:
        html = requests.get(APP_URL, timeout=TIMEOUT).text
        chunks = set(re.findall(r'src="(/_next/static/[^"]+\.js[^"]*)"', html))
        build = re.search(r'"buildId":"([^"]+)"', html)
        if build:
            manifest = requests.get(
                f"{APP_URL}/_next/static/{build.group(1)}/_buildManifest.js",
                timeout=TIMEOUT).text
            chunks.update("/_next/" + p
                          for p in re.findall(r'"(static/[^"]+\.js)"', manifest))
        for path in sorted(chunks):
            js = requests.get(APP_URL + path, timeout=TIMEOUT).text
            if _FORMULA.search(js) and _GATE.search(js):
                return True, path.rsplit("/", 1)[-1]
        return False, ""
    except Exception as e:
        print(f"  bundle no verificable: {e}")
        return None, ""


def main() -> int:
    print("== drift check del Launch Score de DataDive ==")
    unverifiable = False

    official = official_field_exists()
    if official is None:
        unverifiable = True
    elif official:
        print("  ACCION: 'launchScore' YA EXISTE en el spec oficial.\n"
              "  core/datadive.py::_launch_score_of lo prefiere automáticamente,\n"
              "  así que la app ya usa el valor oficial: se puede borrar la réplica.")
        return 1
    else:
        print("  spec oficial: sin launchScore (la réplica sigue siendo la única vía)")

    vigente, chunk = formula_still_in_bundle()
    if vigente is None:
        unverifiable = True
    elif vigente:
        print(f"  fórmula vigente en el bundle ({chunk}): "
              "SV × (1/relevancy) × 0.003 con gate relevancy ≥ 0.4")
    else:
        print("  ACCION: la fórmula NO está en el bundle público — DataDive pudo\n"
              "  recalibrarla. Los Launch Score del modo API pueden estar mal:\n"
              "  recalibrar contra un export real (ver M21 en modules/pages/CLAUDE.md).")
        return 1

    if unverifiable:
        print("  sin red: no se verificó nada, no se afirma nada.")
        return 2
    print("  OK: nada que hacer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
