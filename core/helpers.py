import pandas as pd
import re


def _color_pct(val):
    """Cell style for % change columns."""
    if pd.isna(val):
        return ""
    if val > 0:
        return "color: #28a745; font-weight: bold"
    if val < 0:
        return "color: #dc3545; font-weight: bold"
    return "color: gray"


def extract_sqp_brand(file):
    """Extrae el nombre de marca de la fila de metadata del SQP de Amazon."""
    try:
        first_row = pd.read_csv(file, nrows=0, header=None).columns[0] if not file.name.endswith(".xlsx") else str(pd.read_excel(file, nrows=1, header=None).iloc[0, 0])
        file.seek(0)
        match = re.search(r'Brand=\["([^"]+)"\]', first_row, re.IGNORECASE)
        if match:
            return match.group(1).lower().strip()
    except Exception:
        pass
    file.seek(0)
    return None


def read_sqp(file):
    """Lee un archivo SQP de Amazon, saltando la fila de metadata inicial."""
    if file.name.endswith(".xlsx"):
        return pd.read_excel(file, skiprows=1)
    return pd.read_csv(file, skiprows=1)
