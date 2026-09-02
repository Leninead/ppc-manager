"""The drift detector must reject every semantic change, not just a missing formula.

The Launch Score is a replica of DataDive's client-side computation, so the only
thing standing between a silent recalibration and wrong numbers in the app is this
pattern. These cases mutate the real expression one edit at a time and assert the
detector notices — including the mutation that matters most and that the previous
two-pattern check could not see: returning 0 below the gate instead of undefined.
"""
from __future__ import annotations

import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_launch_score_drift.py"

_spec = importlib.util.spec_from_file_location("check_launch_score_drift", SCRIPT)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)

# Verbatim from https://2.datadive.tools, chunk 354-5e194255c12847f5.js (2026-09-02).
REAL = (
    'columnLaunchScore:(e=>{if("number"==typeof e.relevancy&&!(e.relevancy<.4))'
    "return e.searchVolume&&e.relevancy?"
    "Math.round(e.searchVolume*(1/e.relevancy)*.003):void 0})(e),"
)


def test_matches_the_real_bundle_expression():
    assert drift._EXPR.search(REAL)


def test_tolerates_a_renamed_minifier_variable():
    assert drift._EXPR.search(REAL.replace("e.", "t.").replace("(e=>", "(t=>"))


def test_rejects_returning_zero_below_the_gate():
    """The mutation the old check was blind to: `void 0` -> `0` would turn every
    below-gate keyword into "cheapest to rank" instead of an empty cell."""
    assert not drift._EXPR.search(REAL.replace(":void 0}", ":0}"))


def test_rejects_a_moved_gate():
    assert not drift._EXPR.search(REAL.replace("<.4", "<.5"))


def test_rejects_a_recalibrated_constant():
    assert not drift._EXPR.search(REAL.replace("*.003", "*.004"))


def test_rejects_a_dropped_type_check():
    assert not drift._EXPR.search(REAL.replace('"number"==typeof e.relevancy&&', ""))


def test_rejects_an_inverted_gate():
    assert not drift._EXPR.search(REAL.replace("!(e.relevancy<.4)", "e.relevancy<.4"))


def test_official_field_probe_reads_the_spec_text():
    """When DataDive finally ships the field, the replica must stand down."""
    assert drift.official_field_exists.__doc__
