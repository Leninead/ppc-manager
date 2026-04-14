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

G = "\033[92m"; B = "\033[94m"; E = "\033[0m"

try:
    import bcrypt
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "bcrypt", "-q"])
    import bcrypt

import secrets as _secrets

print(f"\n{B}{'═'*50}")
print(f"  🦫  Generando secrets.toml")
print(f"{'═'*50}{E}\n")

print("  Creá tu usuario de acceso:\n")
username = input("    Username (ej: lenin): ").strip().lower()
name     = input("    Nombre completo (ej: Lenin Acosta): ").strip()
email    = input("    Email: ").strip()
password = input("    Password: ").strip()

hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
cookie_key = _secrets.token_hex(32)

content = f"""# secrets.toml — NUNCA subir al repo

[cookie]
key = "{cookie_key}"
expiry_days = 30

[credentials.usernames.{username}]
name = "{name}"
email = "{email}"
password = "{hashed}"
"""

secrets_path = STREAMLIT_DIR / "secrets.toml"
secrets_path.write_text(content, encoding="utf-8")

print(f"\n{G}  ✓ secrets.toml creado en .streamlit/secrets.toml{E}")
print(f"\n  Contenido para pegar en Streamlit Cloud → Secrets:\n")
print("─" * 50)
print(content)
print("─" * 50)
print("\n  Copiá todo lo de arriba y pegalo en Streamlit Cloud → Settings → Secrets\n")
