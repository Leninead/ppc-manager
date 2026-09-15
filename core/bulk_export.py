"""
Constructores de bulks Amazon Ads SP ejecutables.

Por que se rediseno:
  La version anterior tenia UN constructor generico (build_amazon_bulk) que
  escribia el NOMBRE de la campana en la columna Campaign ID. Eso solo
  resuelve en modo ALIAS (INV-5.1), o sea cuando la campana se crea en el
  mismo archivo. Los dos usos reales — negativizar y harvestear sobre
  campanas que YA existen — son modo REFERENCIA y necesitan el ID numerico
  real. A eso se le sumaban Entity 'Negative keyword' con k minuscula y los
  Match Type en camelCase, ninguno de los dos canonico (INV-5.3).

  Resultado: bulks que Amazon rechazaba enteros. Y como Amazon hace rollback
  total (INV-5.4), un archivo de 200 filas con una sola mal armada no aplica
  ninguna.

Diseno actual — cuatro constructores, no uno:
  Las firmas son incompatibles entre si A PROPOSITO. Cada caso de uso de
  INV-5.2 pide campos distintos, y un unico constructor generico obliga a
  decidir en runtime lo que se puede decidir en el sitio de la llamada.

  - build_campaign_negative(rows)  Entity 'Campaign Negative Keyword'
  - build_adgroup_negative(rows)   Entity 'Negative Keyword'
  - build_keyword_create(rows)     Entity 'Keyword',  Operation 'Create'
  - build_bid_update(rows)         Entity 'Keyword',  Operation 'Update'

  Los cuatro devuelven (bulk_df, invalid_df). Ninguna fila dudosa entra al
  bulk: si no se puede armar bien, va a invalid_df con el motivo escrito.

Doble llave:
  Antes de devolver, cada constructor pasa su propio bulk_df por
  validate_bulk (core.bulk_parser). Lo que el validador marque como error de
  severidad "error" sale del bulk y se va a invalid_df. El validador vive en
  otro modulo a proposito: el que valida no puede ser el mismo que construye.

Sin dependencia de Streamlit: codigo puro, testeable sin levantar la app.

Contrato: .claude/skills/ppc-business-invariants.md — INV-5.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import pandas as pd

# _id_to_str es privado de bulk_parser, pero es LA normalizacion de IDs del
# repo y duplicarla seria garantizar que las dos copias se separen. Se importa
# a proposito. validate_bulk es la segunda llave de cada constructor.
from core.bulk_parser import _id_to_str, validate_bulk
from core.excel_text import force_text_cells


# ============================================================================
# Constantes publicas
# ============================================================================

# Schema del template validado — 26 columnas, ORDEN MANDATORIO (INV-5.5).
# Las columnas anexas del analisis (Prioridad, Regla, Customer Search Term)
# NUNCA van aca: van en la hoja Metadata.
_BULK_COLS: list[str] = [
    "Product",
    "Entity",
    "Operation",
    "Campaign ID",
    "Ad Group ID",
    "Portfolio ID",
    "Ad ID",
    "Keyword ID",
    "Product Targeting ID",
    "Campaign Name",
    "Ad Group Name",
    "Start Date",
    "End Date",
    "Targeting Type",
    "State",
    "Daily Budget",
    "SKU",
    "Ad Group Default Bid",
    "Bid",
    "Keyword Text",
    "Match Type",
    "Bidding Strategy",
    "Placement",
    "Percentage",
    "Product Targeting Expression",
    "Sites",
]

# Valores canonicos (INV-5.3). Title Case, que es el que tiene validacion
# empirica. Los camelCase (negativeExact, exact) no la tienen.
_PRODUCT_SP: str = "Sponsored Products"
_MT_POSITIVOS: tuple[str, ...] = ("Exact", "Phrase", "Broad")
_MT_NEGATIVOS: tuple[str, ...] = ("Negative Exact", "Negative Phrase")

_BULK_SHEET_NAME: str = "Sponsored Products Campaigns"
_METADATA_SHEET_NAME: str = "Metadata Capybaras"

_COL_INVALID_REASON: str = "_invalid_reason"


@dataclass(frozen=True)
class KeywordTextLimits:
    max_characters: int
    max_words_by_match_type: Mapping[str, int]
    forbidden_characters: re.Pattern


# Amazon's negative keyword limits; the negatives selection and validate_bulk both read this one constant.
NEGATIVE_KEYWORD_TEXT_LIMITS = KeywordTextLimits(
    max_characters=80,
    max_words_by_match_type=MappingProxyType({"Negative Phrase": 4, "Negative Exact": 10}),
    forbidden_characters=re.compile(r"[%$#@*!^={}\[\]<>?/\\|`]"),
)


def negative_keyword_text_problem(keyword_text: str, match_type: str) -> str | None:
    """Why Amazon rejects this negative Keyword Text (Spanish, lower case), or None when it is accepted."""
    limits = NEGATIVE_KEYWORD_TEXT_LIMITS
    text = keyword_text.strip()
    if len(text) > limits.max_characters:
        return f"tiene {len(text)} caracteres y Amazon admite hasta {limits.max_characters}"
    max_words = limits.max_words_by_match_type.get(match_type)
    word_count = len(text.split())
    if max_words is not None and word_count > max_words:
        return f"tiene {word_count} palabras y un {match_type} admite hasta {max_words}"
    forbidden = limits.forbidden_characters.search(text)
    if forbidden:
        return f"lleva el signo «{forbidden.group()}», que Amazon no acepta en keywords"
    return None


# ============================================================================
# Helpers privados
# ============================================================================

def _coerce_str(v: Any) -> str:
    """Convierte a string limpio. NaN / None / 'nan' -> ''."""
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    if s.lower() == "nan":
        return ""
    return s


def _norm_id(v: Any) -> tuple[str, str | None]:
    """
    Normaliza un ID a string, o explica por que no se puede.

    Returns:
        (id_normalizado, motivo_de_invalidez_o_None).

    El float con cola decimal ('375512123676480.0') SI se repara: no hay
    perdida de informacion, es el mismo numero mal renderizado.

    La notacion cientifica ('4.42e+14') NO se repara y la fila se marca
    invalida. float('4.42e+14') da 442000000000000, un ID que parece valido
    y no es el que el AM quiso: los digitos que faltaban ya se perdieron en
    el origen. Repararlo seria inventar un ID.
    """
    crudo = _coerce_str(v)
    if crudo == "":
        return "", None
    if "e+" in crudo.lower():
        return "", (
            f"ID en notacion cientifica ({crudo!r}): perdio digitos al leerse "
            "como numero. Cargalo como texto desde el Bulk File."
        )
    return _id_to_str(crudo), None


def _coerce_bid(v: Any) -> tuple[float | None, str | None]:
    """
    Convierte el bid a float, o explica por que no se puede.

    Returns:
        (bid_redondeado_o_None, motivo_de_invalidez_o_None).

    Cambio de comportamiento respecto de la version anterior: antes un bid no
    convertible ('$1.20', 'abc') se transformaba en '' y la fila entraba
    igual al bulk. Amazon rechazaba el archivo entero y el AM no tenia como
    saber cual fila lo habia roto. Ahora la fila no entra y se dice por que.
    """
    crudo = _coerce_str(v)
    if crudo == "":
        return None, "Bid vacio: una keyword tiene que llevar bid."
    try:
        f = float(crudo)
    except (TypeError, ValueError):
        return None, (
            f"Bid {crudo!r} no es un numero. Va sin simbolo de moneda y con "
            "punto decimal, por ejemplo 0.75."
        )
    if pd.isna(f):
        return None, "Bid vacio: una keyword tiene que llevar bid."
    if f <= 0:
        return None, (
            f"Bid de {f:.2f}: tiene que ser mayor a 0, un bid de 0 no compite "
            "en ninguna subasta."
        )
    return round(f, 2), None


@dataclass(frozen=True)
class _Spec:
    """
    Que exige cada caso de uso de INV-5.2.

    Cada campo de ID / bid es "requerido" (no puede venir vacio) o
    "prohibido" (tiene que venir vacio; si viene, la fila es invalida).
    """

    entity: str
    operation: str
    match_types: tuple[str, ...]
    ad_group_id: str
    keyword_id: str
    bid: str


_SPEC_CAMPAIGN_NEGATIVE = _Spec(
    entity="Campaign Negative Keyword",
    operation="Create",
    match_types=_MT_NEGATIVOS,
    ad_group_id="prohibido",
    keyword_id="prohibido",
    bid="prohibido",
)

_SPEC_ADGROUP_NEGATIVE = _Spec(
    entity="Negative Keyword",
    operation="Create",
    match_types=_MT_NEGATIVOS,
    ad_group_id="requerido",
    keyword_id="prohibido",
    bid="prohibido",
)

_SPEC_KEYWORD_CREATE = _Spec(
    entity="Keyword",
    operation="Create",
    match_types=_MT_POSITIVOS,
    ad_group_id="requerido",
    keyword_id="prohibido",
    bid="requerido",
)

_SPEC_BID_UPDATE = _Spec(
    entity="Keyword",
    operation="Update",
    match_types=_MT_POSITIVOS,
    ad_group_id="requerido",
    keyword_id="requerido",
    bid="requerido",
)


def _fila_bulk(**valores: Any) -> dict:
    """Fila con las 26 columnas, todas en '' salvo las que se pasen."""
    fila = {col: "" for col in _BULK_COLS}
    fila.update(valores)
    return fila


def _motivo_id(
    valor_crudo: Any,
    *,
    campo: str,
    columna: str,
    exigencia: str,
    entity: str,
) -> tuple[str, str | None]:
    """Normaliza un ID y lo contrasta contra lo que el spec exige."""
    normalizado, motivo = _norm_id(valor_crudo)
    if motivo:
        return "", f"{columna}: {motivo}"

    if exigencia == "requerido" and not normalizado:
        return "", (
            f"Falta {campo}: una fila '{entity}' no se puede subir sin ese "
            "campo. Amazon la rechaza con 'Missing Parent ID' y tira el "
            "archivo entero."
        )
    if exigencia == "prohibido" and normalizado:
        if entity == "Campaign Negative Keyword" and columna == "Ad Group ID":
            return "", (
                "Un 'Campaign Negative Keyword' NO puede tener Ad Group ID: "
                "el negativo va a nivel campana y no pertenece a ningun ad "
                "group. Si el negativo es de un ad group puntual, el "
                "constructor correcto es build_adgroup_negative."
            )
        return "", (
            f"{columna} tiene que ir vacio en una fila '{entity}', y llego "
            f"{normalizado!r}."
        )
    return normalizado, None


def _armar(
    rows: Iterable[dict] | pd.DataFrame,
    spec: _Spec,
    *,
    state: str = "enabled",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Motor comun de los cuatro constructores.

    Arma las filas segun el spec, aparta las que no cumplen, y despues pasa
    el bulk resultante por validate_bulk como segunda llave.
    """
    if isinstance(rows, pd.DataFrame):
        rows_list = rows.to_dict(orient="records")
    else:
        rows_list = list(rows)

    validas: list[dict] = []
    invalidas: list[dict] = []

    for row in rows_list:
        motivos: list[str] = []

        campaign_id, motivo = _motivo_id(
            row.get("campaign_id"),
            campo="campaign_id",
            columna="Campaign ID",
            exigencia="requerido",
            entity=spec.entity,
        )
        if motivo:
            motivos.append(motivo)

        ad_group_id, motivo = _motivo_id(
            row.get("ad_group_id"),
            campo="ad_group_id",
            columna="Ad Group ID",
            exigencia=spec.ad_group_id,
            entity=spec.entity,
        )
        if motivo:
            motivos.append(motivo)

        keyword_id, motivo = _motivo_id(
            row.get("keyword_id"),
            campo="keyword_id",
            columna="Keyword ID",
            exigencia=spec.keyword_id,
            entity=spec.entity,
        )
        if motivo:
            motivos.append(motivo)

        keyword_text = _coerce_str(row.get("keyword_text"))
        if not keyword_text:
            motivos.append(
                f"Keyword Text vacio: una fila '{spec.entity}' sin termino no "
                "significa nada para Amazon."
            )

        match_type = _coerce_str(row.get("match_type"))
        if match_type not in spec.match_types:
            motivos.append(
                f"Match Type {match_type!r} no es valido para un "
                f"'{spec.entity}'. Amazon acepta: "
                + " | ".join(spec.match_types)
                + ". El casing importa: es Title Case, no camelCase."
            )

        # Bid. En los negativos se fuerza vacio: Amazon rechaza un negativo
        # que traiga bid, y el negativo no puja por nada.
        bid_val: float | str = ""
        if spec.bid == "requerido":
            bid_num, motivo = _coerce_bid(row.get("bid"))
            if motivo:
                motivos.append(motivo)
            else:
                bid_val = bid_num  # type: ignore[assignment]

        registro = _fila_bulk(
            Product=_PRODUCT_SP,
            Entity=spec.entity,
            Operation=spec.operation,
            **{
                "Campaign ID": campaign_id,
                "Ad Group ID": ad_group_id,
                "Keyword ID": keyword_id,
                # Nombres: informativos cuando la fila referencia por ID.
                # Se pasan si el caller los tiene, para que el AM reconozca
                # la fila al abrir el archivo.
                "Campaign Name": _coerce_str(row.get("campaign_name")),
                "Ad Group Name": _coerce_str(row.get("ad_group_name")),
                "State": state,
                "Bid": bid_val,
                "Keyword Text": keyword_text,
                "Match Type": match_type,
            },
        )

        if motivos:
            invalido = dict(registro)
            invalido[_COL_INVALID_REASON] = " | ".join(motivos)
            invalidas.append(invalido)
        else:
            validas.append(registro)

    bulk_df = pd.DataFrame(validas, columns=_BULK_COLS)

    # ── Segunda llave: el validador de core.bulk_parser sobre lo ya armado.
    # Si algo se le escapo al spec, la fila sale del bulk igual.
    if not bulk_df.empty:
        por_fila: dict[int, list[str]] = {}
        for err in validate_bulk(bulk_df):
            if err.severidad != "error":
                continue
            if err.fila < 0:
                # Error de archivo (columnas faltantes). Imposible por
                # construccion: _fila_bulk siempre emite las 26 columnas.
                continue
            por_fila.setdefault(err.fila, []).append(err.mensaje)

        if por_fila:
            for pos in sorted(por_fila):
                rechazada = bulk_df.iloc[pos].to_dict()
                rechazada[_COL_INVALID_REASON] = " | ".join(por_fila[pos])
                invalidas.append(rechazada)
            bulk_df = bulk_df.drop(index=sorted(por_fila)).reset_index(drop=True)

    invalid_df = pd.DataFrame(
        invalidas,
        columns=_BULK_COLS + [_COL_INVALID_REASON],
    )
    return bulk_df, invalid_df


# ============================================================================
# API publica — constructores
# ============================================================================

def build_campaign_negative(
    rows: Iterable[dict] | pd.DataFrame,
    *,
    state: str = "enabled",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Negativos a nivel CAMPANA (INV-5.2, fila 1).

    Args:
        rows: cada dict con
            campaign_id:   ID numerico real de Amazon (~15 digitos). La
                           campana ya existe, asi que va modo REFERENCIA:
                           el nombre no resuelve (INV-5.1).
            keyword_text:  el termino a negativizar.
            match_type:    "Negative Exact" | "Negative Phrase".
            campaign_name: opcional, informativo.
        state: "enabled" por default.

    Returns:
        (bulk_df, invalid_df). bulk_df con las 26 columnas en orden.

    Ad Group ID va SIEMPRE vacio y Bid tambien. Una row con ad_group_id es un
    error de nivel — el negativo de campana no pertenece a ningun ad group —
    y la fila entera se va a invalid_df.
    """
    return _armar(rows, _SPEC_CAMPAIGN_NEGATIVE, state=state)


def build_adgroup_negative(
    rows: Iterable[dict] | pd.DataFrame,
    *,
    state: str = "enabled",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Negativos a nivel AD GROUP (INV-5.2, fila 2).

    Args:
        rows: cada dict con
            campaign_id / ad_group_id: IDs numericos reales, los dos.
            keyword_text: el termino a negativizar.
            match_type:   "Negative Exact" | "Negative Phrase".
            campaign_name / ad_group_name: opcionales, informativos.
        state: "enabled" por default.

    Returns:
        (bulk_df, invalid_df).

    Bid va SIEMPRE vacio: Amazon rechaza un negativo que traiga bid.
    """
    return _armar(rows, _SPEC_ADGROUP_NEGATIVE, state=state)


def build_keyword_create(
    rows: Iterable[dict] | pd.DataFrame,
    *,
    state: str = "enabled",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Keywords nuevas (INV-5.2, fila 3).

    Args:
        rows: cada dict con
            campaign_id / ad_group_id: numericos si la campana y el ad group
                YA existen (modo REFERENCIA), o el mismo alias que usan las
                filas que los crean en este archivo (modo ALIAS, INV-5.1).
                Lo que no se puede es mezclar los dos criterios en una fila.
            keyword_text: la keyword.
            match_type:   "Exact" | "Phrase" | "Broad".
            bid:          numero mayor a 0. Techo por INV-1, que se aplica
                          rio arriba: este helper no calcula bids.
        state: "enabled" por default.

    Returns:
        (bulk_df, invalid_df).
    """
    return _armar(rows, _SPEC_KEYWORD_CREATE, state=state)


def build_bid_update(
    rows: Iterable[dict] | pd.DataFrame,
    *,
    state: str = "enabled",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Update de bid sobre keywords que ya existen (INV-5.2, fila 4).

    Args:
        rows: cada dict con
            campaign_id / ad_group_id / keyword_id: los TRES numericos.
                Sin keyword_id Amazon no sabe que keyword modificar y la fila
                es invalida. El dato sale del Bulk File
                (core.bulk_parser.parse_bulk_str), no del STR standalone.
            keyword_text: el texto de la keyword. Amazon lo resuelve por
                Keyword ID, pero la fila igual lo lleva — es lo que hace
                legible el archivo cuando el AM lo revisa antes de subir.
            match_type: "Exact" | "Phrase" | "Broad", el de la keyword.
            bid:        el bid nuevo, mayor a 0.
        state: "enabled" por default.

    Returns:
        (bulk_df, invalid_df).
    """
    return _armar(rows, _SPEC_BID_UPDATE, state=state)


# ============================================================================
# API publica — agregacion del STR
# ============================================================================

def aggregate_str_with_top_campaign(
    df_str: pd.DataFrame,
    *,
    term_col: str,
    spend_col: str,
    campaign_col: str | None,
    ad_group_col: str | None = None,
    match_type_col: str | None = None,
    extra_agg: dict | None = None,
    extra_inherit: list[str] | None = None,
) -> pd.DataFrame:
    """
    Agrupa STR por termino preservando Campaign Name / Ad Group / Match Type
    del row con MAYOR SPEND (criterio: idxmax sobre spend dentro del grupo).

    Si un term aparece en N campanas, gana la que invirtio mas. La decision
    de bid va contra el contexto que mas pesa economicamente.

    Args:
        df_str: STR raw cargado
        term_col: nombre de columna de search term (ej "Customer Search Term")
        spend_col: nombre de columna spend (criterio idxmax)
        campaign_col: nombre columna Campaign Name (None = no se preserva)
        ad_group_col: nombre columna Ad Group (None = no se preserva)
        match_type_col: nombre columna Match Type (None = no se preserva)
        extra_agg: dict {col: agg_func} para sumar otras metricas
                   (ej {"_sales": "sum", "_orders": "sum"})
        extra_inherit: columnas adicionales que se heredan del row de mayor
                   spend, igual que campaign_col / ad_group_col / match_type_col.
                   Pensado para los IDs del Bulk File (Campaign ID, Ad Group ID,
                   Keyword ID), que son lo que hace ejecutable un bulk.
                   Una columna que no exista en df_str se ignora EN SILENCIO,
                   igual que hace campaign_col. Es deliberado: el caller arma la
                   lista sin saber que trae el archivo del AM.

    Returns:
        DataFrame agrupado por term_col con cols:
          - term_col
          - cols de extra_agg agregadas
          - campaign_col (si != None) — Campaign del row con max spend
          - ad_group_col (si != None) — Ad Group del row con max spend
          - match_type_col (si != None) — Match Type del row con max spend
          - las de extra_inherit que existan — del mismo row con max spend
          - "_n_campaigns" (siempre, int) — cuantas campanas distintas tenia el term.
            N > 1 = ambiguo, AM debe revisar.

    Notas:
      - Si term_col tiene NaN, esas filas se descartan antes del groupby.
      - Si spend_col tiene NaN, se rellena con 0 para idxmax.
      - Todo lo heredado sale del MISMO row (el de mayor spend), asi que los
        IDs y el match type son consistentes entre si: no se mezclan campos de
        campanas distintas en una misma fila del resultado.
    """
    if term_col not in df_str.columns:
        raise ValueError(f"term_col {term_col!r} no esta en df_str.columns")
    if spend_col not in df_str.columns:
        raise ValueError(f"spend_col {spend_col!r} no esta en df_str.columns")

    df = df_str.copy()
    df = df.dropna(subset=[term_col])
    df[spend_col] = pd.to_numeric(df[spend_col], errors="coerce").fillna(0)

    # ── Paso 1: idxmax sobre spend por termino → row con mas inversion
    top_idx = df.groupby(term_col)[spend_col].idxmax()

    # ── Paso 2: cols a heredar del row top
    inherit_cols: list[str] = [term_col]
    if campaign_col and campaign_col in df.columns:
        inherit_cols.append(campaign_col)
    if ad_group_col and ad_group_col in df.columns:
        inherit_cols.append(ad_group_col)
    if match_type_col and match_type_col in df.columns:
        inherit_cols.append(match_type_col)
    for col in (extra_inherit or []):
        # Se ignora la que no exista (contrato documentado) y la repetida, que
        # romperia el .loc con un duplicado de columna.
        if col in df.columns and col not in inherit_cols:
            inherit_cols.append(col)

    top_rows = df.loc[top_idx, inherit_cols].reset_index(drop=True)

    # ── Paso 3: agregaciones extra (sum spend/sales/orders/...)
    agg_dict: dict = {spend_col: "sum"}
    if extra_agg:
        agg_dict.update(extra_agg)
    base = df.groupby(term_col, as_index=False).agg(agg_dict)

    # ── Paso 4: contar N campanas distintas por term (flag de ambiguedad)
    if campaign_col and campaign_col in df.columns:
        n_camps = (
            df.groupby(term_col)[campaign_col]
            .nunique(dropna=True)
            .rename("_n_campaigns")
            .reset_index()
        )
    else:
        n_camps = pd.DataFrame({term_col: base[term_col].unique(), "_n_campaigns": 1})

    # ── Paso 5: merge todo
    out = base.merge(top_rows, on=term_col, how="left").merge(
        n_camps, on=term_col, how="left"
    )

    # idxmax sobre spend trae el spend del row top, no el sum.
    # Sobreescribir spend_col con el SUM (base) — merge ya lo trae correcto desde base.

    return out


# ============================================================================
# API publica — escritura
# ============================================================================

def write_bulk_excel(
    bulk_df: pd.DataFrame,
    metadata_df: pd.DataFrame | None = None,
    *,
    bulk_sheet_name: str = _BULK_SHEET_NAME,
    metadata_sheet_name: str = _METADATA_SHEET_NAME,
) -> bytes:
    """
    Genera Excel multi-hoja para download.

    Args:
        bulk_df: DataFrame con las 26 cols del schema Amazon (salida de
                 cualquiera de los cuatro constructores).
        metadata_df: DataFrame opcional con info contextual (Accion, Regla,
                     Prioridad, etc). Esta hoja NO se sube a Amazon; queda
                     como referencia del AM. INV-5.5: las columnas anexas van
                     aca y nunca en la hoja del bulk.
        bulk_sheet_name: por default "Sponsored Products Campaigns" (oficial
                         Amazon). Si lo cambias podes romper compat.
        metadata_sheet_name: por default "Metadata Capybaras".

    Returns:
        bytes — listo para st.download_button(data=...).
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        bulk_df.to_excel(writer, sheet_name=bulk_sheet_name, index=False)
        if metadata_df is not None and not metadata_df.empty:
            metadata_df.to_excel(writer, sheet_name=metadata_sheet_name, index=False)
        force_text_cells(writer.book)
    return buf.getvalue()
