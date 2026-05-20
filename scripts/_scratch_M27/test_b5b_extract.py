# test_b5b_extract.py — throwaway
import sys
sys.path.insert(0, r"C:\proyectos\ppc-manager")
from openpyxl import load_workbook
from modules.pages.flat_file_migrator import (
    _locate_template_headers,
    _extract_template_rows,
)

OLD = r"C:\proyectos\ppc-manager\data\account-health\flat-file-migrator\ALRBB093_p_USA_2026__1_.xlsm"
NEW = r"C:\proyectos\ppc-manager\data\account-health\flat-file-migrator\COAT__5_.xlsm"

for label, path in [("OLD/fptcustom", OLD), ("NEW/ptd", NEW)]:
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        headers = _locate_template_headers(wb)
        rows, warnings = _extract_template_rows(wb, headers)
        print(f"rows extraidas: {len(rows)}")
        print(f"warnings: {len(warnings)}")
        if rows:
            print(f"primera row keys count: {len(rows[0])}")
            print(f"primera row sample (5 keys con valor):")
            non_empty = [(k, v) for k, v in rows[0].items() if v][:5]
            for k, v in non_empty:
                print(f"  {k!r}: {v!r}")
        print(f"primeros 5 warnings:")
        for w in warnings[:5]:
            print(f"  - {w}")
    finally:
        wb.close()
