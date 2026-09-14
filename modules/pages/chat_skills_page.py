"""Sistema › Skills. Subir conocimiento del chat sin pasar por el código.

Una skill es un archivo de texto que el chat lee sólo cuando decide que aplica:
el formato del reporte semanal, cómo responder cuando un cliente discute el
ACoS, la convención de nombres de campaña de la agencia. Amazon publica las
suyas; éstas las escribe Capybaras.

La pantalla es de admin y lo dice dos veces: el rail no la ofrece
(`core.navigation.ADMIN_ONLY`) y acá se vuelve a chequear el rol, porque
esconder un botón no es control de acceso.

Dos decisiones de esta pantalla, y las dos son sobre no mentirle a quien sube:

* La descripción se muestra tal cual quedó. Es el único texto que el modelo lee
  para decidir si una skill aplica, así que una descripción vaga es una skill
  que nunca se va a usar, y eso hay que poder verlo antes de irse.
* El error de validación se muestra entero y en castellano. Guardar algo que el
  provider va a rechazar con un 422 en mitad de una conversación es la peor
  forma de enterarse.
"""
from __future__ import annotations

import streamlit as st

from core import chat_skills
from core.integrations import roles

_UPLOAD_KEY = "chat_skills_upload"


def _fmt_when(iso: str) -> str:
    return (iso or "").replace("T", " ")[:16] or "—"


def _render_one(name: str, skill: chat_skills.Skill) -> None:
    head, toggle, drop = st.columns([6, 1.4, 1])
    with head:
        estado = "activa" if skill.enabled else "apagada"
        st.markdown(f"**`{name}`** · {estado}")
        st.caption(skill.description or "— sin descripción —")
    with toggle:
        nuevo = st.toggle("Activa", value=skill.enabled, key=f"sk_on_{name}",
                          label_visibility="collapsed")
        if nuevo != skill.enabled:
            chat_skills.set_enabled(name, nuevo)
            st.rerun()
    with drop:
        if st.button("Borrar", key=f"sk_del_{name}"):
            st.session_state[f"sk_confirm_{name}"] = True
    if st.session_state.get(f"sk_confirm_{name}"):
        st.warning(f"¿Borrar «{name}»? El chat deja de usarla.")
        yes, no = st.columns(2)
        if yes.button("Sí, borrar", key=f"sk_yes_{name}", type="primary"):
            chat_skills.remove(name)
            st.session_state.pop(f"sk_confirm_{name}", None)
            st.rerun()
        if no.button("No", key=f"sk_no_{name}"):
            st.session_state.pop(f"sk_confirm_{name}", None)
            st.rerun()

    meta = f"{skill.chars:,} caracteres · {len(skill.files)} archivo(s)".replace(",", ".")
    if skill.uploaded_by or skill.uploaded_at:
        meta += f" · subida por {skill.uploaded_by or '—'} el {_fmt_when(skill.uploaded_at)}"
    st.caption(meta)
    with st.expander("Ver el texto que lee el chat"):
        for item in skill.files:
            st.caption(item.get("path", ""))
            st.code(item.get("content", ""), language="markdown")
    st.divider()


def render(username: str = "", role: str = roles.USER) -> None:
    st.title("🧠 Skills")

    if not roles.is_admin(role):
        st.error("Esta pantalla es sólo para admin.")
        return

    st.caption(
        "Conocimiento que el chat usa cuando la pregunta lo pide. No son datos: "
        "son instrucciones que el modelo obedece, así que lo que subas cambia "
        "cómo le contesta a todos los AMs."
    )

    # Las de Amazon no se listan. Vienen en la imagen del provider, no se
    # editan, no se apagan y no se borran: una sección donde no se puede hacer
    # nada es ruido en una pantalla de administración.
    subidas = chat_skills.load()

    if not subidas:
        st.info("Todavía no subiste ninguna.")
    for nombre in sorted(subidas):
        _render_one(nombre, subidas[nombre])

    st.subheader("Subir una")
    st.caption(
        f"Un `SKILL.md`, o un `.zip` con una carpeta que se llame igual que la "
        f"skill. El archivo arranca con un encabezado `--- name: … "
        f"description: … ---`. Máximo {chat_skills.MAX_SKILLS} skills, "
        f"{chat_skills.MAX_CHARS:,} caracteres cada una.".replace(",", ".")
    )
    archivo = st.file_uploader("Archivo de la skill", type=["md", "zip"],
                               key=_UPLOAD_KEY, label_visibility="collapsed")
    if archivo is None:
        return

    try:
        skill = chat_skills.parse_upload(archivo.name, archivo.getvalue())
    except chat_skills.SkillRejected as exc:
        st.error(str(exc))
        return

    st.success(f"Se llama **{skill.name}** y ocupa {skill.chars:,} caracteres."
               .replace(",", "."))
    st.markdown("**Así la va a leer el chat para decidir si aplica:**")
    st.info(skill.description)
    if skill.name in subidas:
        st.warning(f"Ya existe una skill «{skill.name}». Subirla la reemplaza.")

    if st.button("Guardar", type="primary", key="sk_save"):
        try:
            chat_skills.save(skill, uploaded_by=username)
        except chat_skills.SkillRejected as exc:
            st.error(str(exc))
            return
        st.success(f"«{skill.name}» guardada. El chat la puede usar desde el próximo mensaje.")
        st.rerun()
