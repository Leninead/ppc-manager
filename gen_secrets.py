"""
gen_secrets.py — Genera .streamlit/secrets.toml
================================================
    cd C:\\proyectos\\ppc-manager
    python gen_secrets.py
"""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
STREAMLIT_DIR = BASE / ".streamlit"
STREAMLIT_DIR.mkdir(exist_ok=True)
SECRETS_PATH = STREAMLIT_DIR / "secrets.toml"

G = "\033[92m"; B = "\033[94m"; R = "\033[91m"; E = "\033[0m"

try:
    import bcrypt
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "bcrypt", "-q"])
    import bcrypt

import secrets as _secrets

# stdout a UTF-8: el banner usa ═ y 🦫, que crashean con cp1252 o al redirigir salida
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

print(f"\n{B}{'═'*50}")
print(f"  🦫  Generando secrets.toml")
print(f"{'═'*50}{E}\n")

# Guard: este script escribe UN solo usuario y pisa el archivo entero.
# Si ya hay un secrets.toml, abortamos ANTES de pedir nada por consola.
if SECRETS_PATH.exists():
    print(f"{R}  ✗ Ya existe .streamlit/secrets.toml — NO se sobrescribe.{E}\n")
    print("    Este script escribe un solo usuario y pisa el archivo completo.")
    print("    Si tenés usuarios cargados, los perderías.\n")
    print("    Para agregar un usuario: editá .streamlit/secrets.toml a mano.")
    print("    Para regenerarlo igual: borrá o renombrá el archivo y reintentá.\n")
    sys.exit(1)

print("  Creá tu usuario de acceso:\n")
username = input("    Username (ej: lenin): ").strip().lower()
name     = input("    Nombre completo (ej: Lenin Acosta): ").strip()
email    = input("    Email: ").strip()
password = input("    Password: ").strip()

hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
cookie_key = _secrets.token_hex(32)

content = f"""# secrets.toml — NUNCA subir al repo

[cookie]
name = "agency_os_auth"
key = "{cookie_key}"
expiry_days = 30

[credentials.usernames.{username}]
name = "{name}"
email = "{email}"
password = "{hashed}"
"""

SECRETS_PATH.write_text(content, encoding="utf-8")

print(f"\n{G}  ✓ secrets.toml creado en .streamlit/secrets.toml{E}")
print(f"\n  Contenido para pegar en Streamlit Cloud → Secrets:\n")
print("─" * 50)
print(content)
print("─" * 50)
print("\n  Copiá todo lo de arriba y pegalo en Streamlit Cloud → Settings → Secrets\n")
