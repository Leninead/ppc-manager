"""Paquete `core` — intencionalmente SIN imports de conveniencia.

NO reexportar nada acá. Este `__init__` corre en CUALQUIER `from core.X import Y`
(ej. `from core.constants import _PAGES` en app.py), asi que todo lo que se importe
en este archivo se carga en el boot de la app, para todos los modulos.

Historico: hasta 2026-08-10 este archivo hacia
    from core.ai_analyze import _claude_analyze, _build_sqp_prompt, _build_str_prompt
lo que arrastraba `anthropic` (+httpx +cryptography) = ~22.6 MB de RSS en cada arranque,
aun cuando ningun modulo usara la API. Medido empiricamente contra el techo de 1 GB de
Streamlit Cloud. Los 4 consumidores reales ya importan lazy dentro de sus funciones:
search_term_report.py, search_query_performance.py, weekly_client_report.py, ppc_insights.py.
"""
