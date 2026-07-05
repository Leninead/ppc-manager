"""Tests del generador de HTML del case study (M32 Fase 3).

Herméticos, sin red: `render_case_study_html` es una función pura sobre un dict.
Se valida markup del bloque `.capybaras-cs`, escape de texto de usuario, la banda
de métricas condicional, labels ES y el render de steps.
"""

from __future__ import annotations

from core.case_study_html import render_case_study_html

# cs_result mínimo válido (mismo shape que produce el módulo).
CS_SAMPLE = {
    "en": {
        "headline": "10% CTR Lift",
        "subhead": "sub",
        "metrics": [{"value": "10%", "label": "CTR"}],
        "challenge": "challenge body en",
        "approach": "approach body en",
        "approach_steps": [{"title": "Audit", "text": "t"}],
        "results": "results body en",
    },
    "es": {
        "headline": "Aumento 10%",
        "subhead": "sub es",
        "metrics": [{"value": "10%", "label": "CTR"}],
        "challenge": "challenge body es",
        "approach": "approach body es",
        "approach_steps": [],
        "results": "results body es",
    },
    "meta": {"brand": "lenovo", "can_mention": True, "market": ""},
}


def test_returns_str_with_capybaras_cs():
    """El output es un str con el bloque .capybaras-cs y su <style> inline."""
    h = render_case_study_html(CS_SAMPLE, "en")
    assert isinstance(h, str)
    assert '<div class="capybaras-cs"' in h
    assert "<style>" in h


def test_renders_headline_and_body():
    """El headline y el results del idioma pedido aparecen en el HTML."""
    h = render_case_study_html(CS_SAMPLE, "en")
    assert "10% CTR Lift" in h
    assert "results body en" in h


def test_metricband_present_when_metrics():
    """Con métricas, se renderiza el <div class="metricband"> y el value '10%'."""
    h = render_case_study_html(CS_SAMPLE, "en")
    assert '<div class="metricband">' in h
    assert "10%" in h


def test_metricband_absent_when_empty():
    """Sin métricas, NO hay celda de métrica renderizada.

    Ojo: la palabra 'metricband' vive siempre en el CSS. Se asserta sobre el
    markup del body (el <div class="metric"> de una celda), que solo existe si
    hay métricas — no sobre la clase del CSS.
    """
    sample = {**CS_SAMPLE, "en": {**CS_SAMPLE["en"], "metrics": []}}
    h = render_case_study_html(sample, "en")
    assert '<div class="metric">' not in h
    assert '<div class="metricband">' not in h


def test_html_escapes_user_text():
    """Texto de usuario con '<script>' y '&' sale escapado (no rompe el HTML)."""
    sample = {**CS_SAMPLE, "en": {**CS_SAMPLE["en"], "headline": "A & B <script>"}}
    h = render_case_study_html(sample, "en")
    assert "&amp;" in h
    assert "&lt;script&gt;" in h
    assert "<script>" not in h


def test_es_labels():
    """Con lang='es' aparece un label español de sección."""
    h = render_case_study_html(CS_SAMPLE, "es")
    assert "Desafío" in h or "Resultados" in h


def test_steps_rendered():
    """Los approach_steps aparecen (el title 'Audit' está en el HTML)."""
    h = render_case_study_html(CS_SAMPLE, "en")
    assert "Audit" in h
