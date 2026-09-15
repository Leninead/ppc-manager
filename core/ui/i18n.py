"""Translation catalog for the screens migrated to i18n so far.

The application is Spanish-first: Spanish is the source language, written by
hand in the modules, and every English string here is a translation of it.
Only a handful of surfaces have been migrated — the shell (login, sidebar,
search, footer), the navigation labels, and the Sistema screens (Cuentas
conectadas, Integraciones and Registro de solicitudes). Every other page still
carries its Spanish literals inline and is unaffected by the language toggle.

That partial coverage is deliberate and visible: `t()` falls back to Spanish
when an English translation is missing and to the key itself when the key is
unknown, so a half-migrated screen degrades into readable Spanish instead of
blank labels or a traceback.

Three rules keep this catalog usable as more screens arrive:

- One key per user-visible sentence, never per fragment. A sentence assembled
  from bare nouns at the call site cannot be translated into a language whose
  word order or agreement differs from Spanish.
- Plurals live in the catalog as `<key>_one` / `<key>_other` and are read
  through `tn()`. Appending an "s" at the call site is what produced the
  ungrammatical "2 cuentas requiere reautorizar" this catalog replaces.
- Interpolation is by name (`{provider}`, `{n}`), so a translation may reorder
  the slots freely.

The module imports Streamlit defensively and reads nothing at import time, so
it can be imported by tests and scripts with no Streamlit runtime present.
"""
from __future__ import annotations

try:  # pragma: no cover - exercised only where Streamlit is installed
    import streamlit as st
except Exception:  # pragma: no cover - import-safe outside the app
    st = None  # type: ignore[assignment]

DEFAULT_LANG = "es"
LANGS = ("es", "en")

# The sidebar radio stores its own option label, not a language code.
_RADIO_TO_LANG = {"Español": "es", "English": "en"}


# ══════════════════════════════════════════════════════════════════════════
# CATALOG
# ══════════════════════════════════════════════════════════════════════════

_ES: dict[str, str] = {
    # ── Shell: login, sidebar, footer, local mode ─────────────────────────
    "shell.local_mode.sidebar_caption": "🔓 Modo local — sin login",
    "shell.auth.secrets_missing": (
        "❌ Falta `.streamlit/secrets.toml` o sus claves `credentials`/`cookie`. "
        "Copiá `secrets.toml.example` → `secrets.toml` y completá tus "
        "credenciales, o corré en modo local con la variable de entorno "
        "`AGENCY_OS_LOCAL_MODE=1`."
    ),
    "shell.login.form_name": "🦫 Agency OS",
    "shell.login.username": "Usuario",
    "shell.login.password": "Contraseña",
    "shell.login.submit": "Ingresar",
    "shell.login.bad_credentials": "❌ Usuario o contraseña incorrectos",
    "shell.sidebar.logout": "↩ Cerrar sesión",
    "shell.sidebar.search_label": "Buscar módulo",
    "shell.sidebar.search_placeholder": "Buscar módulo — Enter",
    "shell.sidebar.search_no_results": "Ningún módulo se llama así.",
    # The two options are endonyms rendered by the widget itself, so they are
    # not catalog entries: a language names itself in every language.
    "shell.sidebar.ai_lang_label": "Idioma",
    "shell.sidebar.ai_lang_help": (
        "Cambia el idioma de la interfaz y el de las respuestas de la IA en "
        "las pestañas de análisis (STR, SQP, DataDive). Las pantallas que "
        "todavía no se migraron siguen en español."
    ),
    "shell.sidebar.parent_child_ok": "🧬 {n} parents",
    "shell.sidebar.parent_child_missing": "⚠️ Sin mapeo",
    "shell.sidebar.footer_developed_by": "Desarrollado por",
    "shell.sidebar.footer_author": "Lenin Acosta",
    "shell.sidebar.footer_agency": "Capybaras Agency · 2026",
    "shell.local_mode.banner": (
        "🔓 MODO LOCAL — login desactivado. No usar en producción."
    ),

    # ── Navigation: section titles ────────────────────────────────────────
    "nav.section.ppc": "PPC",
    "nav.section.research": "Research",
    "nav.section.account": "Account",
    "nav.section.sales_director": "Sales Director",
    "nav.section.knowledge": "Knowledge",
    "nav.section.account_health": "Account Health",
    "nav.section.supply_chain": "Supply Chain",
    "nav.section.marketplaces": "Marketplaces",
    "nav.section.sistema": "Sistema",

    # ── Navigation: page labels (routing keys keep their emoji) ───────────
    "nav.page.inicio": "Inicio",
    "nav.page.search_term_report": "Search Term Report",
    "nav.page.search_query_performance": "Search Query Performance",
    "nav.page.analisis_cruzado": "Análisis Cruzado STR vs SQP",
    "nav.page.tendencia_multisemana": "Tendencia Multi-Semana",
    "nav.page.bulk_campanas": "Bulk Campañas",
    "nav.page.business_report": "Business Report",
    "nav.page.analisis_funnel": "Análisis de Funnel",
    "nav.page.bid_optimizer": "Bid Optimizer",
    "nav.page.campaign_builder": "Campaign Builder",
    "nav.page.atom11_rules_builder": "Atom11 Rules Builder",
    "nav.page.datadive_analyzer": "DataDive Analyzer",
    "nav.page.helium10_analyzer": "Helium 10 Analyzer",
    "nav.page.sbh_recommendation": "SBH Recommendation",
    "nav.page.ppc_insights": "PPC Insights",
    "nav.page.ppc_forecast": "PPC Forecast",
    "nav.page.ppc_audit": "PPC Audit",
    "nav.page.account_pulse": "Account Pulse",
    "nav.page.reportes_atom11": "Reportes Atom 11",
    "nav.page.reportes_merchanspring": "Reportes MerchanSpring",
    "nav.page.weekly_client_report": "Weekly Client Report",
    "nav.page.listing_monitor": "Listing Monitor",
    "nav.page.listing_compliance": "Listing Compliance",
    "nav.page.gamboa_generator": "Gamboa Generator",
    "nav.page.variation_builder": "Variation Builder",
    "nav.page.monthly_forecast": "Monthly Forecast",
    "nav.page.proposal_studio": "Proposal Studio",
    "nav.page.case_study_studio": "Case Study Studio",
    "nav.page.knowledge_base": "Knowledge Base",
    "nav.page.flat_file_migrator": "Flat File Migrator",
    "nav.page.sku_progress_report": "SKU Progress Report",
    "nav.page.pricing_dashboard": "Pricing Dashboard",
    "nav.page.supply_proveedores": "Proveedores",
    "nav.page.supply_ordenes": "Órdenes de Compra",
    "nav.page.mercado_libre": "Mercado Libre",
    "nav.page.cuentas_conectadas": "Cuentas conectadas",
    "nav.page.integraciones": "Integraciones",
    "nav.page.registro_solicitudes": "Registro de solicitudes",

    # ── Cuentas conectadas (M37) ──────────────────────────────────────────
    "accounts.sop_md": """
**Qué es esta pantalla**

Es el lugar donde la agencia conecta las cuentas de sus clientes contra
cada proveedor (Mercado Libre y Amazon Ads hoy, Walmart cuando esté
disponible). Cualquier empleado puede conectar o quitar una cuenta: no
hace falta ser admin.

**Mercado Libre: autoriza el vendedor**

1. Apretá **Conectar cuenta nueva**. Se genera un link único.
2. Pasáselo al vendedor (o abrilo vos si ya estás con él): va a Mercado
   Libre, se loguea con SU usuario y aprueba a la app.
3. Cuando termina, la cuenta aparece acá con el nickname de Mercado
   Libre y el país (`MLA` = Argentina, `MLM` = México, etc.).

**Amazon Ads: autorizás vos**

1. Apretá **Autorizar con mi cuenta de Amazon** y entrá con el usuario de
   Amazon que usás para trabajar: el correo de Capybaras que los clientes
   invitaron a su cuenta.
2. Amazon nos devuelve todas las cuentas de clientes que ese usuario ve,
   en todas las regiones. Aparecen solas debajo de tu autorización, con
   país, tipo y región. No hace falta cargar nada.
3. Cada autorización vence a los 365 días. Desde 45 días antes la fila
   avisa y muestra **Reautorizar**: es volver a entrar con el mismo usuario.
4. Si a tu usuario lo invitan a un cliente nuevo, sistemas corre
   `worker discover` y la cuenta aparece sin reautorizar.

**Qué no está acá**

Las credenciales de la agencia (`client_id`, `client_secret`, API keys)
las carga un admin en **⚙️ Sistema → 🔌 Integraciones**. Sin esa
credencial cargada, este panel muestra el proveedor pero no deja
conectar cuentas nuevas.
""",
    "accounts.status_active": "Activa",
    "accounts.status_needs_reauth": "Requiere reautorizar",
    "accounts.header_title": "🔑 Cuentas conectadas",
    "accounts.header_caption": (
        "Cuentas de clientes que la agencia opera vía API en cada marketplace. "
        "Cualquier empleado puede conectar o desconectar."
    ),
    "accounts.verdict_needs_reauth_one": "1 cuenta requiere reautorizar.",
    "accounts.verdict_needs_reauth_other": "{n} cuentas requieren reautorizar.",
    "accounts.verdict_all_clear": "Nada requiere atención.",
    # Noun fragments: needed only by `accounts.verdict_detail`, which counts two
    # different things in one sentence and so cannot carry a single plural form.
    # Nothing else should concatenate them.
    "accounts.word_account_one": "cuenta",
    "accounts.word_account_other": "cuentas",
    "accounts.word_provider_one": "proveedor",
    "accounts.word_provider_other": "proveedores",
    "accounts.verdict_detail": "{accounts} {account_word} en {providers} {provider_word}.",
    "accounts.verdict_detail_coming": "{n} más próximamente.",
    "accounts.sop_expander": "📘 Cómo usar esta pantalla",
    "accounts.error_db_unavailable": (
        "El portal todavía no está conectado a la base de datos, así que no "
        "puedo mostrar las cuentas conectadas ni conectar cuentas nuevas. Es "
        "un paso de infraestructura del servidor: avisale al equipo de "
        "sistemas."
    ),
    "accounts.empty_no_providers": (
        "Todavía no hay proveedores con conexión de cuentas disponibles."
    ),
    "accounts.provider_pending_default": (
        "El proveedor está en el catálogo pero la app de la agencia todavía no "
        "fue aprobada."
    ),
    "accounts.provider_missing_credential": (
        "La credencial del sistema para {provider} todavía no está cargada. "
        "Un admin la agrega en <strong>Sistema → Integraciones</strong>."
    ),
    "accounts.provider_no_accounts": "Todavía no hay cuentas conectadas.",
    "accounts.provider_coming_soon": "Próximamente",
    "accounts.provider_count_one": "{n} cuenta",
    "accounts.provider_count_other": "{n} cuentas",
    "accounts.row_connected_by": "conectada por {user}",
    "accounts.btn_reauth": "Reautorizar",
    "accounts.btn_remove": "Quitar",
    "accounts.btn_connect_new": "Conectar cuenta nueva",
    "accounts.dialog_connect_title": "Conectar cuenta",
    "accounts.error_unknown_provider": "Proveedor desconocido.",
    "accounts.error_db_unavailable_short": "El portal no está conectado a la base.",
    "accounts.error_missing_credential": (
        "Falta la credencial del sistema para {provider}. Un admin la carga en "
        "**Sistema → Integraciones**."
    ),
    "accounts.error_missing_redirect_uri": (
        "Falta configurar `INTEGRATIONS_REDIRECT_URI` en el servidor. "
        "Avisale a sistemas."
    ),
    "accounts.error_missing_public_key": (
        "El worker todavía no publicó su clave pública. Corré `worker keys` "
        "una vez en el servidor."
    ),
    "accounts.connect_dialog_body": (
        "Abrí el link para autorizar a la app desde la cuenta de "
        "**{provider}**. No hay campos: el nombre y el marketplace los tomamos "
        "automáticamente al conectarse. Cuando termine, la cuenta aparece en "
        "el listado."
    ),
    "accounts.btn_open_consent": "Abrir {provider} para autorizar",
    "accounts.btn_close": "Cerrar",
    "accounts.dialog_remove_title": "Quitar cuenta",
    "accounts.remove_dialog_body": (
        "Vas a desconectar la cuenta de **{provider}**. La app deja de poder "
        "consultar sus datos. El registro queda para auditoría; si más "
        "adelante la querés reconectar, andá a `Conectar cuenta nueva`."
    ),
    "accounts.btn_cancel": "Cancelar",
    "accounts.btn_disconnect": "Desconectar",
    "accounts.toast_disconnected": "Cuenta desconectada.",
    # Amazon Ads: the employee authorizes, not the seller. Per-provider
    # variants resolved by `t_provider`.
    "accounts.btn_connect_new.amazon_ads": "Autorizar con mi cuenta de Amazon",
    "accounts.dialog_connect_title.amazon_ads": "Autorizar con Amazon",
    "accounts.btn_open_consent.amazon_ads": "Entrar a Amazon y autorizar",
    "accounts.connect_dialog_body.amazon_ads": (
        "Vas a autorizar a la app con **tu** usuario de Amazon: el correo de "
        "Capybaras que los clientes invitaron a su cuenta de Ads, no una "
        "cuenta personal. Amazon pide permiso para administrar campañas y para "
        "leer tu identificador de usuario. Cuando termines, en unos minutos "
        "aparecen acá todas las cuentas de clientes que ese usuario ve."
    ),
    "accounts.dialog_remove_title.amazon_ads": "Quitar autorización",
    "accounts.remove_dialog_body.amazon_ads": (
        "Vas a quitar la autorización de **{user}** en **{provider}**. Las "
        "cuentas de clientes que sólo esa autorización alcanza dejan de estar "
        "disponibles hasta que alguien vuelva a autorizar. El registro queda "
        "para auditoría."
    ),
    "accounts.status_expiring_one": "Vence en 1 día",
    "accounts.status_expiring_other": "Vence en {n} días",
    "accounts.status_expires_today": "Vence hoy",
    "accounts.status_no_authorization": "Sin autorización activa",
    "accounts.verdict_expiring_one": "1 autorización vence en menos de {days} días.",
    "accounts.verdict_expiring_other": "{n} autorizaciones vencen en menos de {days} días.",
    "accounts.authorizations_heading": "Autorizaciones",
    "accounts.accounts_heading": "Cuentas de clientes",
    "accounts.provider_no_authorizations": "Todavía nadie autorizó su cuenta de Amazon.",
    "accounts.auth_row_title": "Autorización de {user}",
    "accounts.auth_row_consented": "autorizada el {date}",
    "accounts.auth_row_reaches_one": "alcanza 1 cuenta",
    "accounts.auth_row_reaches_other": "alcanza {n} cuentas",
    "accounts.auth_no_accounts": "sin cuentas publicitarias visibles",
    "accounts.auth_discovery_errors": "Amazon no respondió en {regions}",
    "accounts.account_row_meta": "{type} · {region} · vista por {user}",
    "accounts.account_type.seller": "Seller",
    "accounts.account_type.vendor": "Vendor",
    "accounts.account_type.agency": "Agencia",

    # ── Integraciones (M38) ───────────────────────────────────────────────
    "integrations.sop_md": """**Dos niveles de credential, con radios de impacto distintos.**

- **Credencial del sistema** — una por integración. Es la API key de la agencia, o el
  `client_id` y `client_secret` de la aplicación OAuth. La carga un admin una sola vez.
  Si falla, se cae la integración para **todos** los clientes.
- **Cuenta conectada** — una por cliente. El vendedor autoriza desde su propia sesión y
  queda un permiso renovable. Si falla, se cae **ese** cliente nada más.

**Por qué no se puede ver una credential ya cargada.** Las credenciales OAuth se guardan
cifradas con una clave que sólo sirve para cerrar: la app puede guardarlas y no puede
volver a abrirlas. La mitad que descifra la tiene sólo el worker de ingesta, así que si
alguien entrara a la aplicación se llevaría un texto ilegible.

Por eso las acciones son *Agregar*, *Reemplazar* y *Quitar*, y no hay *Ver* ni *Editar*:
para cambiar una credential se carga de nuevo. La huella de seis caracteres sirve para
que dos personas confirmen que hablan de la misma clave, sin revelarla.

**Permisos.** Conectar la cuenta de un cliente lo puede hacer cualquier usuario. Cargar,
reemplazar o quitar una credential del sistema es sólo de admin: si no sos admin, esos
botones no aparecen.

**Cómo se lee la lista.** Arriba de todo, una línea dice si hay algo roto y a qué cliente
le pega. Debajo, una fila por integración agrupada en bandas: *Requiere atención* primero,
después *Se puede cargar* y *En servicio*. Una banda sin filas no se dibuja — que la de
atención no esté es el mensaje.

Cuando una cuenta de cliente deja de autorizar, la integración **no** se pinta como caída:
anda para las demás. Lo que se marca es la línea de ese cliente, colgada de su integración.

Lo que todavía no existe no ocupa una fila: va en una sola oración al pie.""",
    "integrations.band.uncertain": "SIN PODER CONFIRMAR",
    "integrations.band.attention": "REQUIERE ATENCIÓN",
    "integrations.band.loadable": "SE PUEDE CARGAR",
    "integrations.band.live": "EN SERVICIO",
    "integrations.months_short": "ene,feb,mar,abr,may,jun,jul,ago,sep,oct,nov,dic",
    "integrations.page.header": "Integraciones · sistema",
    "integrations.page.caption": (
        "Credenciales de las apps que la agencia registró en cada proveedor. "
        "Sólo admin."
    ),
    "integrations.page.admin_only_info": (
        "Esta pantalla es sólo para admin. Para conectar la cuenta de un "
        "cliente, andá a **🔑 Cuentas conectadas** en el menú Sistema."
    ),
    "integrations.sop.expander_title": "📘 Cómo usar este módulo",
    "integrations.verdict.no_db": "El portal no está conectado a la base.",
    "integrations.verdict.read_failed": "No se pudo leer el estado del portal.",
    "integrations.verdict.needs_attention_one": "{n} integración requiere atención.",
    "integrations.verdict.needs_attention_other": "{n} integraciones requieren atención.",
    "integrations.verdict.all_ok": "Nada requiere atención.",
    "integrations.verdict.summary_count_one": "{n} integración.",
    "integrations.verdict.summary_count_other": "{n} integraciones.",
    "integrations.row.btn_detail": "Detalle",
    "integrations.footer.coming_soon_label": "Próximamente:",
    "integrations.row.btn_add_credential": "Agregar credential",
    "integrations.row.btn_replace": "Reemplazar",
    "integrations.notice.no_db_warning": (
        "El portal todavía no está conectado a la base de datos, así que abajo "
        "ves el catálogo pero no se puede guardar nada. Es un paso de "
        "infraestructura del servidor: avisale al equipo de sistemas."
    ),
    "integrations.notice.none_enabled": "Todavía no hay integraciones habilitadas.",
    "integrations.notice.worker_not_run": (
        "El worker de ingesta todavía no corrió por primera vez. Se configura "
        "solo cuando lo hace —esta noche, en su corrida programada— y ahí se "
        "habilitan las integraciones que conectan cuentas de clientes."
    ),
    "integrations.dialog.detail_title": "Detalle de la integración",
    "integrations.detail.section_system_credential": "**Credencial del sistema**",
    "integrations.detail.label_fingerprint": "Huella",
    "integrations.detail.label_created_by": "Cargada por",
    "integrations.detail.label_updated_at": "Última actualización",
    "integrations.detail.label_storage": "Cómo se guarda",
    "integrations.detail.storage_encrypted": "Cifrada",
    "integrations.detail.storage_plain": "Sin cifrar",
    "integrations.detail.caption_sealed": (
        "La app la guarda cifrada y no puede volver a leerla: sólo la abre el "
        "worker."
    ),
    "integrations.detail.caption_plain": (
        "La usa el propio módulo que la consume, así que se guarda sin cifrar."
    ),
    "integrations.detail.warning_imported_copy": (
        "Esta credential se {detail}. Borrá esa copia del servidor: el portal "
        "es la única fuente y dos copias se desincronizan."
    ),
    "integrations.detail.btn_remove_credential": "Quitar credential",
    "integrations.dialog.credential_title": "Credencial del sistema",
    "integrations.credential.caption_blast_radius": (
        "Esta credential la usan todos los clientes de la integración. Si "
        "falla, la integración deja de funcionar para toda la agencia."
    ),
    "integrations.credential.btn_replace": "Reemplazar",
    "integrations.credential.btn_save": "Guardar",
    "integrations.credential.error_missing_secret": "Falta {field}.",
    "integrations.credential.error_missing_public_one": "Falta {fields}.",
    "integrations.credential.error_missing_public_other": "Faltan {fields}.",
    "integrations.credential.error_seal_failed": (
        "No se pudo cifrar la credential: {error}"
    ),
    "integrations.credential.error_no_db_save": (
        "El portal no está conectado a la base de datos, así que no se puede "
        "guardar."
    ),
    "integrations.credential.flash_saved": "Credencial de {integration} guardada.",
    "integrations.dialog.remove_title": "Quitar credential",
    "integrations.remove.warning_accounts_one": (
        "La cuenta que depende de esta credential deja de funcionar."
    ),
    "integrations.remove.warning_accounts_other": (
        "Las {n} cuentas que dependen de esta credential dejan de funcionar."
    ),
    "integrations.remove.confirm_input_label": "Escribí {name} para confirmar",
    "integrations.remove.btn_confirm": "Quitar",
    "integrations.remove.error_no_db": (
        "El portal no está conectado a la base de datos."
    ),
    "integrations.remove.flash_removed": "Credencial de {integration} quitada.",
    "integrations.status.out_of_scope": "Andando, fuera del portal",
    "integrations.status.no_sealing": "Esperando la primera corrida del worker",
    "integrations.status.no_credential": "Sin configurar",
    "integrations.status.pending_migration": "Anda con una copia vieja, sin migrar",
    "integrations.status.credential_loaded": "Credencial cargada",
    "integrations.status.ready_for_accounts": "Lista para conectar cuentas de clientes",
    "integrations.fact.sealing_tonight": "Se configura solo en la corrida de esta noche",
    "integrations.fact.pending_migration_origin": "Quedó en {origin}",
    "integrations.kind.oauth": "OAuth",
    "integrations.kind.api_key": "API key",

    # ── Registro de solicitudes ───────────────────────────────────────────
    "request_log.admin_only": (
        "Esta pantalla es sólo para admin. Si una cuenta no se actualiza, "
        "avisale a un admin o revisá **🔑 Cuentas conectadas** en el menú Sistema."
    ),
    "request_log.header_title": "Registro de solicitudes",
    "request_log.header_caption": (
        "Cada pedido de datos que el sistema hace a las cuentas conectadas, en "
        "qué estado está y qué pasó cuando falla. Sólo admin."
    ),
    "request_log.sop_expander": "📘 Cómo leer este registro",
    "request_log.sop_md": """
**Qué es esta pantalla**

Cada vez que el sistema le pide datos a una cuenta conectada (hoy, los términos
de búsqueda de Amazon Ads) queda una solicitud acá: cuándo se pidió, en qué
estado está, cuántas veces se intentó y cuántas filas guardó.

**Arriba: lo que requiere atención**

- *Falló hoy*: una actualización se quedó sin intentos. **Reintentar** crea una
  solicitud nueva; la fallida queda en el historial.
- *Primera carga fallida*: la carga inicial de una cuenta no se completó y, hasta
  que se complete, la cuenta no recibe actualizaciones diarias. **Reintentar** la
  vuelve a pedir.
- *Trabada*: el sincronizador empezó una solicitud y no la terminó. Si quedó
  soltada, se puede cancelar desde **Ver**.
- *Datos atrasados*: pasadas las 9 de la mañana, hora del perfil, la cuenta
  todavía no tiene los datos de ayer.
- *Sin señales*: el sincronizador no responde hace más de 5 minutos.
- *Requiere reautorizar* y *Vence pronto*: son de la autorización de Amazon y se
  arreglan en **🔑 Cuentas conectadas**.

**Estados de una solicitud**

- *En cola*: esperando su turno.
- *Pidiendo a Amazon*, *Esperando a Amazon* y *Guardando*: en curso. Amazon
  puede tardar hasta 3 horas en armar un reporte.
- *Reintentando*: falló un intento y el sistema vuelve a probar solo, cada vez
  más espaciado. Cuando Amazon limita los pedidos, espera sin gastar un intento.
- *Completada · día vacío*: Amazon devolvió un día sin términos y se
  conservaron los datos que ya estaban guardados.
- *Fallida*: se agotaron los intentos o se venció el plazo.
- *Cancelada*: alguien la sacó de la cola, o la cuenta dejó de estar conectada.

**Cómo leer cada fila**

- *Pedida* está en hora de Argentina. El período pedido sigue el calendario
  del perfil de Amazon: Estados Unidos, Canadá y México usan la hora del Pacífico.
- *Intentos* muestra el intento actual sobre el máximo: `3/8` es el tercero de ocho.
- *Ver* abre el detalle: los intentos uno por uno, los reportes que se pidieron
  a Amazon, el error completo y qué conviene hacer.
""",
    "request_log.error_db_unavailable": (
        "El portal todavía no está conectado a la base de datos, así que no hay "
        "solicitudes para mostrar. Es un paso de infraestructura del servidor: "
        "avisale al equipo de sistemas."
    ),
    "request_log.verdict.read_failed": (
        "No se pudo leer el estado de las solicitudes: puede haber problemas que "
        "esta pantalla no está mostrando."
    ),
    "request_log.verdict.all_clear": "Nada requiere atención.",
    "request_log.verdict.errors_one": "1 problema requiere atención.",
    "request_log.verdict.errors_other": "{n} problemas requieren atención.",
    "request_log.verdict.warnings_one": "1 aviso para revisar.",
    "request_log.verdict.warnings_other": "{n} avisos para revisar.",
    # Noun fragments: needed only by `request_log.verdict.mixed`, which counts two
    # different things in one sentence.
    "request_log.word_problem_one": "problema",
    "request_log.word_problem_other": "problemas",
    "request_log.word_warning_one": "aviso",
    "request_log.word_warning_other": "avisos",
    "request_log.verdict.mixed": (
        "{errors} {error_word} y {warnings} {warning_word} para revisar."
    ),
    "request_log.summary.window": "Últimas 24 h: {items}",
    "request_log.summary.no_requests": "sin solicitudes",
    "request_log.summary.completed_one": "1 completada",
    "request_log.summary.completed_other": "{n} completadas",
    "request_log.summary.open_one": "1 en curso",
    "request_log.summary.open_other": "{n} en curso",
    "request_log.summary.failed_one": "1 fallida",
    "request_log.summary.failed_other": "{n} fallidas",
    "request_log.summary.cancelled_one": "1 cancelada",
    "request_log.summary.cancelled_other": "{n} canceladas",
    "request_log.summary.worker_seen": "el sincronizador respondió hace {age}",
    "request_log.summary.worker_never": "el sincronizador todavía no reportó actividad",
    "request_log.summary.read_failed": "No se pudo leer el resumen de las últimas 24 h.",
    "request_log.alerts.title": "Requiere atención",
    "request_log.alerts.tag": "Alertas",
    "request_log.alerts.count_one": "1 alerta",
    "request_log.alerts.count_other": "{n} alertas",
    "request_log.alerts.read_failed": (
        "No se pudieron leer las alertas. Probá de nuevo en un minuto; si sigue, "
        "avisale al equipo de sistemas."
    ),
    "request_log.alert.failed_today": "Falló hoy",
    "request_log.alert.first_load_failed": "Primera carga fallida",
    "request_log.alert.stuck": "Trabada",
    "request_log.alert.stale_data": "Datos atrasados",
    "request_log.alert.worker_silent": "Sin señales",
    "request_log.alert.needs_reauth": "Requiere reautorizar",
    "request_log.alert.consent_expiring": "Vence pronto",
    "request_log.btn.retry": "Reintentar",
    "request_log.btn.accounts": "Cuentas conectadas",
    "request_log.btn.view": "Ver",
    "request_log.btn.retry_now": "Reintentar ahora",
    "request_log.btn.cancel_job": "Cancelar solicitud",
    "request_log.btn.close": "Cerrar",
    "request_log.btn.load_more": "Cargar más",
    "request_log.requests.title": "Solicitudes",
    "request_log.requests.tag": "Historial",
    "request_log.requests.shown_one": "1 mostrada · hora de Argentina",
    "request_log.requests.shown_other": "{n} mostradas · hora de Argentina",
    "request_log.requests.empty": "No hay solicitudes con estos filtros.",
    "request_log.requests.read_failed": (
        "No se pudo leer el registro de solicitudes. Probá de nuevo en un minuto; "
        "si sigue, avisale al equipo de sistemas."
    ),
    "request_log.filter.provider": "Proveedor",
    "request_log.filter.status": "Estado",
    "request_log.filter.account": "Cuenta",
    "request_log.filter.period": "Período",
    "request_log.filter.only_problems": "Solo con problemas",
    "request_log.filter.all_providers": "Todos",
    "request_log.filter.all_statuses": "Todos",
    "request_log.filter.all_accounts": "Todas",
    "request_log.period.day": "Últimas 24 h",
    "request_log.period.week": "Últimos 7 días",
    "request_log.period.month": "Últimos 30 días",
    "request_log.period.all": "Todo el historial",
    "request_log.column.status": "Estado",
    "request_log.column.account": "Cuenta",
    "request_log.column.request": "Solicitud",
    "request_log.column.requested": "Pedida",
    "request_log.column.duration": "Duración",
    "request_log.column.attempts": "Intentos",
    "request_log.column.rows": "Filas",
    "request_log.status.pending": "En cola",
    "request_log.status.running": "En curso",
    "request_log.status.requesting": "Pidiendo a Amazon",
    "request_log.status.waiting": "Esperando a Amazon",
    "request_log.status.saving": "Guardando",
    "request_log.status.retrying": "Reintentando",
    "request_log.status.completed": "Completada",
    "request_log.status.completed_empty_day": "Completada · día vacío",
    "request_log.status.completed_warning": "Completada · con aviso",
    "request_log.status.failed": "Fallida",
    "request_log.status.cancelled": "Cancelada",
    "request_log.kind.sp_search_terms": "Search terms",
    "request_log.kind.portfolio_names": "Nombres de portfolio",
    "request_log.kind.ai_str_analysis": "Análisis IA de search terms",
    "request_log.trigger.scheduled_daily": "Diaria",
    "request_log.trigger.scheduled_deep": "Semanal",
    "request_log.trigger.backfill": "Primera carga",
    "request_log.trigger.manual": "Manual",
    "request_log.trigger.retry": "Reintento",
    "request_log.request_title": "{trigger} · {kind}",
    "request_log.request_title_by": "{trigger} · {user}",
    "request_log.window_one": "{start} → {end} · 1 día",
    "request_log.window_other": "{start} → {end} · {n} días",
    "request_log.sub.next_attempt": "próximo intento {time}",
    "request_log.sub.reports_ready": "{saved} de {total} reportes listos",
    "request_log.sub.portfolios_one": "1 portfolio",
    "request_log.sub.portfolios_other": "{n} portfolios",
    "request_log.duration.waiting": "en espera",
    "request_log.duration.running": "{elapsed} · en curso",
    "request_log.time.yesterday": "ayer {time}",
    "request_log.time.dated": "{day} {month} {time}",
    "request_log.date.short": "{day} {month}",
    "request_log.detail.dialog_title": "Detalle de la solicitud",
    "request_log.detail.eyebrow": "{provider} · {kind} · #{job_id}",
    "request_log.detail.read_failed": (
        "No se pudo leer la solicitud. Probá de nuevo en un minuto."
    ),
    "request_log.detail.not_found": "La solicitud ya no existe.",
    "request_log.detail.account": "Cuenta",
    "request_log.detail.profile": "Perfil de Amazon",
    "request_log.detail.window": "Período pedido",
    "request_log.detail.origin": "Origen",
    "request_log.detail.created": "Creada",
    "request_log.detail.finished": "Terminó",
    "request_log.detail.gave_up": "Se dejó de intentar",
    "request_log.detail.cancelled_at": "Cancelada",
    "request_log.detail.next_attempt": "Próximo intento",
    "request_log.detail.deadline": "Plazo",
    "request_log.detail.rows": "Filas guardadas",
    "request_log.detail.attempts": "Intentos",
    "request_log.origin.scheduled_daily": "Programada, actualización diaria",
    "request_log.origin.scheduled_deep": "Programada, repaso semanal de 42 días",
    "request_log.origin.backfill": "Primera carga de la cuenta",
    "request_log.origin.manual": "Pedida a mano por {user}",
    "request_log.origin.retry": "Reintento de la #{job_id}, pedido por {user}",
    "request_log.detail.timeline": "Qué pasó",
    "request_log.detail.created_event": "Creada",
    "request_log.detail.attempt": "Intento {n}",
    "request_log.detail.rows_saved_one": "1 fila guardada.",
    "request_log.detail.rows_saved_other": "{count} filas guardadas.",
    "request_log.detail.reports": "Reportes en Amazon",
    "request_log.detail.report_window": "Tramo",
    "request_log.detail.report_id": "Report ID",
    "request_log.detail.report_status": "Estado",
    "request_log.detail.report_rows": "Filas",
    "request_log.detail.reports_empty": (
        "Todavía no se pidió ningún reporte para esta solicitud."
    ),
    "request_log.detail.reports_read_failed": (
        "No se pudieron leer los reportes de esta solicitud."
    ),
    "request_log.chunk.to_request": "Sin pedir",
    "request_log.chunk.requested": "Pedido",
    "request_log.chunk.saving": "Guardando",
    "request_log.chunk.saved": "Guardado",
    "request_log.chunk.failed": "Falló",
    "request_log.detail.error": "Error",
    "request_log.detail.warning": "Aviso",
    "request_log.detail.retry_caption": (
        "Reintentar crea una solicitud nueva y esta queda en el historial."
    ),
    "request_log.detail.cancel_caption": (
        "Cancelar la saca de la cola; lo que ya se guardó queda guardado."
    ),
    "request_log.detail.cancel_abandoned_caption": (
        "El sincronizador soltó esta solicitud a mitad de camino. Cancelarla la "
        "cierra; lo que ya se guardó queda guardado."
    ),
    "request_log.flash.retried": (
        "Se creó la solicitud #{new_job_id} para reintentar la #{job_id}."
    ),
    "request_log.flash.not_retryable": (
        "La solicitud #{job_id} no se puede reintentar: sólo se reintentan las "
        "fallidas o canceladas de cuentas que siguen conectadas."
    ),
    "request_log.flash.cancelled": "Solicitud #{job_id} cancelada.",
    "request_log.flash.not_cancellable": (
        "La solicitud #{job_id} ya no estaba en cola ni trabada, así que no se canceló."
    ),
    "request_log.hint.needs_reauth": (
        "La autorización de Amazon dejó de funcionar. Reautorizá en Sistema → "
        "Cuentas conectadas y después reintentá."
    ),
    "request_log.hint.connection_unavailable": (
        "La autorización que usa esta cuenta no está activa. Revisala en Sistema "
        "→ Cuentas conectadas y después reintentá."
    ),
    "request_log.hint.access_denied": (
        "El usuario de Amazon que autorizó no tiene permiso sobre esta cuenta. "
        "Pedile al cliente que lo vuelva a invitar, o autorizá con otro usuario."
    ),
    "request_log.hint.report_failed": (
        "Es una falla del lado de Amazon y reintentar suele alcanzar. Si no, la "
        "actualización diaria de mañana vuelve a pedir estos días y el domingo se "
        "piden los últimos 42."
    ),
    "request_log.hint.report_timed_out": (
        "Amazon tardó más de tres horas en armar el reporte. Reintentar suele "
        "alcanzar; si se repite, es carga del lado de Amazon."
    ),
    "request_log.hint.duplicate": (
        "Amazon respondió que ya estaba armando este mismo reporte, pero no dijo "
        "cuál. Esperá unos minutos y reintentá."
    ),
    "request_log.hint.deadline": (
        "Se venció el plazo antes de completarse. La próxima actualización "
        "programada vuelve a pedir estos días; si los necesitás antes, reintentá."
    ),
    "request_log.hint.throttled": (
        "Amazon limitó la cantidad de pedidos. El sistema espera solo sin gastar "
        "intentos; reintentá más tarde si hace falta."
    ),
    "request_log.hint.invalid_rows": (
        "El reporte vino con datos que no pasan la validación. Reintentar pide uno "
        "nuevo; si se repite, pasale este error al equipo de sistemas."
    ),
    "request_log.hint.invalid_job": (
        "La solicitud quedó mal armada y no se puede ejecutar. Pasale este error "
        "al equipo de sistemas."
    ),
    "request_log.hint.save_crashed": (
        "El sincronizador se cortó dos veces guardando este tramo, casi siempre por "
        "un reporte demasiado grande. Pasale este error al equipo de sistemas antes "
        "de reintentar."
    ),
    "request_log.hint.network": (
        "Hubo un problema de red hablando con Amazon o con la base de datos. "
        "Reintentar suele alcanzar."
    ),
    "request_log.hint.amazon_api": (
        "Amazon rechazó el pedido. Reintentar suele alcanzar; si se repite, pasale "
        "este error al equipo de sistemas."
    ),
    "request_log.hint.default": (
        "Reintentar suele alcanzar. Si vuelve a fallar, pasale este error al "
        "equipo de sistemas."
    ),
}


_EN: dict[str, str] = {
    # ── Shell: login, sidebar, footer, local mode ─────────────────────────
    "shell.local_mode.sidebar_caption": "🔓 Local mode — no login",
    "shell.auth.secrets_missing": (
        "❌ Missing `.streamlit/secrets.toml` or its `credentials`/`cookie` "
        "keys. Copy `secrets.toml.example` → `secrets.toml` and fill in your "
        "credentials, or run in local mode with the environment variable "
        "`AGENCY_OS_LOCAL_MODE=1`."
    ),
    "shell.login.form_name": "🦫 Agency OS",
    "shell.login.username": "Username",
    "shell.login.password": "Password",
    "shell.login.submit": "Sign in",
    "shell.login.bad_credentials": "❌ Incorrect username or password",
    "shell.sidebar.logout": "↩ Sign out",
    "shell.sidebar.search_label": "Search modules",
    "shell.sidebar.search_placeholder": "Search modules — Enter",
    "shell.sidebar.search_no_results": "No module by that name.",
    "shell.sidebar.ai_lang_label": "Language",
    "shell.sidebar.ai_lang_help": (
        "Switches the interface language and the language the AI answers in "
        "on the analysis tabs (STR, SQP, DataDive). Screens not migrated yet "
        "stay in Spanish."
    ),
    "shell.sidebar.parent_child_ok": "🧬 {n} parents",
    "shell.sidebar.parent_child_missing": "⚠️ No mapping",
    "shell.sidebar.footer_developed_by": "Developed by",
    "shell.sidebar.footer_author": "Lenin Acosta",
    "shell.sidebar.footer_agency": "Capybaras Agency · 2026",
    "shell.local_mode.banner": (
        "🔓 LOCAL MODE — login disabled. Not for production use."
    ),

    # ── Navigation: section titles ────────────────────────────────────────
    "nav.section.ppc": "PPC",
    "nav.section.research": "Research",
    "nav.section.account": "Account",
    "nav.section.sales_director": "Sales Director",
    "nav.section.knowledge": "Knowledge",
    "nav.section.account_health": "Account Health",
    "nav.section.supply_chain": "Supply Chain",
    "nav.section.marketplaces": "Marketplaces",
    "nav.section.sistema": "System",

    # ── Navigation: page labels (routing keys keep their emoji) ───────────
    "nav.page.inicio": "Home",
    "nav.page.search_term_report": "Search Term Report",
    "nav.page.search_query_performance": "Search Query Performance",
    "nav.page.analisis_cruzado": "STR vs SQP Cross-Analysis",
    "nav.page.tendencia_multisemana": "Multi-Week Trend",
    "nav.page.bulk_campanas": "Bulk Campaigns",
    "nav.page.business_report": "Business Report",
    "nav.page.analisis_funnel": "Funnel Analysis",
    "nav.page.bid_optimizer": "Bid Optimizer",
    "nav.page.campaign_builder": "Campaign Builder",
    "nav.page.atom11_rules_builder": "Atom11 Rules Builder",
    "nav.page.datadive_analyzer": "DataDive Analyzer",
    "nav.page.helium10_analyzer": "Helium 10 Analyzer",
    "nav.page.sbh_recommendation": "SBH Recommendation",
    "nav.page.ppc_insights": "PPC Insights",
    "nav.page.ppc_forecast": "PPC Forecast",
    "nav.page.ppc_audit": "PPC Audit",
    "nav.page.account_pulse": "Account Pulse",
    "nav.page.reportes_atom11": "Atom 11 Reports",
    "nav.page.reportes_merchanspring": "MerchanSpring Reports",
    "nav.page.weekly_client_report": "Weekly Client Report",
    "nav.page.listing_monitor": "Listing Monitor",
    "nav.page.listing_compliance": "Listing Compliance",
    "nav.page.gamboa_generator": "Gamboa Generator",
    "nav.page.variation_builder": "Variation Builder",
    "nav.page.monthly_forecast": "Monthly Forecast",
    "nav.page.proposal_studio": "Proposal Studio",
    "nav.page.case_study_studio": "Case Study Studio",
    "nav.page.knowledge_base": "Knowledge Base",
    "nav.page.flat_file_migrator": "Flat File Migrator",
    "nav.page.sku_progress_report": "SKU Progress Report",
    "nav.page.pricing_dashboard": "Pricing Dashboard",
    "nav.page.supply_proveedores": "Suppliers",
    "nav.page.supply_ordenes": "Purchase Orders",
    "nav.page.mercado_libre": "Mercado Libre",
    "nav.page.cuentas_conectadas": "Connected Accounts",
    "nav.page.integraciones": "Integrations",
    "nav.page.registro_solicitudes": "Request log",

    # ── Cuentas conectadas (M37) ──────────────────────────────────────────
    "accounts.sop_md": """
**What this screen is**

This is where the agency connects its clients' accounts to each provider
(Mercado Libre and Amazon Ads today; Walmart once it's available). Any
employee can connect or remove an account — you don't need to be an
admin.

**Mercado Libre: the seller authorizes**

1. Click **Connect a new account**. A one-time link is generated.
2. Hand it to the seller (or open it yourself if you're with them): it
   takes them to Mercado Libre, where they log in with THEIR user and
   approve the app.
3. Once they're done, the account shows up here with its Mercado Libre
   nickname and country (`MLA` = Argentina, `MLM` = Mexico, etc.).

**Amazon Ads: you authorize**

1. Click **Authorize with my Amazon account** and sign in with the Amazon
   user you work with: the Capybaras email the clients invited into their
   account.
2. Amazon returns every client account that user can see, in every
   region. They appear on their own under your authorization, with
   country, type and region. Nothing to type.
3. Each authorization expires after 365 days. From 45 days before, the
   row warns and shows **Reauthorize**: just sign in again with the same user.
4. If your user gets invited into a new client, systems runs
   `worker discover` and the account appears without reauthorizing.

**What's not here**

The agency's own credentials (`client_id`, `client_secret`, API keys)
are loaded by an admin under **⚙️ System → 🔌 Integrations**. Without
that credential loaded, this panel shows the provider but won't let you
connect new accounts.
""",
    "accounts.status_active": "Active",
    "accounts.status_needs_reauth": "Needs reauthorization",
    "accounts.header_title": "🔑 Connected accounts",
    "accounts.header_caption": (
        "Client accounts the agency operates through each marketplace's API. "
        "Any employee can connect or disconnect one."
    ),
    "accounts.verdict_needs_reauth_one": "1 account needs to be reauthorized.",
    "accounts.verdict_needs_reauth_other": "{n} accounts need to be reauthorized.",
    "accounts.verdict_all_clear": "Nothing needs your attention.",
    "accounts.word_account_one": "account",
    "accounts.word_account_other": "accounts",
    "accounts.word_provider_one": "provider",
    "accounts.word_provider_other": "providers",
    "accounts.verdict_detail": "{accounts} {account_word} across {providers} {provider_word}.",
    "accounts.verdict_detail_coming": "{n} more coming soon.",
    "accounts.sop_expander": "📘 How to use this screen",
    "accounts.error_db_unavailable": (
        "The portal isn't connected to the database yet, so it can't list "
        "connected accounts or connect new ones. That's a server-side setup "
        "step — let the systems team know."
    ),
    "accounts.empty_no_providers": "No provider supports account connections yet.",
    "accounts.provider_pending_default": (
        "This provider is in the catalog, but the agency's app hasn't been "
        "approved yet."
    ),
    "accounts.provider_missing_credential": (
        "The system credential for {provider} hasn't been loaded yet. An admin "
        "adds it under <strong>System → Integrations</strong>."
    ),
    "accounts.provider_no_accounts": "No accounts connected yet.",
    "accounts.provider_coming_soon": "Coming soon",
    "accounts.provider_count_one": "{n} account",
    "accounts.provider_count_other": "{n} accounts",
    "accounts.row_connected_by": "connected by {user}",
    "accounts.btn_reauth": "Reauthorize",
    "accounts.btn_remove": "Remove",
    "accounts.btn_connect_new": "Connect a new account",
    "accounts.dialog_connect_title": "Connect account",
    "accounts.error_unknown_provider": "Unknown provider.",
    "accounts.error_db_unavailable_short": (
        "The portal isn't connected to the database."
    ),
    "accounts.error_missing_credential": (
        "The system credential for {provider} is missing. An admin loads it "
        "under **System → Integrations**."
    ),
    "accounts.error_missing_redirect_uri": (
        "`INTEGRATIONS_REDIRECT_URI` isn't configured on the server. Let the "
        "systems team know."
    ),
    "accounts.error_missing_public_key": (
        "The worker hasn't published its public key yet. Run `worker keys` "
        "once on the server."
    ),
    "accounts.connect_dialog_body": (
        "Open the link to authorize the app from the **{provider}** account. "
        "There are no fields to fill in — we pick up the name and marketplace "
        "automatically once it connects. When it's done, the account shows up "
        "in the list."
    ),
    "accounts.btn_open_consent": "Open {provider} to authorize",
    "accounts.btn_close": "Close",
    "accounts.dialog_remove_title": "Remove account",
    "accounts.remove_dialog_body": (
        "You're about to disconnect the **{provider}** account. The app will "
        "no longer be able to read its data. The record is kept for auditing; "
        "if you want to reconnect it later, use `Connect a new account`."
    ),
    "accounts.btn_cancel": "Cancel",
    "accounts.btn_disconnect": "Disconnect",
    "accounts.toast_disconnected": "Account disconnected.",
    "accounts.btn_connect_new.amazon_ads": "Authorize with my Amazon account",
    "accounts.dialog_connect_title.amazon_ads": "Authorize with Amazon",
    "accounts.btn_open_consent.amazon_ads": "Sign in to Amazon and authorize",
    "accounts.connect_dialog_body.amazon_ads": (
        "You're about to authorize the app with **your** Amazon user: the "
        "Capybaras email the clients invited into their Ads account, not a "
        "personal account. Amazon asks for permission to manage campaigns and "
        "to read your user id. Once you're done, every client account that "
        "user can see shows up here within a few minutes."
    ),
    "accounts.dialog_remove_title.amazon_ads": "Remove authorization",
    "accounts.remove_dialog_body.amazon_ads": (
        "You're about to remove **{user}**'s authorization on **{provider}**. "
        "Client accounts reached only through that authorization become "
        "unavailable until someone authorizes again. The record is kept for "
        "auditing."
    ),
    "accounts.status_expiring_one": "Expires in 1 day",
    "accounts.status_expiring_other": "Expires in {n} days",
    "accounts.status_expires_today": "Expires today",
    "accounts.status_no_authorization": "No active authorization",
    "accounts.verdict_expiring_one": "1 authorization expires in less than {days} days.",
    "accounts.verdict_expiring_other": "{n} authorizations expire in less than {days} days.",
    "accounts.authorizations_heading": "Authorizations",
    "accounts.accounts_heading": "Client accounts",
    "accounts.provider_no_authorizations": "Nobody has authorized their Amazon account yet.",
    "accounts.auth_row_title": "Authorization by {user}",
    "accounts.auth_row_consented": "authorized on {date}",
    "accounts.auth_row_reaches_one": "reaches 1 account",
    "accounts.auth_row_reaches_other": "reaches {n} accounts",
    "accounts.auth_no_accounts": "no advertising accounts visible",
    "accounts.auth_discovery_errors": "Amazon did not answer in {regions}",
    "accounts.account_row_meta": "{type} · {region} · seen by {user}",
    "accounts.account_type.seller": "Seller",
    "accounts.account_type.vendor": "Vendor",
    "accounts.account_type.agency": "Agency",

    # ── Integraciones (M38) ───────────────────────────────────────────────
    "integrations.sop_md": """**Two levels of credential, with different blast radii.**

- **System credential** — one per integration. It is the agency's API key, or the
  `client_id` and `client_secret` of the OAuth application. An admin loads it once.
  If it fails, the integration goes down for **every** client.
- **Connected account** — one per client. The seller authorizes from their own session and
  a renewable grant is left behind. If it fails, only **that** client goes down.

**Why a credential that is already loaded cannot be viewed.** OAuth credentials are stored
encrypted with a key that can only close: the app can save them and cannot open them again.
Only the ingest worker holds the half that decrypts, so if someone got into the application
they would walk away with unreadable text.

That is why the actions are *Add*, *Replace* and *Remove*, and there is no *View* or *Edit*:
to change a credential you load it again. The six-character fingerprint is there so two
people can confirm they are talking about the same key, without revealing it.

**Permissions.** Connecting a client's account can be done by any user. Loading, replacing
or removing a system credential is admin-only: if you are not an admin, those buttons do
not appear.

**How to read the list.** At the very top, one line says whether anything is broken and
which client it hits. Below that, one row per integration grouped into bands: *Needs
attention* first, then *Ready to add* and *In service*. A band with no rows is not drawn —
the attention band being absent is the message.

When a client account stops authorizing, the integration is **not** painted as down: it
works for the others. What gets flagged is that client's line, hanging off its integration.

What does not exist yet does not take up a row: it goes in a single sentence at the foot.""",
    "integrations.band.uncertain": "UNABLE TO CONFIRM",
    "integrations.band.attention": "NEEDS ATTENTION",
    "integrations.band.loadable": "READY TO ADD",
    "integrations.band.live": "IN SERVICE",
    "integrations.months_short": "Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec",
    "integrations.page.header": "Integrations · system",
    "integrations.page.caption": (
        "Credentials for the apps the agency registered with each provider. "
        "Admin only."
    ),
    "integrations.page.admin_only_info": (
        "This screen is admin-only. To connect a client's account, go to "
        "**🔑 Connected accounts** in the System menu."
    ),
    "integrations.sop.expander_title": "📘 How to use this module",
    "integrations.verdict.no_db": "The portal is not connected to the database.",
    "integrations.verdict.read_failed": "The portal's status could not be read.",
    "integrations.verdict.needs_attention_one": "{n} integration needs attention.",
    "integrations.verdict.needs_attention_other": "{n} integrations need attention.",
    "integrations.verdict.all_ok": "Nothing needs attention.",
    "integrations.verdict.summary_count_one": "{n} integration.",
    "integrations.verdict.summary_count_other": "{n} integrations.",
    "integrations.row.btn_detail": "Details",
    "integrations.footer.coming_soon_label": "Coming soon:",
    "integrations.row.btn_add_credential": "Add credential",
    "integrations.row.btn_replace": "Replace",
    "integrations.notice.no_db_warning": (
        "The portal is not connected to the database yet, so you can see the "
        "catalog below but nothing can be saved. It's a server infrastructure "
        "step: let the systems team know."
    ),
    "integrations.notice.none_enabled": "No integrations are enabled yet.",
    "integrations.notice.worker_not_run": (
        "The ingest worker hasn't run for the first time yet. It sets itself "
        "up when it does — tonight, on its scheduled run — and that's when the "
        "integrations that connect client accounts become available."
    ),
    "integrations.dialog.detail_title": "Integration detail",
    "integrations.detail.section_system_credential": "**System credential**",
    "integrations.detail.label_fingerprint": "Fingerprint",
    "integrations.detail.label_created_by": "Loaded by",
    "integrations.detail.label_updated_at": "Last updated",
    "integrations.detail.label_storage": "How it's stored",
    "integrations.detail.storage_encrypted": "Encrypted",
    "integrations.detail.storage_plain": "Unencrypted",
    "integrations.detail.caption_sealed": (
        "The app stores it encrypted and cannot read it back: only the worker "
        "can open it."
    ),
    "integrations.detail.caption_plain": (
        "The module that consumes it reads it directly, so it's stored "
        "unencrypted."
    ),
    "integrations.detail.warning_imported_copy": (
        "This credential was {detail}. Delete that copy from the server: the "
        "portal is the single source and two copies drift apart."
    ),
    "integrations.detail.btn_remove_credential": "Remove credential",
    "integrations.dialog.credential_title": "System credential",
    "integrations.credential.caption_blast_radius": (
        "Every client of this integration uses this credential. If it fails, "
        "the integration stops working for the whole agency."
    ),
    "integrations.credential.btn_replace": "Replace",
    "integrations.credential.btn_save": "Save",
    "integrations.credential.error_missing_secret": "Missing {field}.",
    "integrations.credential.error_missing_public_one": "Missing {fields}.",
    "integrations.credential.error_missing_public_other": "Missing {fields}.",
    "integrations.credential.error_seal_failed": (
        "The credential could not be encrypted: {error}"
    ),
    "integrations.credential.error_no_db_save": (
        "The portal is not connected to the database, so nothing can be saved."
    ),
    "integrations.credential.flash_saved": "{integration} credential saved.",
    "integrations.dialog.remove_title": "Remove credential",
    "integrations.remove.warning_accounts_one": (
        "The account that depends on this credential stops working."
    ),
    "integrations.remove.warning_accounts_other": (
        "The {n} accounts that depend on this credential stop working."
    ),
    "integrations.remove.confirm_input_label": "Type {name} to confirm",
    "integrations.remove.btn_confirm": "Remove",
    "integrations.remove.error_no_db": (
        "The portal is not connected to the database."
    ),
    "integrations.remove.flash_removed": "{integration} credential removed.",
    "integrations.status.out_of_scope": "Working, outside the portal",
    "integrations.status.no_sealing": "Waiting for the worker's first run",
    "integrations.status.no_credential": "Not set up",
    "integrations.status.pending_migration": "Running on an old copy, not migrated",
    "integrations.status.credential_loaded": "Credential loaded",
    "integrations.status.ready_for_accounts": "Ready to connect client accounts",
    "integrations.fact.sealing_tonight": "Sets itself up in tonight's run",
    "integrations.fact.pending_migration_origin": "Still in {origin}",
    "integrations.kind.oauth": "OAuth",
    "integrations.kind.api_key": "API key",

    # ── Registro de solicitudes ───────────────────────────────────────────
    "request_log.admin_only": (
        "This screen is admin-only. If an account is not updating, let an admin "
        "know or check **🔑 Connected accounts** in the System menu."
    ),
    "request_log.header_title": "Request log",
    "request_log.header_caption": (
        "Every data request the system makes to the connected accounts, where it "
        "stands and what happened when it fails. Admin only."
    ),
    "request_log.sop_expander": "📘 How to read this log",
    "request_log.sop_md": """
**What this screen is**

Every time the system asks a connected account for data (today, the Amazon Ads
search terms) a request lands here: when it was asked for, where it stands, how
many times it was tried and how many rows it saved.

**At the top: what needs attention**

- *Failed today*: an update ran out of attempts. **Retry** creates a new
  request; the failed one stays in the history.
- *First load failed*: an account's initial load did not complete and, until it
  does, the account gets no daily updates. **Retry** asks for it again.
- *Stuck*: the sync worker started a request and never finished it. If the
  worker let go of it, it can be cancelled from **View**.
- *Data behind*: past 9 in the morning, profile time, the account still lacks
  yesterday's data.
- *No signal*: the sync worker has not answered for more than 5 minutes.
- *Needs reauthorization* and *Expiring soon*: they belong to the Amazon
  authorization and are fixed under **🔑 Connected accounts**.

**Request states**

- *Queued*: waiting for its turn.
- *Asking Amazon*, *Waiting for Amazon* and *Saving*: in progress. Amazon can
  take up to 3 hours to build a report.
- *Retrying*: an attempt failed and the system tries again on its own, spacing
  the attempts out. When Amazon throttles requests it waits without spending an
  attempt.
- *Completed · empty day*: Amazon returned a day with no search terms and the
  data already saved was kept.
- *Failed*: attempts ran out or the deadline passed.
- *Cancelled*: someone took it off the queue, or the account stopped being
  connected.

**How to read each row**

- *Requested* is in Argentina time. The requested period follows the Amazon
  profile's calendar: the United States, Canada and Mexico use Pacific time.
- *Attempts* shows the current attempt over the maximum: `3/8` is the third of eight.
- *View* opens the detail: each attempt, the reports asked from Amazon, the full
  error and what to do about it.
""",
    "request_log.error_db_unavailable": (
        "The portal is not connected to the database yet, so there are no "
        "requests to show. It's a server infrastructure step: let the systems "
        "team know."
    ),
    "request_log.verdict.read_failed": (
        "The request status could not be read: there may be problems this screen "
        "is not showing."
    ),
    "request_log.verdict.all_clear": "Nothing needs attention.",
    "request_log.verdict.errors_one": "1 problem needs attention.",
    "request_log.verdict.errors_other": "{n} problems need attention.",
    "request_log.verdict.warnings_one": "1 warning to review.",
    "request_log.verdict.warnings_other": "{n} warnings to review.",
    "request_log.word_problem_one": "problem",
    "request_log.word_problem_other": "problems",
    "request_log.word_warning_one": "warning",
    "request_log.word_warning_other": "warnings",
    "request_log.verdict.mixed": (
        "{errors} {error_word} and {warnings} {warning_word} to review."
    ),
    "request_log.summary.window": "Last 24 h: {items}",
    "request_log.summary.no_requests": "no requests",
    "request_log.summary.completed_one": "1 completed",
    "request_log.summary.completed_other": "{n} completed",
    "request_log.summary.open_one": "1 in progress",
    "request_log.summary.open_other": "{n} in progress",
    "request_log.summary.failed_one": "1 failed",
    "request_log.summary.failed_other": "{n} failed",
    "request_log.summary.cancelled_one": "1 cancelled",
    "request_log.summary.cancelled_other": "{n} cancelled",
    "request_log.summary.worker_seen": "the sync worker answered {age} ago",
    "request_log.summary.worker_never": "the sync worker has not reported yet",
    "request_log.summary.read_failed": "The last 24 h summary could not be read.",
    "request_log.alerts.title": "Needs attention",
    "request_log.alerts.tag": "Alerts",
    "request_log.alerts.count_one": "1 alert",
    "request_log.alerts.count_other": "{n} alerts",
    "request_log.alerts.read_failed": (
        "The alerts could not be read. Try again in a minute; if it persists, let "
        "the systems team know."
    ),
    "request_log.alert.failed_today": "Failed today",
    "request_log.alert.first_load_failed": "First load failed",
    "request_log.alert.stuck": "Stuck",
    "request_log.alert.stale_data": "Data behind",
    "request_log.alert.worker_silent": "No signal",
    "request_log.alert.needs_reauth": "Needs reauthorization",
    "request_log.alert.consent_expiring": "Expiring soon",
    "request_log.btn.retry": "Retry",
    "request_log.btn.accounts": "Connected accounts",
    "request_log.btn.view": "View",
    "request_log.btn.retry_now": "Retry now",
    "request_log.btn.cancel_job": "Cancel request",
    "request_log.btn.close": "Close",
    "request_log.btn.load_more": "Load more",
    "request_log.requests.title": "Requests",
    "request_log.requests.tag": "History",
    "request_log.requests.shown_one": "1 shown · Argentina time",
    "request_log.requests.shown_other": "{n} shown · Argentina time",
    "request_log.requests.empty": "No requests match these filters.",
    "request_log.requests.read_failed": (
        "The request log could not be read. Try again in a minute; if it persists, "
        "let the systems team know."
    ),
    "request_log.filter.provider": "Provider",
    "request_log.filter.status": "Status",
    "request_log.filter.account": "Account",
    "request_log.filter.period": "Period",
    "request_log.filter.only_problems": "Only with problems",
    "request_log.filter.all_providers": "All",
    "request_log.filter.all_statuses": "All",
    "request_log.filter.all_accounts": "All",
    "request_log.period.day": "Last 24 h",
    "request_log.period.week": "Last 7 days",
    "request_log.period.month": "Last 30 days",
    "request_log.period.all": "Full history",
    "request_log.column.status": "Status",
    "request_log.column.account": "Account",
    "request_log.column.request": "Request",
    "request_log.column.requested": "Requested",
    "request_log.column.duration": "Duration",
    "request_log.column.attempts": "Attempts",
    "request_log.column.rows": "Rows",
    "request_log.status.pending": "Queued",
    "request_log.status.running": "In progress",
    "request_log.status.requesting": "Asking Amazon",
    "request_log.status.waiting": "Waiting for Amazon",
    "request_log.status.saving": "Saving",
    "request_log.status.retrying": "Retrying",
    "request_log.status.completed": "Completed",
    "request_log.status.completed_empty_day": "Completed · empty day",
    "request_log.status.completed_warning": "Completed · with a warning",
    "request_log.status.failed": "Failed",
    "request_log.status.cancelled": "Cancelled",
    "request_log.kind.sp_search_terms": "Search terms",
    "request_log.kind.portfolio_names": "Portfolio names",
    "request_log.kind.ai_str_analysis": "Search terms AI analysis",
    "request_log.trigger.scheduled_daily": "Daily",
    "request_log.trigger.scheduled_deep": "Weekly",
    "request_log.trigger.backfill": "First load",
    "request_log.trigger.manual": "Manual",
    "request_log.trigger.retry": "Retry",
    "request_log.request_title": "{trigger} · {kind}",
    "request_log.request_title_by": "{trigger} · {user}",
    "request_log.window_one": "{start} → {end} · 1 day",
    "request_log.window_other": "{start} → {end} · {n} days",
    "request_log.sub.next_attempt": "next attempt {time}",
    "request_log.sub.reports_ready": "{saved} of {total} reports ready",
    "request_log.sub.portfolios_one": "1 portfolio",
    "request_log.sub.portfolios_other": "{n} portfolios",
    "request_log.duration.waiting": "waiting",
    "request_log.duration.running": "{elapsed} · running",
    "request_log.time.yesterday": "yesterday {time}",
    "request_log.time.dated": "{month} {day} {time}",
    "request_log.date.short": "{month} {day}",
    "request_log.detail.dialog_title": "Request detail",
    "request_log.detail.eyebrow": "{provider} · {kind} · #{job_id}",
    "request_log.detail.read_failed": (
        "The request could not be read. Try again in a minute."
    ),
    "request_log.detail.not_found": "The request no longer exists.",
    "request_log.detail.account": "Account",
    "request_log.detail.profile": "Amazon profile",
    "request_log.detail.window": "Requested period",
    "request_log.detail.origin": "Origin",
    "request_log.detail.created": "Created",
    "request_log.detail.finished": "Finished",
    "request_log.detail.gave_up": "Gave up",
    "request_log.detail.cancelled_at": "Cancelled",
    "request_log.detail.next_attempt": "Next attempt",
    "request_log.detail.deadline": "Deadline",
    "request_log.detail.rows": "Rows saved",
    "request_log.detail.attempts": "Attempts",
    "request_log.origin.scheduled_daily": "Scheduled, daily update",
    "request_log.origin.scheduled_deep": "Scheduled, weekly 42-day pass",
    "request_log.origin.backfill": "The account's first load",
    "request_log.origin.manual": "Requested by hand by {user}",
    "request_log.origin.retry": "Retry of #{job_id}, requested by {user}",
    "request_log.detail.timeline": "What happened",
    "request_log.detail.created_event": "Created",
    "request_log.detail.attempt": "Attempt {n}",
    "request_log.detail.rows_saved_one": "1 row saved.",
    "request_log.detail.rows_saved_other": "{count} rows saved.",
    "request_log.detail.reports": "Reports on Amazon",
    "request_log.detail.report_window": "Chunk",
    "request_log.detail.report_id": "Report ID",
    "request_log.detail.report_status": "Status",
    "request_log.detail.report_rows": "Rows",
    "request_log.detail.reports_empty": "No report has been requested for this request yet.",
    "request_log.detail.reports_read_failed": (
        "The reports of this request could not be read."
    ),
    "request_log.chunk.to_request": "Not requested",
    "request_log.chunk.requested": "Requested",
    "request_log.chunk.saving": "Saving",
    "request_log.chunk.saved": "Saved",
    "request_log.chunk.failed": "Failed",
    "request_log.detail.error": "Error",
    "request_log.detail.warning": "Warning",
    "request_log.detail.retry_caption": (
        "Retrying creates a new request and this one stays in the history."
    ),
    "request_log.detail.cancel_caption": (
        "Cancelling takes it off the queue; whatever was already saved stays saved."
    ),
    "request_log.detail.cancel_abandoned_caption": (
        "The sync worker let go of this request halfway. Cancelling closes it; "
        "whatever was already saved stays saved."
    ),
    "request_log.flash.retried": (
        "Request #{new_job_id} was created to retry #{job_id}."
    ),
    "request_log.flash.not_retryable": (
        "Request #{job_id} cannot be retried: only failed or cancelled requests "
        "of accounts that are still connected can."
    ),
    "request_log.flash.cancelled": "Request #{job_id} cancelled.",
    "request_log.flash.not_cancellable": (
        "Request #{job_id} was no longer queued or stalled, so it was not cancelled."
    ),
    "request_log.hint.needs_reauth": (
        "The Amazon authorization stopped working. Reauthorize under System → "
        "Connected accounts and then retry."
    ),
    "request_log.hint.connection_unavailable": (
        "The authorization this account uses is not active. Check it under "
        "System → Connected accounts and then retry."
    ),
    "request_log.hint.access_denied": (
        "The Amazon user who authorized has no permission on this account. Ask "
        "the client to invite them again, or authorize with another user."
    ),
    "request_log.hint.report_failed": (
        "It is a failure on Amazon's side and retrying is usually enough. If not, "
        "tomorrow's daily update asks for these days again and on Sunday the last "
        "42 are requested."
    ),
    "request_log.hint.report_timed_out": (
        "Amazon took more than three hours to build the report. Retrying is "
        "usually enough; if it repeats, it is load on Amazon's side."
    ),
    "request_log.hint.duplicate": (
        "Amazon answered that it was already building this same report, but did "
        "not say which one. Wait a few minutes and retry."
    ),
    "request_log.hint.deadline": (
        "The deadline passed before it could finish. The next scheduled update "
        "asks for these days again; if you need them sooner, retry."
    ),
    "request_log.hint.throttled": (
        "Amazon throttled the requests. The system waits on its own without "
        "spending attempts; retry later if needed."
    ),
    "request_log.hint.invalid_rows": (
        "The report came with data that fails validation. Retrying asks for a new "
        "one; if it repeats, pass this error to the systems team."
    ),
    "request_log.hint.invalid_job": (
        "The request was built wrong and cannot run. Pass this error to the "
        "systems team."
    ),
    "request_log.hint.save_crashed": (
        "The sync worker died twice while saving this chunk, almost always because "
        "the report was too large. Pass this error to the systems team before "
        "retrying."
    ),
    "request_log.hint.network": (
        "There was a network problem talking to Amazon or the database. Retrying "
        "is usually enough."
    ),
    "request_log.hint.amazon_api": (
        "Amazon rejected the request. Retrying is usually enough; if it repeats, "
        "pass this error to the systems team."
    ),
    "request_log.hint.default": (
        "Retrying is usually enough. If it fails again, pass this error to the "
        "systems team."
    ),
}

_CATALOG: dict[str, dict[str, str]] = {"es": _ES, "en": _EN}


# ══════════════════════════════════════════════════════════════════════════
# LOOKUP TABLES — routing keys and section titles
# ══════════════════════════════════════════════════════════════════════════

# Routing key → catalog key. The routing key is the literal `app.py` compares
# (emoji included) and must never be translated; only the label it shows is.
_PAGE_KEYS: dict[str, str] = {
    "🏠 Inicio": "nav.page.inicio",
    "📊 Search Term Report": "nav.page.search_term_report",
    "🔍 Search Query Performance": "nav.page.search_query_performance",
    "🔗 Análisis Cruzado STR vs SQP": "nav.page.analisis_cruzado",
    "📈 Tendencia Multi-Semana": "nav.page.tendencia_multisemana",
    "📁 Bulk Campañas": "nav.page.bulk_campanas",
    "💰 Business Report": "nav.page.business_report",
    "🔻 Análisis de Funnel": "nav.page.analisis_funnel",
    "🧠 Bid Optimizer": "nav.page.bid_optimizer",
    "🚀 Campaign Builder": "nav.page.campaign_builder",
    "⚙️ Atom11 Rules Builder": "nav.page.atom11_rules_builder",
    "🧲 DataDive Analyzer": "nav.page.datadive_analyzer",
    "🧲 Helium 10 Analyzer": "nav.page.helium10_analyzer",
    "📢 SBH Recommendation": "nav.page.sbh_recommendation",
    "🔎 PPC Insights": "nav.page.ppc_insights",
    "📈 PPC Forecast": "nav.page.ppc_forecast",
    "🛡️ PPC Audit": "nav.page.ppc_audit",
    "📊 Account Pulse": "nav.page.account_pulse",
    "🔬 Reportes Atom 11": "nav.page.reportes_atom11",
    "🛡️ Reportes MerchanSpring": "nav.page.reportes_merchanspring",
    "📊 Weekly Client Report": "nav.page.weekly_client_report",
    "👁️ Listing Monitor": "nav.page.listing_monitor",
    "🛡️ Listing Compliance": "nav.page.listing_compliance",
    "📊 Gamboa Generator": "nav.page.gamboa_generator",
    "🧬 Variation Builder": "nav.page.variation_builder",
    "📈 Monthly Forecast": "nav.page.monthly_forecast",
    "📋 Proposal Studio": "nav.page.proposal_studio",
    "🏆 Case Study Studio": "nav.page.case_study_studio",
    "📚 Knowledge Base": "nav.page.knowledge_base",
    "🗂️ Flat File Migrator": "nav.page.flat_file_migrator",
    "🏥 SKU Progress Report": "nav.page.sku_progress_report",
    "💲 Pricing Dashboard": "nav.page.pricing_dashboard",
    "🚚 Proveedores": "nav.page.supply_proveedores",
    "📦 Órdenes de Compra": "nav.page.supply_ordenes",
    "🛒 Mercado Libre": "nav.page.mercado_libre",
    "🔑 Cuentas conectadas": "nav.page.cuentas_conectadas",
    "🔌 Integraciones": "nav.page.integraciones",
    "🧾 Registro de solicitudes": "nav.page.registro_solicitudes",
}

# `navigation.Section.title` → catalog key. The title is also the identifier of
# the section in `SECTIONS`, so it is looked up, never translated in place.
_SECTION_KEYS: dict[str, str] = {
    "PPC": "nav.section.ppc",
    "Research": "nav.section.research",
    "Account": "nav.section.account",
    "Sales Director": "nav.section.sales_director",
    "Knowledge": "nav.section.knowledge",
    "Account Health": "nav.section.account_health",
    "Supply Chain": "nav.section.supply_chain",
    "Marketplaces": "nav.section.marketplaces",
    "Sistema": "nav.section.sistema",
}


# ══════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════

def current_lang() -> str:
    """The interface language: `"en"` or `"es"`, Spanish by default.

    Reads the sidebar radio's own option label out of `session_state`, so it
    works whether the widget has been drawn yet or not. Outside a Streamlit
    runtime — tests, scripts, `import` at collection time — session state is
    unreachable and the answer is the default, never an exception.
    """
    if st is None:
        return DEFAULT_LANG
    try:
        chosen = st.session_state.get("app_lang")
    except Exception:
        return DEFAULT_LANG
    return _RADIO_TO_LANG.get(chosen, DEFAULT_LANG)


def t(key: str, **kwargs) -> str:
    """The translated string for `key`, interpolated with `kwargs`.

    Degrades in three steps and never raises: the current language, then
    Spanish (the source language, always complete), then the key itself. A key
    is a readable last resort — `accounts.btn_close` in a button says what is
    missing; an empty label says nothing.

    `.format()` runs only when kwargs are passed, so markdown blocks with
    literal braces survive untouched. A template whose slots don't match the
    kwargs is returned raw rather than blowing up a render.
    """
    lang = current_lang()
    text = _CATALOG.get(lang, {}).get(key)
    if text is None:
        text = _ES.get(key)
    if text is None:
        return key
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


def tn(key: str, n: int, **kwargs) -> str:
    """The plural form of `key` for `n`, interpolated with `n` and `kwargs`.

    Reads `<key>_one` when `n == 1` and `<key>_other` otherwise, and always
    passes `n` into the format call, so a template can spend it (`"{n} cuentas"`)
    or ignore it (`"1 cuenta requiere reautorizar."`).

    Picking the branch here rather than at the call site is what stops the
    call site from appending an "s": Spanish also inflects the verb, and other
    languages have more than two forms.
    """
    variant = f"{key}_one" if n == 1 else f"{key}_other"
    return t(variant, n=n, **kwargs)


def t_provider(key: str, slug: str, **kwargs) -> str:
    """`key`, or its per-provider variant `<key>.<slug>` when the catalog has one.

    Some sentences are true for one provider and false for the others — a
    Mercado Libre account is authorized by the seller, an Amazon Ads one by the
    employee — and a neutral wording for both would say nothing. The variant
    is declared in Spanish, the source language, so its presence there decides;
    the parity test keeps English in step.
    """
    variant = f"{key}.{slug}"
    if variant in _ES:
        return t(variant, **kwargs)
    return t(key, **kwargs)


def page_label(routing_key: str) -> str:
    """The visible label of a sidebar destination, without its leading emoji.

    The routing key keeps the emoji — `app.py` compares it literally — while
    the rail draws a Material icon, so showing the emoji too would put two
    icons in one row. A destination that isn't in the catalog (a page added to
    `navigation.SECTIONS` and not yet translated) falls back to its Spanish
    routing key with the emoji stripped, which is exactly what the rail showed
    before i18n.
    """
    catalog_key = _PAGE_KEYS.get(routing_key)
    if catalog_key is not None:
        label = t(catalog_key)
        if label != catalog_key:
            return label
    return _strip_leading_emoji(routing_key)


def section_title(title: str) -> str:
    """The visible title of a `navigation.SECTIONS` section.

    The title doubles as the section's identifier, so an unknown one comes
    back unchanged instead of being blanked out.
    """
    catalog_key = _SECTION_KEYS.get(title)
    if catalog_key is None:
        return title
    translated = t(catalog_key)
    return title if translated == catalog_key else translated


def months_short() -> tuple[str, ...]:
    """The twelve abbreviated month names, in order, for the current language.

    Stored as one comma-separated entry so the catalog holds only strings;
    split here so no caller has to remember the separator.
    """
    return tuple(part.strip() for part in t("integrations.months_short").split(","))


def _strip_leading_emoji(page: str) -> str:
    """Everything from the first letter or digit on.

    Mirrors `core.navigation.visible_label` on purpose instead of importing it:
    this module sits underneath the navigation layer and stays free of it, so
    navigation can start calling `page_label()` without a circular import.
    Skipping to the first alphanumeric also carries away composite emojis like
    `🛡️` (symbol + variation selector U+FE0F) without orphaning the selector.
    """
    for index, char in enumerate(page):
        if char.isalnum():
            return page[index:]
    return page
