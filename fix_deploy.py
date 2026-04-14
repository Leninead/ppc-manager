"""
fix_deploy.py — Corrige el error de Python 3.14 en Streamlit Cloud
===================================================================
Corré desde la raíz del proyecto:

    cd C:\\proyectos\\ppc-manager
    python fix_deploy.py
"""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent

G = "\033[92m"; Y = "\033[93m"; B = "\033[94m"; E = "\033[0m"

print(f"\n{B}{'═'*50}")
print(f"  🦫  Fix Deploy — Python 3.11")
print(f"{'═'*50}{E}\n")

# 1. Crear runtime.txt
print("[ 1/3 ] Creando runtime.txt...")
(BASE / "runtime.txt").write_text("python-3.11\n", encoding="utf-8")
print(f"{G}  ✓ runtime.txt creado{E}")

# 2. Actualizar requirements.txt (sin Pillow)
print("\n[ 2/3 ] Actualizando requirements.txt...")
(BASE / "requirements.txt").write_text(
    "streamlit==1.43.2\n"
    "pandas==2.2.3\n"
    "openpyxl==3.1.5\n"
    "pdfplumber==0.11.4\n"
    "streamlit-authenticator==0.3.3\n"
    "bcrypt==4.2.1\n",
    encoding="utf-8"
)
print(f"{G}  ✓ requirements.txt actualizado{E}")

# 3. Git commit y push
print("\n[ 3/3 ] Commiteando y pusheando...")
subprocess.run(["git", "add", "."], cwd=BASE, check=True)
subprocess.run(["git", "commit", "-m", "fix: runtime python 3.11 + remove Pillow"], cwd=BASE, check=True)
subprocess.run(["git", "push"], cwd=BASE, check=True)
print(f"{G}  ✓ Push exitoso{E}")

print(f"\n{G}{'═'*50}")
print(f"  ✅  Listo — Streamlit Cloud va a redeployar solo")
print(f"{'═'*50}{E}\n")
print(f"  Monitoreá el progreso en:")
print(f"  https://share.streamlit.io\n")
