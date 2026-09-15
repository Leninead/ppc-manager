"""
Parser del Bulk File de Amazon Ads (Sponsored Products).

Por que existe:
  El STR standalone que se bajaba de Campaign Manager NO trae los IDs
  numericos de Amazon. Sin esos IDs, todo bulk generado a partir de el es
  inejecutable en modo REFERENCIA (INV-5.1): pone el NOMBRE de campana en
  Campaign ID, que solo resuelve al CREAR entidades nuevas.

  El Bulk File completo si los trae. Su hoja "SP Search Term Report" ata
  cada search term a Campaign ID / Ad Group ID / Keyword ID reales, y la
  hoja "Sponsored Products Campaigns" aporta Portfolio Name, Match Type y
  State — los tres datos que INV-11 necesita para no negativizar contra el
  ranking organico.

Regla dura de este modulo:
  Los cuatro campos de ID salen SIEMPRE como string. Un ID en float64 se
  renderiza como "4.091515e+14" en pantalla y como "409151500000001.0" al
  escribirlo a archivo. Amazon rechaza las dos formas. La conversion es
  float -> int -> str, y NaN -> "".

Alcance:
  Solo parseo y helpers de calculo. La clasificacion de negativos y el
  harvest NO viven aca.

Sin dependencia de Streamlit a proposito: el modulo es codigo puro y por
eso testeable sin levantar la app. El cacheo (@st.cache_data) es
responsabilidad del caller.

Contrato: .claude/skills/ppc-business-invariants.md — INV-3, INV-5, INV-11.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


# ============================================================================
# Constantes publicas
# ============================================================================

SHEET_STR: str = "SP Search Term Report"
SHEET_CAMPAIGNS: str = "Sponsored Products Campaigns"

# Sufijo que Amazon le cuelga a las columnas de solo-lectura. Estorba para
# indexar, y el mismo dato aparece con y sin el segun la hoja.
_SUFIJO_INFO: str = " (Informational only)"

# Columnas que son IDs y por lo tanto van si o si a string.
_ID_COLS: tuple[str, ...] = (
    "Campaign ID",
    "Ad Group ID",
    "Keyword ID",
    "Product Targeting ID",
    "Portfolio ID",
    "Ad ID",
)

# Valores canonicos de Match Type positivo (INV-5.3).
_MATCH_TYPES_CANONICOS: dict[str, str] = {
    "exact": "Exact",
    "phrase": "Phrase",
    "broad": "Broad",
}


# ============================================================================
# Helpers privados
# ============================================================================

def _norm_col(nombre: str) -> str:
    """Saca el sufijo '(Informational only)' y espacios sobrantes."""
    s = str(nombre).strip()
    if s.endswith(_SUFIJO_INFO):
        s = s[: -len(_SUFIJO_INFO)]
    return s.strip()


def _id_to_str(v: Any) -> str:
    """
    Normaliza un ID de Amazon a string de digitos.

    float64 -> int -> str, para matar tanto la notacion cientifica
    ("4.091515e+14") como el sufijo decimal ("409151500000001.0").
    NaN / None / "" / "nan" -> "".
    Si el valor no es numerico se devuelve tal cual (puede ser un alias
    de INV-5.1, que es un string arbitrario y valido).
    """
    if v is None:
        return ""
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        return str(int(v))
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return str(v)

    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "nat", "<na>"):
        return ""
    try:
        return str(int(float(s)))
    except (TypeError, ValueError):
        return s  # alias no numerico: se respeta


def _ids_a_string(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica _id_to_str a todas las columnas de ID presentes en el df."""
    for col in _ID_COLS:
        if col in df.columns:
            df[col] = df[col].map(_id_to_str)
    return df


def _match_type_canonico(v: Any) -> str:
    """
    Lleva el Match Type a Title Case (INV-5.3).

    Amazon no es consistente con el casing entre exports. Devuelve "" para
    filas sin match type (product targeting).
    """
    s = str(v).strip() if v is not None else ""
    if s == "" or s.lower() in ("nan", "none"):
        return ""
    return _MATCH_TYPES_CANONICOS.get(s.lower(), s)


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    """Columna como numerica con NaN->0. Serie de ceros si la col no existe."""
    if col not in df.columns:
        return pd.Series(0.0, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


# ============================================================================
# API publica — parseo
# ============================================================================

def parse_bulk_str(file: Any) -> pd.DataFrame:
    """
    Lee la hoja "SP Search Term Report" del Bulk File.

    Args:
        file: ruta, bytes o file-like con el .xlsx del bulk.

    Returns:
        DataFrame con las columnas del reporte, mas:
          - IDs (Campaign/Ad Group/Keyword/Product Targeting) como string
          - nombres de columna sin el sufijo "(Informational only)"
          - "_origen_match_type": Match Type de origen en Title Case
            (Exact/Phrase/Broad), "" si la fila es product targeting.
            Es el dato que INV-11.1 usa para excluir candidatos.
          - "_es_product_targeting": True si Keyword ID esta vacio y
            Product Targeting ID no.

    Raises:
        ValueError: si el archivo no tiene la hoja esperada.
    """
    df = _leer_hoja(file, SHEET_STR)
    df.columns = [_norm_col(c) for c in df.columns]
    df = _ids_a_string(df)

    kw_id = df["Keyword ID"] if "Keyword ID" in df.columns else pd.Series("", index=df.index)
    pt_id = df["Product Targeting ID"] if "Product Targeting ID" in df.columns else pd.Series("", index=df.index)

    df["_es_product_targeting"] = (kw_id.astype(str) == "") & (pt_id.astype(str) != "")

    if "Match Type" in df.columns:
        df["_origen_match_type"] = df["Match Type"].map(_match_type_canonico)
    else:
        df["_origen_match_type"] = ""
    # Una fila de product targeting no tiene match type de keyword.
    df.loc[df["_es_product_targeting"], "_origen_match_type"] = ""

    return df


def parse_bulk_campaigns(file: Any) -> pd.DataFrame:
    """
    Lee la hoja "Sponsored Products Campaigns" del Bulk File.

    Mismo tratamiento de IDs (string) y de nombres de columna que
    parse_bulk_str. Es la fuente de INV-11.2 (Exact activas) y de
    INV-11.3 (portfolio por campana).

    Raises:
        ValueError: si el archivo no tiene la hoja esperada.
    """
    df = _leer_hoja(file, SHEET_CAMPAIGNS)
    df.columns = [_norm_col(c) for c in df.columns]
    return _ids_a_string(df)


def _leer_hoja(file: Any, sheet: str) -> pd.DataFrame:
    """Lee una hoja del xlsx con error explicito si no existe."""
    try:
        return pd.read_excel(file, sheet_name=sheet)
    except ValueError as exc:
        raise ValueError(
            f"El archivo no tiene la hoja {sheet!r}. "
            "Verifica que sea el Bulk File completo de Campaign Manager "
            "(Bulk Operations), no el Search Term Report standalone."
        ) from exc


# ============================================================================
# API publica — lookups sobre la hoja de campanas
# ============================================================================

def get_exact_activas(df_campaigns: pd.DataFrame) -> set[str]:
    """
    Keywords Exact ACTIVAS de la cuenta, normalizadas a lowercase + strip.

    Fuente del guard INV-11.2: un search term que ya existe como Exact
    activa no se negativiza, por mal que rinda en Broad o Phrase.

    Filtro: Entity == "Keyword" AND Match Type == "Exact" AND
    State == "enabled". Las pausadas y archivadas NO cuentan — si esta
    pausada, negativizar el termino no le saca trafico a nada.

    Returns:
        set de Keyword Text. Vacio si el df no trae las columnas necesarias.
    """
    requeridas = {"Entity", "Match Type", "State", "Keyword Text"}
    if not requeridas.issubset(df_campaigns.columns):
        return set()

    def _lower(col: str) -> pd.Series:
        return df_campaigns[col].astype(str).str.strip().str.lower()

    mask = (
        (_lower("Entity") == "keyword")
        & (_lower("Match Type") == "exact")
        & (_lower("State") == "enabled")
    )
    textos = df_campaigns.loc[mask, "Keyword Text"].dropna().astype(str).str.strip().str.lower()
    return set(t for t in textos if t)


def get_portfolio_por_campaign(df_campaigns: pd.DataFrame) -> dict[str, str]:
    """
    Mapa Campaign ID (string) -> Portfolio Name.

    Fuente de INV-11.3: los terminos de campanas en portfolio RANKING se
    marcan como ranking keyword por default y no se negativizan.

    Solo se leen las filas Entity == "Campaign", que son las que definen el
    portfolio. Campanas sin portfolio quedan fuera del dict.
    """
    if "Campaign ID" not in df_campaigns.columns:
        return {}
    if "Portfolio Name" not in df_campaigns.columns:
        return {}

    df = df_campaigns
    if "Entity" in df.columns:
        df = df[df["Entity"].astype(str).str.strip().str.lower() == "campaign"]

    out: dict[str, str] = {}
    for cid, portfolio in zip(df["Campaign ID"], df["Portfolio Name"]):
        cid_s = str(cid).strip()
        p_s = "" if portfolio is None else str(portfolio).strip()
        if cid_s and p_s and p_s.lower() != "nan":
            out[cid_s] = p_s
    return out


# ============================================================================
# API publica — calculo de thresholds (INV-3)
# ============================================================================

def calcular_cvr_por_campana(
    df_str: pd.DataFrame,
    min_clicks: int = 30,
) -> dict[str, float]:
    """
    CVR de PPC por campana: orders totales / clicks totales de esa campana.

    Args:
        df_str: salida de parse_bulk_str.
        min_clicks: piso de clicks para que la campana tenga estadistica
            suficiente. Por debajo, la campana NO entra al dict y el caller
            debe caer al CVR de cuenta (ver calcular_cvr_cuenta).

    Returns:
        dict Campaign ID (string) -> CVR en fraccion (0.10 == 10%).
        Las campanas con 0 clicks nunca entran: no hay division por cero.
    """
    if df_str.empty or "Campaign ID" not in df_str.columns:
        return {}

    tmp = pd.DataFrame({
        "cid": df_str["Campaign ID"].astype(str),
        "clicks": _num(df_str, "Clicks"),
        "orders": _num(df_str, "Orders"),
    })
    agg = tmp.groupby("cid", as_index=True)[["clicks", "orders"]].sum()

    out: dict[str, float] = {}
    for cid, fila in agg.iterrows():
        clicks = float(fila["clicks"])
        if clicks <= 0 or clicks < min_clicks:
            continue
        out[str(cid)] = float(fila["orders"]) / clicks
    return out


def calcular_cvr_cuenta(df_str: pd.DataFrame) -> float:
    """
    CVR agregado de todas las filas. Fallback de calcular_cvr_por_campana.

    Returns:
        CVR en fraccion. 0.0 si no hay clicks (evita la division por cero).
    """
    if df_str.empty:
        return 0.0
    clicks = float(_num(df_str, "Clicks").sum())
    if clicks <= 0:
        return 0.0
    return float(_num(df_str, "Orders").sum()) / clicks


def clicks_threshold(cvr: float) -> int:
    """
    Clicks sin orden necesarios para negativizar (INV-3).

        max(10, ceil((1 / cvr) * 2))

    CVR 20% -> 10 (minimo absoluto) | 10% -> 20 | 5% -> 40 | 2% -> 100.

    Args:
        cvr: CVR del producto en fraccion (0.10 == 10%).

    Returns:
        Threshold de clicks. Si cvr <= 0 devuelve 100, el valor mas
        conservador de la tabla: sin CVR conocido no se mata nada barato.
    """
    if cvr is None or cvr <= 0:
        return 100
    return max(10, math.ceil((1.0 / cvr) * 2))


def spend_threshold(precio: float) -> float:
    """
    Spend sin ventas necesario para negativizar (INV-3): precio * 0.50.

    Producto de $30 -> negativizar si gasto $15 sin convertir.
    """
    return float(precio) * 0.50


# ============================================================================
# Validacion del bulk antes de la descarga (INV-5)
# ============================================================================
#
# Por que vive aca y no en bulk_export.py:
#   El que valida no puede ser el mismo que construye. Si el validador
#   compartiera modulo con el builder, un bug de construccion se validaria a
#   si mismo y el AM se enteraria recien cuando Amazon rechace el archivo.
#
# Por que bloquea la descarga (INV-5.4):
#   Amazon hace ROLLBACK TOTAL: una sola fila invalida rechaza el ARCHIVO
#   COMPLETO. Evidencia: report__60_ -> 0 de 8 filas aplicadas, siendo el
#   unico defecto un valor de Match Type mal escrito en una celda.

_PRODUCT_SP_VALIDO: str = "Sponsored Products"

_ENTITIES_VALIDAS: frozenset[str] = frozenset({
    "Campaign",
    "Ad Group",
    "Product Ad",
    "Keyword",
    "Negative Keyword",
    "Campaign Negative Keyword",
    "Product Targeting",
    "Negative Product Targeting",
})

_OPERACIONES_VALIDAS: frozenset[str] = frozenset({"Create", "Update"})

_STATES_VALIDOS: frozenset[str] = frozenset({"enabled", "paused", "archived"})

# Match Type canonico por familia de Entity (INV-5.3).
_MT_POSITIVOS: tuple[str, ...] = ("Exact", "Phrase", "Broad")
_MT_NEGATIVOS: tuple[str, ...] = ("Negative Exact", "Negative Phrase")

_ENTITIES_MT_POSITIVO: frozenset[str] = frozenset({"Keyword", "Product Targeting"})
_ENTITIES_MT_NEGATIVO: frozenset[str] = frozenset({
    "Negative Keyword",
    "Campaign Negative Keyword",
})

_ENTITIES_CON_KEYWORD_TEXT: frozenset[str] = frozenset({
    "Keyword",
    "Negative Keyword",
    "Campaign Negative Keyword",
})

# Amazon rechaza un negativo que traiga Bid.
_ENTITIES_SIN_BID: frozenset[str] = frozenset({
    "Negative Keyword",
    "Campaign Negative Keyword",
})

# Valor prohibido con evidencia empirica: report__60_, 8/8 filas rechazadas.
_MT_PROHIBIDO: str = "campaignNegativeExact"
_MT_PROHIBIDO_LITERAL: str = (
    'Invalid value: "campaignNegativeExact" for column: "Match Type"'
)

# camelCase -> Title Case. Los camelCase NO tienen validacion empirica; el
# Title Case si. Clave normalizada a lowercase y sin espacios.
_MT_SUGERENCIA: dict[str, str] = {
    "exact": "Exact",
    "phrase": "Phrase",
    "broad": "Broad",
    "negativeexact": "Negative Exact",
    "negativephrase": "Negative Phrase",
    "campaignnegativeexact": "Negative Exact",
    "campaignnegativephrase": "Negative Phrase",
}

# Columnas sin las cuales no se puede ni construir ni validar el bulk.
_COLS_OBLIGATORIAS: tuple[str, ...] = (
    "Product",
    "Entity",
    "Operation",
    "Campaign ID",
    "Ad Group ID",
    "Keyword ID",
    "State",
    "Bid",
    "Keyword Text",
    "Match Type",
)

# INV-5.2, tabla de campos obligatorios por Entity.
# "requerido" = no puede ir vacio | "vacio" = tiene que ir vacio.
_REGLAS_IDS: dict[tuple[str, str], dict[str, str]] = {
    ("Campaign Negative Keyword", ""): {
        "Campaign ID": "requerido",
        "Ad Group ID": "vacio",
        "Keyword ID": "vacio",
    },
    ("Negative Keyword", ""): {
        "Campaign ID": "requerido",
        "Ad Group ID": "requerido",
        "Keyword ID": "vacio",
    },
    ("Keyword", "Create"): {
        "Campaign ID": "requerido",
        "Ad Group ID": "requerido",
        "Keyword ID": "vacio",
    },
    ("Keyword", "Update"): {
        "Campaign ID": "requerido",
        "Ad Group ID": "requerido",
        "Keyword ID": "requerido",
    },
}

# Umbrales de los warnings.
_BID_WARN: float = 20.00
_FILAS_WARN: int = 500
_ID_NUMERICO_MIN_DIGITOS: int = 10


@dataclass
class ErrorBulk:
    """
    Un problema detectado en el bulk.

    Attributes:
        fila: indice 0-based de la fila en el df. -1 para problemas del
            archivo entero (columnas faltantes, df vacio, warnings globales).
        columna: columna que tiene el problema. "" si es del archivo.
        valor: valor que trajo la celda, truncado a 50 chars.
        mensaje: explicacion en espanol, dirigida al AM.
        severidad: "error" (Amazon rechaza el archivo entero, no se descarga)
            o "warning" (sospechoso pero puede ser valido, se descarga igual).
    """

    fila: int
    columna: str
    valor: str
    mensaje: str
    severidad: str


def _raw(v: Any) -> str:
    """
    Celda a string sin normalizar el literal "nan".

    NaN / None / NaT reales -> "". Pero el STRING "nan" se devuelve tal cual:
    es sintoma de un ID mal parseado y lo tiene que cazar la validacion de
    formato, no taparlo este helper.
    """
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def _trunc(s: str) -> str:
    """Recorta a 50 chars para que el valor entre en la tabla de errores."""
    return s if len(s) <= 50 else s[:50]


def _mostrar(v: str) -> str:
    """Valor legible dentro de un mensaje."""
    return f"'{v}'" if v else "(vacio)"


def _a_float(s: str) -> float | None:
    """Bid a float. None si no es numerico."""
    if s == "":
        return None
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


def _es_id_numerico(s: str) -> bool:
    """True si parece un ID real de Amazon (~15 digitos), no un alias."""
    return s.isdigit() and len(s) >= _ID_NUMERICO_MIN_DIGITOS


def validate_bulk(df: pd.DataFrame) -> list[ErrorBulk]:
    """
    Valida un bulk de Amazon Ads SP antes de habilitar la descarga (INV-5).

    Amazon hace rollback total: una fila mala rechaza el archivo entero
    (INV-5.4). Por eso esta validacion va ANTES del st.download_button, no
    despues.

    Args:
        df: DataFrame con el bulk armado, en el schema de la hoja
            "Sponsored Products Campaigns".

    Returns:
        Lista de ErrorBulk. Vacia si el bulk es valido.
        Si hay al menos un ErrorBulk con severidad "error", el archivo NO se
        debe poder descargar. Los "warning" no bloquean.

    No muta el df recibido (INV-8).
    """
    # core.bulk_export imports this module at load time, so the shared keyword-text limits are imported here.
    from core.bulk_export import negative_keyword_text_problem

    errores: list[ErrorBulk] = []

    if df is None or len(df) == 0:
        return [
            ErrorBulk(
                fila=-1,
                columna="",
                valor="",
                mensaje=(
                    "El bulk no tiene ninguna fila. Amazon rechaza los archivos "
                    "vacios: revisa los filtros de la vista antes de descargar."
                ),
                severidad="error",
            )
        ]

    faltantes = [c for c in _COLS_OBLIGATORIAS if c not in df.columns]
    if faltantes:
        errores.append(
            ErrorBulk(
                fila=-1,
                columna=", ".join(faltantes),
                valor="",
                mensaje=(
                    "Al bulk le faltan columnas obligatorias del schema de Amazon: "
                    + ", ".join(faltantes)
                    + ". Sin esas columnas Amazon rechaza el archivo completo."
                ),
                severidad="error",
            )
        )

    d = df.reset_index(drop=True)
    cols = set(d.columns)

    for i in range(len(d)):
        fila = d.iloc[i]
        entity = _raw(fila.get("Entity"))
        operation = _raw(fila.get("Operation"))

        # E2. Product
        if "Product" in cols:
            producto = _raw(fila.get("Product"))
            if producto != _PRODUCT_SP_VALIDO:
                errores.append(ErrorBulk(
                    fila=i,
                    columna="Product",
                    valor=_trunc(producto),
                    mensaje=(
                        "La columna Product debe decir exactamente "
                        f"'{_PRODUCT_SP_VALIDO}' en todas las filas. Esta trae "
                        f"{_mostrar(producto)}."
                    ),
                    severidad="error",
                ))

        # E3. Entity
        if "Entity" in cols and entity not in _ENTITIES_VALIDAS:
            errores.append(ErrorBulk(
                fila=i,
                columna="Entity",
                valor=_trunc(entity),
                mensaje=(
                    f"El Entity {_mostrar(entity)} no existe en el schema de "
                    "Amazon. Ojo con las mayusculas: se escribe exactamente "
                    "'Negative Keyword', no 'Negative keyword'. Validos: "
                    + " | ".join(sorted(_ENTITIES_VALIDAS))
                    + "."
                ),
                severidad="error",
            ))

        # E4. Operation
        if "Operation" in cols and operation not in _OPERACIONES_VALIDAS:
            errores.append(ErrorBulk(
                fila=i,
                columna="Operation",
                valor=_trunc(operation),
                mensaje=(
                    f"La Operation {_mostrar(operation)} no es valida. Amazon "
                    "acepta 'Create' (crear la entidad) o 'Update' (modificar "
                    "una que ya existe)."
                ),
                severidad="error",
            ))

        # E5. State
        if "State" in cols:
            state = _raw(fila.get("State"))
            if state not in _STATES_VALIDOS:
                errores.append(ErrorBulk(
                    fila=i,
                    columna="State",
                    valor=_trunc(state),
                    mensaje=(
                        f"El State {_mostrar(state)} no es valido. Amazon acepta "
                        "'enabled', 'paused' o 'archived', siempre en minuscula."
                    ),
                    severidad="error",
                ))

        # E6. Match Type segun Entity (INV-5.3)
        if "Match Type" in cols:
            mt = _raw(fila.get("Match Type"))
            if entity in _ENTITIES_MT_NEGATIVO:
                validos: tuple[str, ...] | None = _MT_NEGATIVOS
            elif entity in _ENTITIES_MT_POSITIVO:
                validos = _MT_POSITIVOS
            else:
                validos = None

            if validos is not None and mt not in validos:
                if mt == _MT_PROHIBIDO:
                    mensaje = (
                        f"El Match Type '{_MT_PROHIBIDO}' esta prohibido: Amazon "
                        f"rechaza el archivo entero con {_MT_PROHIBIDO_LITERAL}. "
                        "Usa 'Negative Exact' (con espacio y mayusculas)."
                    )
                else:
                    sugerido = _MT_SUGERENCIA.get(mt.lower().replace(" ", ""))
                    mensaje = (
                        f"El Match Type {_mostrar(mt)} no es valido para un "
                        f"'{entity}'. Amazon acepta: " + " | ".join(validos) + "."
                    )
                    if sugerido and sugerido != mt:
                        if sugerido in validos:
                            mensaje += (
                                f" Usa '{sugerido}' (con espacio y mayusculas)."
                            )
                        else:
                            mensaje += (
                                f" El equivalente en Title Case de {_mostrar(mt)} "
                                f"es '{sugerido}', pero ese valor no corresponde "
                                f"a un '{entity}'."
                            )
                errores.append(ErrorBulk(
                    fila=i,
                    columna="Match Type",
                    valor=_trunc(mt),
                    mensaje=mensaje,
                    severidad="error",
                ))

        # E7. Campos obligatorios por Entity (INV-5.2)
        clave = (entity, operation) if entity == "Keyword" else (entity, "")
        reglas = _REGLAS_IDS.get(clave)
        if reglas:
            for col, exigencia in reglas.items():
                if col not in cols:
                    continue
                valor = _raw(fila.get(col))
                if exigencia == "requerido" and not valor:
                    detalle = (
                        " En una fila de Update, Amazon necesita el ID numerico "
                        "real de la entidad que vas a modificar."
                        if operation == "Update"
                        else ""
                    )
                    errores.append(ErrorBulk(
                        fila=i,
                        columna=col,
                        valor="",
                        mensaje=(
                            f"Falta {col}: una fila '{entity}' no se puede subir "
                            "sin ese campo. Amazon la rechaza con 'Missing "
                            "Parent ID' y tira el archivo entero." + detalle
                        ),
                        severidad="error",
                    ))
                elif exigencia == "vacio" and valor:
                    if entity == "Campaign Negative Keyword" and col == "Ad Group ID":
                        mensaje = (
                            "Un 'Campaign Negative Keyword' NO puede tener Ad "
                            "Group ID: el negativo va a nivel campana y no "
                            "pertenece a ningun ad group. Si lo que queres es un "
                            "negativo dentro de un ad group, el Entity correcto "
                            "es 'Negative Keyword'."
                        )
                    else:
                        mensaje = (
                            f"La columna {col} tiene que ir vacia en una fila "
                            f"'{entity}'. Borra el valor {_mostrar(valor)}."
                        )
                    errores.append(ErrorBulk(
                        fila=i,
                        columna=col,
                        valor=_trunc(valor),
                        mensaje=mensaje,
                        severidad="error",
                    ))

        # E8. Formato de los IDs
        for col in _ID_COLS:
            if col not in cols:
                continue
            valor = _raw(fila.get(col))
            if not valor:
                continue
            if "e+" in valor.lower():
                mensaje = (
                    f"El {col} {_mostrar(valor)} viene en notacion cientifica: "
                    "se leyo como numero en vez de como texto y perdio digitos. "
                    "Amazon lo rechaza. Tiene que ir el numero completo, sin 'e+'."
                )
            elif "." in valor:
                mensaje = (
                    f"El {col} {_mostrar(valor)} viene con decimales: se parseo "
                    "como float en vez de como texto. Amazon lo rechaza. Tiene "
                    "que ir sin el '.0' del final."
                )
            elif valor.lower() == "nan":
                mensaje = (
                    f"El {col} llego como el texto 'nan': la celda estaba vacia "
                    "en el origen y se convirtio mal. Amazon lo rechaza. Recarga "
                    "el Bulk File y volve a generar el archivo."
                )
            else:
                continue
            errores.append(ErrorBulk(
                fila=i,
                columna=col,
                valor=_trunc(valor),
                mensaje=mensaje,
                severidad="error",
            ))

        # E9. Keyword Text
        if "Keyword Text" in cols and entity in _ENTITIES_CON_KEYWORD_TEXT:
            kw = _raw(fila.get("Keyword Text"))
            if not kw:
                errores.append(ErrorBulk(
                    fila=i,
                    columna="Keyword Text",
                    valor="",
                    mensaje=(
                        f"Falta el Keyword Text: una fila '{entity}' sin termino "
                        "no significa nada para Amazon y rechaza el archivo."
                    ),
                    severidad="error",
                ))
            elif entity in _ENTITIES_MT_NEGATIVO:
                problema = negative_keyword_text_problem(kw, _raw(fila.get("Match Type")))
                if problema:
                    errores.append(ErrorBulk(
                        fila=i,
                        columna="Keyword Text",
                        valor=_trunc(kw),
                        mensaje=(
                            f"Amazon rechaza este Keyword Text en un '{entity}': "
                            f"{problema}. Una sola fila asi tira el archivo entero."
                        ),
                        severidad="error",
                    ))

        # E10. Bid
        bid_val: float | None = None
        if "Bid" in cols:
            bid_raw = _raw(fila.get("Bid"))
            if entity == "Keyword":
                bid_val = _a_float(bid_raw)
                if bid_val is None:
                    errores.append(ErrorBulk(
                        fila=i,
                        columna="Bid",
                        valor=_trunc(bid_raw),
                        mensaje=(
                            f"El Bid {_mostrar(bid_raw)} no es un numero. Una "
                            "keyword tiene que llevar un bid en dolares, por "
                            "ejemplo 0.75."
                        ),
                        severidad="error",
                    ))
                elif bid_val <= 0:
                    errores.append(ErrorBulk(
                        fila=i,
                        columna="Bid",
                        valor=_trunc(bid_raw),
                        mensaje=(
                            f"El Bid de {bid_val:.2f} tiene que ser mayor a 0. Un "
                            "bid de 0 no compite en ninguna subasta y Amazon "
                            "rechaza la fila."
                        ),
                        severidad="error",
                    ))
            elif entity in _ENTITIES_SIN_BID and bid_raw:
                errores.append(ErrorBulk(
                    fila=i,
                    columna="Bid",
                    valor=_trunc(bid_raw),
                    mensaje=(
                        f"Un '{entity}' no lleva Bid: un negativo no puja por "
                        "nada. Amazon rechaza la fila. Deja la celda vacia."
                    ),
                    severidad="error",
                ))

        # W3. Bid inusualmente alto
        if bid_val is not None and bid_val > _BID_WARN:
            errores.append(ErrorBulk(
                fila=i,
                columna="Bid",
                valor=_trunc(_raw(fila.get("Bid"))),
                mensaje=(
                    f"El Bid de {bid_val:.2f} es inusualmente alto. No es "
                    "invalido, pero revisa que el precio y el target ACoS del "
                    "producto sean los correctos antes de subir el archivo."
                ),
                severidad="warning",
            ))

    # W2. Keyword Text duplicado en la misma Campaign + Ad Group + Match Type
    if "Keyword Text" in cols:
        vistos: dict[tuple[str, str, str, str], int] = {}
        for i in range(len(d)):
            fila = d.iloc[i]
            kw = _raw(fila.get("Keyword Text")).lower()
            if not kw:
                continue
            clave_dup = (
                _raw(fila.get("Campaign ID")).lower(),
                _raw(fila.get("Ad Group ID")).lower(),
                _raw(fila.get("Match Type")).lower(),
                kw,
            )
            if clave_dup in vistos:
                errores.append(ErrorBulk(
                    fila=i,
                    columna="Keyword Text",
                    valor=_trunc(_raw(fila.get("Keyword Text"))),
                    mensaje=(
                        f"Este termino ya aparece en la fila {vistos[clave_dup]} "
                        "con la misma campana, ad group y match type. Amazon lo "
                        "acepta, pero la fila repetida no agrega nada."
                    ),
                    severidad="warning",
                ))
            else:
                vistos[clave_dup] = i

    # W1. Modo de ID mezclado (INV-5.1)
    if "Campaign ID" in cols:
        hay_numerico = False
        hay_alias = False
        for i in range(len(d)):
            valor = _raw(d.iloc[i].get("Campaign ID"))
            if not valor:
                continue
            if _es_id_numerico(valor):
                hay_numerico = True
            else:
                hay_alias = True
        if hay_numerico and hay_alias:
            errores.append(ErrorBulk(
                fila=-1,
                columna="Campaign ID",
                valor="",
                mensaje=(
                    "El archivo mezcla los dos modos de Campaign ID: algunas "
                    "filas traen el ID numerico de una campana que ya existe y "
                    "otras traen un alias de una campana que se crea en este "
                    "mismo archivo. Puede ser correcto si estas creando una "
                    "campana nueva y ademas tocando una existente, pero es raro: "
                    "revisalo antes de subir."
                ),
                severidad="warning",
            ))

    # W4. Archivo muy grande
    if len(d) > _FILAS_WARN:
        errores.append(ErrorBulk(
            fila=-1,
            columna="",
            valor="",
            mensaje=(
                f"El archivo tiene {len(d)} filas. Amazon las procesa, pero "
                f"conviene partirlo en tandas de {_FILAS_WARN}: si rebota, es "
                "mas facil encontrar cual fila lo rompio."
            ),
            severidad="warning",
        ))

    return errores
