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
from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.agency_dashboard_format import (
    _LEYENDA_ACCO,
    _METRICS,
    _PCT_METRICS,
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

    cuerpo.append(f'<p class="nota">{html.escape(_LEYENDA_ACCO)}</p>')

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


# ─────────────────────────────────────────────────────────────────────────────
# Export XLSX — layout del mockup de Dirección, branding Capybaras
# ─────────────────────────────────────────────────────────────────────────────
#
# Convenciones de `.claude/skills/ppc-reporting-standard.md`: portada con fila
# naranja + fila negra, headers de tabla en negro con texto blanco, y `_autofit`
# (min 8 / max 40) al final. La función vive FUERA de cualquier `render()` — es
# la regla arquitectónica del estándar, que evita el "At least one sheet must be
# visible" de openpyxl bajo el runtime de Streamlit.

_XL_NARANJA = "E84000"
_XL_NEGRO = "1F1F1F"
_XL_BLANCO = "FFFFFF"
_XL_GRIS = "6B7280"
_XL_BANDA = "FFF3E0"      # naranja pálido del estándar, para la banda de cuenta

_FILL_NARANJA = PatternFill("solid", start_color=_XL_NARANJA, end_color=_XL_NARANJA)
_FILL_NEGRO = PatternFill("solid", start_color=_XL_NEGRO, end_color=_XL_NEGRO)
_FILL_BANDA = PatternFill("solid", start_color=_XL_BANDA, end_color=_XL_BANDA)


def _fill(color_hex: str) -> PatternFill:
    """PatternFill sólido a partir de un color '#RRGGBB' del módulo de formato."""
    rgb = color_hex.lstrip("#").upper()
    return PatternFill("solid", start_color=rgb, end_color=rgb)


def _autofit(ws, min_w: int = 8, max_w: int = 40) -> None:
    """Ancho de columna al contenido, acotado (estándar: min 8, max 40)."""
    anchos: dict[int, int] = {}
    for row in ws.iter_rows():
        for celda in row:
            if celda.value is None:
                continue
            largo = max(len(linea) for linea in str(celda.value).split("\n"))
            anchos[celda.column] = max(anchos.get(celda.column, 0), largo)
    for col, largo in anchos.items():
        ws.column_dimensions[get_column_letter(col)].width = min(
            max(largo + 2, min_w), max_w
        )


# Formatos de celda del XLSX. La planilla es OPERABLE: cada celda lleva el
# número crudo y Excel se encarga de mostrarlo. Lo que el usuario ve es el
# mismo dato que ve en pantalla, pero se puede sumar, promediar y graficar.
_FMT_PCT = "0.0%"            # sobre fracción (0.95 → 95,0%), como manda el estándar
_FMT_RATIO = '0.0"%"'        # ACOS / TACOS reales: son puntos, no fracción
_FMT_DELTA = "+0.0;-0.0"     # desvío contra el plan, con signo siempre visible


def _valor_actual(metric_id: str, crudo, currency: str) -> tuple:
    """(valor, number_format) de una celda Actual. Sin dato → (None, '')."""
    if crudo is None:
        return None, ""
    if metric_id in _PCT_METRICS:
        return float(crudo), f'"{currency}" #,##0'
    return float(crudo), _FMT_RATIO


def _valor_acco(metric_id: str, crudo) -> tuple:
    """(valor, number_format) de una celda Acco. Sin dato → (None, '').

    Revenue / Ad Sales / Ad Spend: el cumplimiento llega en escala 0-100 (95.0)
    y se escribe como FRACCIÓN (0.95) con formato de porcentaje. Es lo que
    manda el estándar de planillas —"percentages stored as fractions"— y lo que
    hace que Excel lo trate como un porcentaje de verdad: se puede promediar
    entre cuentas sin que el promedio quede 100 veces más grande.
    ACOS / TACOS: el desvío en puntos se escribe tal cual (3.0), con formato de
    signo. NO es una fracción: son puntos porcentuales de diferencia.
    """
    if crudo is None:
        return None, ""
    if metric_id in _PCT_METRICS:
        return float(crudo) / 100.0, _FMT_PCT
    return float(crudo), _FMT_DELTA


def _tabla_excel(ws, account: dict, periods: list, fila: int) -> tuple:
    """Escribe la tabla de UNA cuenta a partir de `fila`.

    Returns:
        (siguiente fila libre, si la cuenta tiene algún mes en curso).
    """
    df, hay_parcial = _account_df(account, periods)
    months = account.get("months") or {}
    currency = str(account.get("currency") or "USD")
    # `_account_df` se usa SOLO por sus etiquetas de columna ("Ago Actual",
    # "Sep* Acco"): sus celdas son strings ya formateados y acá van números.
    acco_cols = [c for c in df.columns if c.endswith(" Acco")]
    col_period = dict(zip(acco_cols, periods))
    # Cada mes ocupa dos columnas contiguas; la de Actual es la anterior a su Acco.
    for col_acco, period in list(col_period.items()):
        idx = list(df.columns).index(col_acco)
        col_period[df.columns[idx - 1]] = period
    n_cols = 1 + len(df.columns)

    # ── Banda con el nombre de la cuenta + su plan ──
    nombre = str(account.get("name") or account.get("client_id") or "—")
    if account.get("has_baseline"):
        detalle = (f"Plan: {account.get('baseline_name')} "
                   f"({account.get('baseline_created_at')})")
    else:
        detalle = "⚠ sin plan cargado"
    ws.cell(row=fila, column=1, value=nombre).font = Font(
        bold=True, size=12, color=_XL_NEGRO,
    )
    ws.cell(row=fila, column=2, value=detalle).font = Font(size=9, color=_XL_GRIS)
    for col in range(1, n_cols + 1):
        ws.cell(row=fila, column=col).fill = _FILL_BANDA
    ws.row_dimensions[fila].height = 20
    fila += 1

    # ── Header de la tabla (negro, texto blanco) ──
    encabezados = ["Métrica"] + [str(c) for c in df.columns]
    for col, texto in enumerate(encabezados, start=1):
        celda = ws.cell(row=fila, column=col, value=texto)
        celda.fill = _FILL_NEGRO
        celda.font = Font(bold=True, color=_XL_BLANCO, size=10)
        celda.alignment = Alignment(
            horizontal="left" if col == 1 else "center", vertical="center",
        )
    ws.row_dimensions[fila].height = 20
    fila += 1

    # ── Las 5 métricas, con VALORES NUMÉRICOS ──
    for metric_id, label in _METRICS:
        ws.cell(row=fila, column=1, value=label).font = Font(bold=True, size=10)
        for j, col_name in enumerate(df.columns, start=2):
            celda = ws.cell(row=fila, column=j)
            celda.alignment = Alignment(horizontal="right")
            period = col_period.get(col_name)
            if period is None:
                continue
            cell_data = months.get(period) or {}
            es_acco = col_name.endswith(" Acco")

            if es_acco:
                crudo = (cell_data.get("accomplishment") or {}).get(metric_id)
                valor, fmt_num = _valor_acco(metric_id, crudo)
                # El semáforo va SOLO en las métricas de % (ver el docstring de
                # `_build_agency_excel`). Sacar `and metric_id in _PCT_METRICS`
                # devuelve el color a ACOS / TACOS.
                if metric_id in _PCT_METRICS:
                    color = _acco_color(metric_id, crudo)
                    if color:
                        celda.fill = _fill(color)
            else:
                crudo = (cell_data.get("actual") or {}).get(metric_id)
                valor, fmt_num = _valor_actual(metric_id, crudo, currency)

            # Sin dato → celda VACÍA, nunca 0: un cero se sumaría y ensuciaría
            # los totales de quien usa la planilla.
            if valor is None:
                continue
            celda.value = valor
            celda.number_format = fmt_num
        fila += 1

    return fila, hay_parcial


def _build_agency_excel(data: dict, generated_at: Optional[date] = None) -> bytes:
    """Workbook XLSX del Dashboard Global, con el layout del mockup de Dirección.

    Una tabla por cuenta, apiladas: banda con el nombre, fila de meses (cada uno
    ocupa dos columnas, Actual y Acco) y las 5 métricas. Los VALORES salen de
    `_account_df` — los mismos strings que la pantalla y el export HTML, para
    que los tres no puedan divergir.

    SEMÁFORO SOLO EN LAS MÉTRICAS DE %: Revenue / Ad Sales / Ad Spend se pintan
    con `_acco_color`; ACOS y TACOS van SIN relleno, solo el número con signo.
    Es una desviación consciente de `ppc-reporting-standard.md` L129 ("nunca
    mostrar ACoS sin semáforo"), que habla del ACoS ABSOLUTO —donde el color
    orienta sobre si 22% o 76% está bien—. Acá la celda Acco no es un ACoS: es
    un DELTA EN PUNTOS contra el plan, y el signo ya dice de qué lado estás. El
    mockup de Dirección las muestra sin fondo.
    Para revertirlo cuando Dirección confirme, alcanza con sacar
    `and metric_id in _PCT_METRICS` en `_tabla_excel`: la regla vive en UNA
    línea, a propósito.

    Args:
        data: lo que devuelve `_build_agency_dashboard` — el mismo dict que
            consume la pantalla. No se reordena nada.
        generated_at: fecha para la portada. Parámetro y no `date.today()`
            adentro, para que la función sea determinística.

    Returns:
        Bytes del .xlsx. No escribe a disco.

    Nota: los BYTES no son reproducibles entre corridas aunque la entrada sea la
    misma — openpyxl estampa `dcterms:created` / `dcterms:modified` en
    `docProps/core.xml` (medido). Lo determinístico es el CONTENIDO (celdas y
    colores), que es lo que verifican los tests.
    """
    if generated_at is None:
        generated_at = date.today()
    gen = generated_at.isoformat()

    periods = list(data.get("periods") or [])
    accounts = list(data.get("accounts") or [])
    n_cols = max(1 + 2 * len(periods), 6)

    wb = Workbook()
    ws = wb.active
    ws.title = "Dashboard general"

    # ── Portada (estándar: fila naranja + fila negra + separador) ──
    ws.cell(row=1, column=1, value="Dashboard Global de Agencia")
    ws.cell(row=2, column=1, value=f"Capybaras Agency — {gen}")
    for fila_p, relleno, tam in ((1, _FILL_NARANJA, 14), (2, _FILL_NEGRO, 11)):
        ws.merge_cells(
            start_row=fila_p, start_column=1, end_row=fila_p, end_column=n_cols,
        )
        for col in range(1, n_cols + 1):
            celda = ws.cell(row=fila_p, column=col)
            celda.fill = relleno
            celda.font = Font(bold=(fila_p == 1), color=_XL_BLANCO, size=tam)
        ws.row_dimensions[fila_p].height = 22

    rango = f"{periods[0]} → {periods[-1]}" if periods else "sin meses"
    plural = "s" if len(accounts) != 1 else ""
    ws.cell(
        row=3, column=1,
        value=f"Meses: {rango} · {len(accounts)} cuenta{plural}",
    ).font = Font(color=_XL_GRIS, size=10)

    fila = 5
    algun_parcial = False

    if not accounts:
        ws.cell(
            row=fila, column=1,
            value=("Sin cuentas para mostrar: ninguna tiene forecast cargado "
                   "para esta ventana."),
        ).font = Font(color=_XL_GRIS, italic=True)
        fila += 2      # si no, la leyenda de abajo pisa este mensaje
    else:
        for account in accounts:
            fila, hay_parcial = _tabla_excel(ws, account, periods, fila)
            algun_parcial = algun_parcial or hay_parcial
            fila += 2      # aire entre cuentas

    ws.cell(row=fila, column=1, value=_LEYENDA_ACCO).font = Font(
        color=_XL_GRIS, size=9, italic=True,
    )
    fila += 1

    if algun_parcial:
        ws.cell(row=fila, column=1, value=_NOTA_MTD).font = Font(
            color=_XL_GRIS, size=9, italic=True,
        )

    _autofit(ws)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
