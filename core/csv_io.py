"""Encoding y separador de un CSV que sube el usuario.

Logica pura: recibe bytes y devuelve strings. No lee disco, no toca la UI y no
parsea el CSV; eso lo hace quien llama, con el encoding y el separador que
resuelven estas funciones.

Salio del import de OC de M37 (`modules/pages/supply_ordenes.py`) y se movio a
core/ porque el mismo bug aparecio en `pricing_dashboard._parse_fee`
(UnicodeDecodeError en el byte 0xe1, reportado por Marcos el 24/09). No es un
caso aislado: hay 8 lecturas de archivos subidos con el encoding fijo en 6
archivos, y dos modulos que ya lo resolvieron por su cuenta y de forma distinta
(`atom11_rules_builder` cae a latin-1; `listing_compliance` prueba 4 encodings
en otro orden).

`encoding_csv` prueba utf-8-sig PRIMERO a proposito. Hay modulos que dependen de
que el BOM de UTF-8 se saque para que el primer header quede limpio
(`pricing_dashboard`, docstring L24-28): con utf-8-sig adelante, un archivo que
hoy se lee bien no cambia de comportamiento.
"""

from __future__ import annotations

import csv

DELIMITADORES_CSV = ",;\t|"
"""Candidatos a separador del CSV. Acotados a proposito: ver `sep_csv`."""

ENCODINGS_CSV = ("utf-8-sig", "cp1252", "latin-1")
"""Cascada de decodificacion del CSV, en orden. Ver `encoding_csv`."""

BOMS_UTF16 = (b"\xff\xfe", b"\xfe\xff")


def encoding_csv(data: bytes) -> str:
    """Encoding con el que hay que leer este CSV.

    Los proveedores exportan desde su propio Excel y su propio locale (Peru,
    Ecuador, Bolivia, China, Pakistan): asumir UTF-8 en todos rechaza archivos
    buenos. La cascada, en orden:

    1. BOM de UTF-16 (`\\xff\\xfe` / `\\xfe\\xff`) -> utf-16. Es lo que escribe
       el "Guardar como" de Excel en algunas variantes, y sin esto el archivo
       ni se abre.
    2. utf-8-sig. Lo mas comun, y se come el BOM de UTF-8 si lo hay.
    3. cp1252. Lo que Excel en Windows escribe de verdad en español.
    4. latin-1, ultimo recurso.

    Por que latin-1 va ULTIMO y no segundo: nunca falla, decodifica cualquier
    byte. Si se lo prueba antes que cp1252, un archivo que fallo UTF-8 por otra
    razon se convierte en mojibake silencioso. cp1252 falla ruidosamente en los
    bytes que no le corresponden, asi que filtra antes del ultimo recurso.

    Args:
        data: Bytes del archivo.

    Returns:
        Nombre del encoding. Siempre devuelve uno: latin-1 no falla.
    """
    if data[:2] in BOMS_UTF16:
        return "utf-16"
    for encoding in ENCODINGS_CSV:
        try:
            data.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    return "latin-1"


def sep_csv(data: bytes, encoding: str) -> str:
    """Separador del CSV, sniffeado entre los candidatos razonables.

    NO se usa `sep=None` de pandas: su sniffer no acota los delimitadores y con
    un archivo de UNA columna elige cualquier caracter repetido. Con `SKU / A1 /
    A2` elige la letra 'U' y parte los SKU en dos, en silencio y sin fallar.
    Acotado a `, ; tab |`, ese archivo se lee como una sola columna.

    Sin pistas suficientes (una columna, o archivo raro) devuelve ',': un
    separador que no aparece deja la fila entera en una celda, que es
    exactamente lo que se quiere para un archivo de una columna.

    `encoding` lo resuelve `encoding_csv` y lo comparte con la lectura: si el
    sniffer mirara un texto decodificado distinto del que despues parsea pandas,
    podria elegir un separador que en el otro texto no existe.

    Args:
        data: Bytes del archivo.
        encoding: El que devolvio `encoding_csv` para estos mismos bytes.

    Returns:
        El caracter separador.
    """
    texto = data.decode(encoding, errors="replace")
    try:
        return csv.Sniffer().sniff(texto[:4096], delimiters=DELIMITADORES_CSV).delimiter
    except csv.Error:
        return ","
