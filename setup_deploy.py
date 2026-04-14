"""
setup_deploy.py — Capybaras Agency OS
======================================
Corré este script UNA vez desde la raíz del proyecto:

    cd C:\\proyectos\\ppc-manager
    python setup_deploy.py

Qué hace:
  1. Crea .gitignore
  2. Crea requirements.txt
  3. Crea .streamlit/config.toml
  4. Te pide nombre + usuario + password y genera .streamlit/secrets.toml
  5. Parchea app.py con el bloque de login (backup automático)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).parent
STREAMLIT_DIR = BASE / ".streamlit"

# ── Colores para terminal ─────────────────────────────────────────────────
G = "\033[92m"  # verde
Y = "\033[93m"  # amarillo
R = "\033[91m"  # rojo
B = "\033[94m"  # azul
E = "\033[0m"   # reset

def ok(msg):  print(f"{G}  ✓ {msg}{E}")
def warn(msg): print(f"{Y}  ⚠ {msg}{E}")
def info(msg): print(f"{B}  → {msg}{E}")
def err(msg):  print(f"{R}  ✗ {msg}{E}")

# ─────────────────────────────────────────────────────────────────────────
print(f"\n{B}{'═'*55}")
print(f"  🦫  Capybaras Agency OS — Deploy Setup")
print(f"{'═'*55}{E}\n")

# ── PASO 1: .gitignore ────────────────────────────────────────────────────
print("[ 1/5 ] Creando .gitignore...")
gitignore_path = BASE / ".gitignore"
gitignore_content = """\
# ── CRÍTICO: Secrets nunca al repo ────────────────────────────────
.streamlit/secrets.toml

# ── Python ────────────────────────────────────────────────────────
__pycache__/
*.py[cod]
*$py.class
.env
.venv
env/
venv/

# ── IDE ───────────────────────────────────────────────────────────
.vscode/
.idea/
.DS_Store
Thumbs.db

# ── Outputs temporales ────────────────────────────────────────────
*.log
.streamlit/cache/
"""

if gitignore_path.exists():
    existing = gitignore_path.read_text(encoding="utf-8")
    if ".streamlit/secrets.toml" in existing:
        warn(".gitignore ya existe y tiene secrets.toml protegido — sin cambios")
    else:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n# ── Agregado por setup_deploy.py ──────────────────\n")
            f.write(".streamlit/secrets.toml\n")
        ok(".gitignore actualizado — secrets protegido")
else:
    gitignore_path.write_text(gitignore_content, encoding="utf-8")
    ok(".gitignore creado")

# ── PASO 2: requirements.txt ─────────────────────────────────────────────
print("\n[ 2/5 ] Creando requirements.txt...")
req_path = BASE / "requirements.txt"
req_content = """\
streamlit==1.43.2
pandas==2.2.3
openpyxl==3.1.5
pdfplumber==0.11.4
streamlit-authenticator==0.3.3
bcrypt==4.2.1
Pillow==11.1.0
"""
if req_path.exists():
    warn("requirements.txt ya existe — sobrescribiendo...")
req_path.write_text(req_content, encoding="utf-8")
ok("requirements.txt creado")

# ── PASO 3: .streamlit/config.toml ───────────────────────────────────────
print("\n[ 3/5 ] Creando .streamlit/config.toml...")
STREAMLIT_DIR.mkdir(exist_ok=True)
config_path = STREAMLIT_DIR / "config.toml"
config_content = """\
[server]
runOnSave = false
fileWatcherType = "none"
maxUploadSize = 200

[browser]
gatherUsageStats = false

[theme]
base = "light"
primaryColor = "#E84000"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F5F5F5"
textColor = "#1A1A1A"
font = "sans serif"

[logger]
level = "warning"
"""
config_path.write_text(config_content, encoding="utf-8")
ok(".streamlit/config.toml creado")

# ── PASO 4: .streamlit/secrets.toml ──────────────────────────────────────
print("\n[ 4/5 ] Generando .streamlit/secrets.toml...")

# Instalar bcrypt si no está
try:
    import bcrypt
except ImportError:
    info("Instalando bcrypt...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "bcrypt", "-q"])
    import bcrypt

try:
    import streamlit_authenticator
except ImportError:
    info("Instalando streamlit-authenticator...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "streamlit-authenticator==0.3.3", "-q"
    ])

secrets_path = STREAMLIT_DIR / "secrets.toml"
secrets_example_path = STREAMLIT_DIR / "secrets.toml.example"

if secrets_path.exists():
    warn("secrets.toml ya existe — saltando creación de usuarios")
    warn("Si querés agregar usuarios, editá .streamlit/secrets.toml manualmente")
else:
    print(f"\n{Y}  Vamos a crear tu primer usuario de acceso.{E}")
    print(f"  (Podés agregar más después en .streamlit/secrets.toml)\n")

    users = {}
    while True:
        print(f"  {B}Usuario nuevo:{E}")
        username = input("    Username (sin espacios, ej: lenin): ").strip().lower()
        if not username:
            warn("Username vacío, saltando...")
            break
        name = input(f"    Nombre completo (ej: Lenin Acosta): ").strip()
        email = input(f"    Email: ").strip()
        password = input(f"    Password: ").strip()

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        users[username] = {"name": name, "email": email, "password": hashed}
        ok(f"Usuario '{username}' generado")

        another = input("\n  ¿Agregar otro usuario? (s/n): ").strip().lower()
        if another != "s":
            break

    if not users:
        warn("No se crearon usuarios. Editá secrets.toml manualmente después.")
        users["admin"] = {
            "name": "Admin",
            "email": "admin@capybaras.agency",
            "password": "$2b$12$REEMPLAZAR_CON_HASH_REAL"
        }

    import secrets as _secrets
    cookie_key = _secrets.token_hex(32)

    lines = [
        "# secrets.toml — NUNCA subir al repo\n\n",
        "[cookie]\n",
        f'key = "{cookie_key}"\n',
        "expiry_days = 30\n\n",
    ]
    for uname, udata in users.items():
        lines += [
            f"[credentials.usernames.{uname}]\n",
            f'name = "{udata["name"]}"\n',
            f'email = "{udata["email"]}"\n',
            f'password = "{udata["password"]}"\n\n',
        ]

    secrets_path.write_text("".join(lines), encoding="utf-8")
    ok(f"secrets.toml creado con {len(users)} usuario(s)")

    # Ejemplo sin datos reales para el repo
    example_lines = [
        "# secrets.toml.example — SÍ va al repo, es solo un template\n\n",
        "[cookie]\n",
        'key = "clave_secreta_larga_y_random_cambiar_esto"\n',
        "expiry_days = 30\n\n",
        "# Para generar hash de password:\n",
        "#   import bcrypt\n",
        '#   print(bcrypt.hashpw("tu_password".encode(), bcrypt.gensalt()).decode())\n\n',
        "[credentials.usernames.tu_usuario]\n",
        'name = "Tu Nombre"\n',
        'email = "tu@email.com"\n',
        'password = "$2b$12$HASH_GENERADO_CON_BCRYPT"\n',
    ]
    secrets_example_path.write_text("".join(example_lines), encoding="utf-8")
    ok("secrets.toml.example creado (para el repo)")

# ── PASO 5: Parchear app.py ───────────────────────────────────────────────
print("\n[ 5/5 ] Parcheando app.py con bloque de login...")

app_path = BASE / "app.py"
if not app_path.exists():
    err("app.py no encontrado en la ruta actual. ¿Estás en C:\\proyectos\\ppc-manager?")
    sys.exit(1)

app_content = app_path.read_text(encoding="utf-8")

LOGIN_MARKER = "# ── CAPYBARAS LOGIN BLOCK ──"

if LOGIN_MARKER in app_content:
    warn("app.py ya tiene el bloque de login — sin cambios")
else:
    # Backup
    backup_path = BASE / "app.py.backup_pre_login"
    shutil.copy(app_path, backup_path)
    ok(f"Backup creado: app.py.backup_pre_login")

    LOGIN_BLOCK = f"""\
# ── CAPYBARAS LOGIN BLOCK ─────────────────────────────────────────────────
import streamlit_authenticator as stauth

_credentials = dict(st.secrets["credentials"])
_authenticator = stauth.Authenticate(
    credentials=_credentials,
    cookie_name="capybaras_ppc",
    cookie_key=st.secrets["cookie"]["key"],
    cookie_expiry_days=int(st.secrets["cookie"].get("expiry_days", 30)),
)
_authenticator.login(location="main")

if not st.session_state.get("authentication_status"):
    if st.session_state.get("authentication_status") is False:
        st.error("Usuario o contraseña incorrectos")
    else:
        st.markdown(
            "<div style='max-width:380px;margin:6rem auto;text-align:center;'>"
            "<div style='font-size:3rem;'>🦫</div>"
            "<div style='font-size:1.5rem;font-weight:800;color:#1A1A1A;"
            "margin:0.5rem 0;'>Capybaras Agency OS</div>"
            "<div style='font-size:0.88rem;color:#888;margin-bottom:2rem;'>"
            "PPC Manager · Ingresá con tus credenciales</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    st.stop()
# ── FIN LOGIN BLOCK ───────────────────────────────────────────────────────

"""

    # Insertar ANTES del set_page_config
    new_content = app_content.replace(
        "import streamlit as st\n",
        f"import streamlit as st\n{LOGIN_BLOCK}",
        1  # solo la primera ocurrencia
    )

    # Agregar logout en sidebar (después del st.divider() del sidebar)
    LOGOUT_LINE = "    _authenticator.logout(\"🚪 Cerrar sesión\", location=\"sidebar\")\n"
    SIDEBAR_ANCHOR = "    st.divider()\n\n    st.button(\"🏠 Inicio\""

    if LOGOUT_LINE not in new_content:
        new_content = new_content.replace(
            SIDEBAR_ANCHOR,
            f"    st.divider()\n    {LOGOUT_LINE}\n    st.button(\"🏠 Inicio\""
        )

    app_path.write_text(new_content, encoding="utf-8")
    ok("app.py parcheado con login + logout en sidebar")

# ── RESUMEN FINAL ─────────────────────────────────────────────────────────
print(f"\n{G}{'═'*55}")
print(f"  ✅  Setup completo")
print(f"{'═'*55}{E}")
print(f"""
  Archivos creados/modificados:
    ✓ .gitignore
    ✓ requirements.txt
    ✓ .streamlit/config.toml
    ✓ .streamlit/secrets.toml      ← NO va al repo
    ✓ .streamlit/secrets.toml.example  ← sí va al repo
    ✓ app.py  (backup: app.py.backup_pre_login)

  Próximos pasos:
    1. Testear local:
       python -m streamlit run app.py

    2. Si funciona, hacer commit y push:
       git add .
       git commit -m "feat: deploy setup con autenticacion"
       git push

    3. Ir a https://share.streamlit.io
       → New app → conectar repo → branch main → app.py
       → Advanced settings → pegar el contenido de secrets.toml

    4. ¡App live! 🚀
""")
