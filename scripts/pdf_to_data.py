"""
Utilitario one-off para extraer tablas + texto de PDFs de reportes.

Uso:
    python scripts/pdf_to_data.py "C:\\Users\\lenin\\Downloads\\ltd_monthly_report_may2026.pdf"

Output (en la misma carpeta del PDF):
    - <nombre>_text.txt              (texto plano completo, liviano para subir a Claude.ai)
    - <nombre>_table_NN_pXX.csv      (una por cada tabla detectada, numerada + página)
"""
import sys
import csv
from pathlib import Path

import pdfplumber


def extract_pdf(pdf_path: Path) -> None:
    if not pdf_path.exists():
        print(f"ERROR: no se encontro el archivo: {pdf_path}")
        sys.exit(1)

    base = pdf_path.with_suffix("")
    txt_out = base.parent / f"{base.name}_text.txt"

    tables_extracted = 0
    with pdfplumber.open(pdf_path) as pdf, open(txt_out, "w", encoding="utf-8") as f_txt:
        total_pages = len(pdf.pages)
        print(f"Procesando {total_pages} paginas...\n")

        for page_num, page in enumerate(pdf.pages, start=1):
            # Texto plano
            text = page.extract_text() or ""
            f_txt.write(f"\n--- Pagina {page_num} ---\n{text}\n")

            # Tablas
            for table in page.extract_tables():
                if not table or len(table) < 2:
                    continue
                tables_extracted += 1
                csv_out = base.parent / f"{base.name}_table_{tables_extracted:02d}_p{page_num}.csv"
                with open(csv_out, "w", newline="", encoding="utf-8") as f_csv:
                    writer = csv.writer(f_csv)
                    for row in table:
                        writer.writerow([(c or "").strip() for c in row])
                print(f"  [tabla {tables_extracted:02d}] pagina {page_num} -> {csv_out.name}")

    print(f"\nTexto plano  -> {txt_out.name}")
    print(f"Tablas totales: {tables_extracted}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python scripts/pdf_to_data.py <ruta_al_pdf>")
        sys.exit(1)
    extract_pdf(Path(sys.argv[1]))
