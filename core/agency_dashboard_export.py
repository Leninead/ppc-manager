"""Export HTML del Dashboard Global de Agencia (M39 · B3b).

Capa PURA: recibe el dict que devuelve `core.agency_dashboard._build_agency_dashboard`
y devuelve un string. No toca Streamlit, no lee disco y no llama a `date.today()`
adentro — la fecha entra por parámetro, para que la misma entrada dé el mismo
documento byte a byte.

Diferencias deliberadas con el export de M31 (`revenue_forecast._build_export_html`),
del que se copia la ESTRUCTURA (doctype + head + style + body, `_tbl`, `html.escape`
en cada celda) y no el archivo:

- **Standalone de verdad.** M31 trae Google Fonts por `<link>` y la librería de
  charts por CDN: sin internet se ve roto. Este documento no tiene ni un `<link>`,
  ni una URL, ni una línea de JS. Se manda por mail y se abre con doble clic.
- **Tema claro.** M31 es oscuro; acá el semáforo es pastel y necesita fondo
  blanco para leerse. Mismos colores que la pantalla.
- **Apilado con índice de anclas**, sin pestañas: el reporte se lee de corrido y
  se le sacan capturas, y una pestaña oculta es contenido que nadie captura.

El semáforo y el formato de celda se IMPORTAN de `core.agency_dashboard_format`
— los mismos que usa la pantalla. Duplicarlos acá haría que el PDF que ve
Dirección pudiera pintar una celda distinto que la app.
"""
from __future__ import annotations

import html
import re
from datetime import date
from typing import Optional

from core.agency_dashboard_format import (
    _METRICS,
    _acco_color,
    _account_df,
)

_NARANJA = "#E84000"
_NEGRO = "#1F1F1F"

# Sin `@font-face` ni `<link>`: stack del sistema. El documento tiene que verse
# igual sin conexión.
_CSS = """
*{box-sizing:border-box;}
body{
  margin:0; background:#FFFFFF; color:#1F1F1F;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  font-size:14px; line-height:1.55;
}
.wrap{max-width:1180px; margin:0 auto; padding:0 28px 56px;}
header.top{background:#E84000; color:#FFFFFF; padding:26px 28px;}
header.top .inner{max-width:1180px; margin:0 auto;}
header.top .brand{
  font-size:0.72rem; letter-spacing:0.16em; text-transform:uppercase;
  opacity:0.85; margin-bottom:6px;
}
header.top h1{margin:0; font-size:1.6rem; letter-spacing:-0.01em;}
header.top .meta{margin-top:8px; font-size:0.84rem; opacity:0.92;}
nav.indice{
  border:1px solid #E5E5E5; border-left:3px solid #E84000; border-radius:8px;
  padding:16px 20px; margin:28px 0 8px; background:#FAFAFA;
}
nav.indice h2{margin:0 0 10px; font-size:0.78rem; letter-spacing:0.1em;
  text-transform:uppercase; color:#6B7280;}
nav.indice ul{margin:0; padding-left:18px;}
nav.indice li{margin:3px 0;}
nav.indice a{color:#1F1F1F; text-decoration:none; border-bottom:1px solid #E5E5E5;}
nav.indice a:hover{border-bottom-color:#E84000;}
section.cuenta{margin-top:36px; page-break-inside:avoid;}
section.cuenta h2{margin:0; font-size:1.15rem;}
section.cuenta .plan{color:#6B7280; font-size:0.8rem; margin:4px 0 12px;}
.badge{
  display:inline-block; font-size:0.72rem; font-weight:700; color:#B26A00;
  background:#FFF8E1; border:1px solid #F0E0B0; border-radius:999px;
  padding:2px 10px;
}
table{width:100%; border-collapse:collapse; font-size:0.8rem;
  font-variant-numeric:tabular-nums;}
thead th{
  color:#6B7280; font-weight:600; font-size:0.68rem; text-transform:uppercase;
  letter-spacing:0.06em; text-align:right; padding:8px 10px;
  border-bottom:1px solid #D8D8D8; white-space:nowrap;
}
thead th:first-child{text-align:left;}
tbody td{padding:7px 10px; text-align:right; border-bottom:1px solid #EFEFEF;}
tbody td:first-child{text-align:left; font-weight:600; color:#1F1F1F;}
tbody tr:last-child td{border-bottom:none;}
p.nota{color:#6B7280; font-size:0.78rem; margin-top:10px;}
p.vacio{
  border:2px dashed #FFD9B3; border-radius:12px; background:#FFF8F0;
  padding:28px; text-align:center; color:#6B7280;
}
footer{
  border-top:1px solid #E5E5E5; margin-top:48px; padding-top:18px;
  color:#9CA3AF; font-size:0.74rem;
}
"""

_NOTA_MTD = (
    "* Mes en curso (MtD): el real cubre solo los días transcurridos y se "
    "compara contra un plan de mes completo, así que el cumplimiento se lee "
    "bajo. No se prorratea a propósito."
)
_SIN_PLAN = "⚠ sin plan cargado"


def _slug(account: dict, i: int) -> str:
    """Ancla estable y segura para el `id` / `href` de una cuenta.

    Sale del `client_id` (que ya es un slug de disco), saneado a [a-z0-9-]. Si
    quedara vacío, cae al índice: el ancla nunca puede quedar vacía porque el
    índice dejaría de saltar.
    """
    base = re.sub(r"[^a-z0-9-]+", "-", str(account.get("client_id") or "").lower())
    base = base.strip("-")
    return f"cuenta-{base or i}"


def _tabla_html(account: dict, periods: list[str]) -> tuple[str, bool]:
    """Tabla de una cuenta + si tiene algún mes en curso.

    Las celdas de texto salen de `_account_df` (el MISMO DataFrame que dibuja la
    pantalla, ya formateado y sin None). El color se resuelve aparte, contra el
    valor crudo del cumplimiento: el del df ya es string y no sirve para comparar.
    """
    df, hay_parcial = _account_df(account, periods)
    months = account.get("months") or {}
    # Las columnas vienen de a pares (Actual, Acco) en el orden de `periods`.
    acco_cols = [c for c in df.columns if c.endswith(" Acco")]
    col_period = dict(zip(acco_cols, periods))

    out = ["<table><thead><tr><th>Métrica</th>"]
    out += [f"<th>{html.escape(str(c))}</th>" for c in df.columns]
    out.append("</tr></thead><tbody>")

    for metric_id, label in _METRICS:
        out.append(f"<tr><td>{html.escape(label)}</td>")
        for col in df.columns:
            texto = html.escape(str(df.loc[label, col]))
            period = col_period.get(col)
            color = ""
            if period is not None:
                acco = (months.get(period) or {}).get("accomplishment") or {}
                color = _acco_color(metric_id, acco.get(metric_id))
            style = f' style="background-color: {color};"' if color else ""
            out.append(f"<td{style}>{texto}</td>")
        out.append("</tr>")

    out.append("</tbody></table>")
    return "".join(out), hay_parcial


def _seccion_cuenta(account: dict, periods: list[str], slug: str) -> tuple[str, bool]:
    """Bloque de una cuenta: nombre, plan (o badge) y su tabla."""
    nombre = html.escape(str(account.get("name") or account.get("client_id") or "—"))
    tabla, hay_parcial = _tabla_html(account, periods)

    if account.get("has_baseline"):
        plan = (
            f'<p class="plan">⭐ Plan: '
            f'{html.escape(str(account.get("baseline_name") or "—"))} · '
            f'{html.escape(str(account.get("baseline_created_at") or "—"))}</p>'
        )
    else:
        plan = f'<p class="plan"><span class="badge">{_SIN_PLAN}</span></p>'

    return (
        f'<section class="cuenta" id="{slug}">\n'
        f"<h2>{nombre}</h2>\n{plan}\n{tabla}\n</section>",
        hay_parcial,
    )


def _build_agency_html(data: dict, generated_at: Optional[date] = None) -> str:
    """Documento HTML standalone del Dashboard Global.

    Args:
        data: lo que devuelve `_build_agency_dashboard` — el MISMO dict que
            consume la pantalla. Las cuentas se emiten en el orden en que vienen
            (el agregador ya las ordenó): el export no reordena nada.
        generated_at: fecha de generación para el header. Parámetro y no
            `date.today()` adentro, para que la función sea determinística;
            None sólo como comodidad del caller.

    Returns:
        String HTML completo (doctype + head + style embebido + body), sin JS,
        sin `<link>` y sin ninguna URL: se abre con doble clic y se manda por
        mail.
    """
    if generated_at is None:
        generated_at = date.today()
    gen = generated_at.isoformat()

    periods = list(data.get("periods") or [])
    accounts = list(data.get("accounts") or [])

    rango = f"{periods[0]} → {periods[-1]}" if periods else "sin meses"
    titulo = "Dashboard Global de Agencia"

    cuerpo: list[str] = []
    if not accounts:
        cuerpo.append(
            '<p class="vacio"><strong>Sin cuentas para mostrar.</strong><br>'
            "Ninguna cuenta tiene forecast cargado para esta ventana.</p>"
        )
        algun_parcial = False
    else:
        slugs = [_slug(a, i) for i, a in enumerate(accounts)]
        indice = ['<nav class="indice"><h2>Cuentas</h2><ul>']
        for account, slug in zip(accounts, slugs):
            marca = "" if account.get("has_baseline") else f" — {_SIN_PLAN}"
            nombre = html.escape(str(account.get("name")
                                     or account.get("client_id") or "—"))
            indice.append(f'<li><a href="#{slug}">{nombre}</a>{marca}</li>')
        indice.append("</ul></nav>")
        cuerpo.append("".join(indice))

        algun_parcial = False
        for account, slug in zip(accounts, slugs):
            seccion, hay_parcial = _seccion_cuenta(account, periods, slug)
            algun_parcial = algun_parcial or hay_parcial
            cuerpo.append(seccion)

    if algun_parcial:
        cuerpo.append(f'<p class="nota">{html.escape(_NOTA_MTD)}</p>')

    cuerpo.append(
        f'<footer>Capybaras Agency — {html.escape(gen)}</footer>'
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(titulo)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        '<header class="top"><div class="inner">'
        '<div class="brand">Capybaras Agency</div>'
        f"<h1>{html.escape(titulo)}</h1>"
        f'<div class="meta">Meses: {html.escape(rango)} · '
        f"{len(accounts)} cuenta{'s' if len(accounts) != 1 else ''} · "
        f"Generado: {html.escape(gen)}</div>"
        "</div></header>\n"
        f'<div class="wrap">\n{chr(10).join(cuerpo)}\n</div>\n'
        "</body>\n</html>\n"
    )
