# DEV-WORKFLOW — Metodología de desarrollo de Agency OS

> **Leé este archivo antes de tocar git.** Define cómo se trabaja en `ppc-manager`
> desde la migración de infraestructura del 18–20/08/2026. Reemplaza el modelo
> anterior de "consolidador único". Si un prompt de arranque viejo contradice esto,
> vale esto.

**Última actualización:** 2026-08-20 · **Vigente desde:** commit `cfc2f92` (destrackeo de `notes/`)

---

## TL;DR (lo mínimo que todo chat tiene que saber)

1. **No hay consolidador.** Cada chat/frente pushea lo suyo a `main` directamente.
2. **`notes/` ya NO vive en git.** El vault vive en disco + Obsidian. Nunca se pushea.
3. **Antes de cada push: `fetch` + `rebase` sobre `origin/main`.** Es lo que evita colisiones.
4. **`main` auto-deploya a producción vía Jenkins.** Un push malo rompe la app para todo el equipo.
5. **Solo se pushea código funcional y testeado.** Nada a medias.

---

## Contexto: qué cambió en la migración

Hasta el 18/08 la app corría en Streamlit Community Cloud y el vault (`notes/`) se
versionaba dentro del repo. Se llegó al techo de RAM (~1 GB) y la app se caía en producción.

Juan Vargas ejecutó la migración de infraestructura:

- La app ahora corre en una **VPS** (Oracle ARM, São Paulo), en vivo en `app.capybaras.agency` con HTTPS (Caddy/Let's Encrypt).
- El backend migró de **Supabase a Postgres self-hosted** dentro de la VPS.
- **`main` auto-deploya a producción vía Jenkins.** Cada push a `main` se despliega.
- El vault (`notes/`) se **destrackeó del repo** (commit `cfc2f92`, vía `git rm --cached`). Los archivos siguen en disco; solo dejaron de versionarse.

Consecuencia para el flujo de trabajo: el rol de "consolidador único que pushea el vault
una vez al día" perdió su razón de ser. Se reemplaza por el modelo de este documento.

---

## Modelo nuevo: cada chat pushea lo suyo

No hay un chat que junte y pushee por todos. Cada frente commitea y pushea su propio
trabajo de código a `main`, respetando las reglas de abajo para no pisarse con otros
frentes ni romper producción.

### Qué se pushea y qué no

| Contenido | ¿Va a git / se pushea? | Dónde vive |
|---|---|---|
| Código (`modules/`, `core/`, `app.py`, `tests/`, `deploy/`) | Sí | Repo, se pushea a `main` |
| Metodología / SOPs de dev (este archivo, `CLAUDE.md`) | Sí | Repo, en `docs/` o raíz |
| Vault / notas de trabajo (`notes/`) | **No** | Disco + Obsidian, nunca se pushea |

---

## Las reglas de push (obligatorias, en orden)

Como `main` auto-deploya a producción, todo push sigue esta secuencia. Sin excepciones.

### 1. Pre-flight (verificar dónde estás parado)

```
pwd
git remote -v
git branch --show-current
git status
git log -1
```

### 2. Fetch + rebase sobre `origin/main` (evita colisiones)

Antes de pushear, traé lo que otros frentes hayan pusheado y poné tu trabajo encima:

```
git fetch origin
git rebase origin/main
```

Si otro chat pusheó mientras trabajabas, esto integra su cambio antes que el tuyo.
Sin este paso, dos frentes se pisan sobre `main` y Jenkins deploya un estado roto.

### 3. Verificar que NO se cuela `notes/`

```
git diff --cached --name-only
git status
```

Si aparece **cualquier** archivo bajo `notes/` en lo que se va a pushear, **frená** y
sacalo del stage. `notes/` no se versiona más. Reintroducirlo deshace el trabajo de
Juan y rompe el modelo.

### 4. Push (solo con lo anterior limpio)

```
git push origin <tu-rama>   # o main, según el flujo acordado con Juan
```

Solo se pushea **código funcional y testeado**. Jenkins deploya al instante: un push a
medias tira la app para todo el equipo (fue lo que pasó con el módulo pesado que agotó
la RAM).

---

## Reglas duras que NO cambiaron

- **Nunca `git add .` ni `git add modules/`.** Siempre paths explícitos.
- **Cada frente en su propio worktree.** Comparten el `.venv` en `C:\proyectos\ppc-manager\.venv`.
- **Discovery antes de codear:** leé el código y los datos reales antes de diseñar la solución.
- **No levantar `streamlit run` repetido desde el repo main** (genera procesos huérfanos sobre el `.venv` compartido). Cerrar con Ctrl+C, nunca matando el PID.

---

## Formato de commits y PRs (estándar de Juan)

Todo commit relevante y todo PR usa esta estructura de 3 secciones + tests:

- **User Description:** impacto para el usuario final. Si es un cambio interno sin efecto de usuario: `Empty (internal change, no user-facing impact)`.
- **General Description:** qué se hizo y por qué, en bullets. Contexto, decisiones, dependencias con otros cambios.
- **Files:** detalle archivo por archivo de qué cambió y por qué.
- **Tests:** resultado (ej: `pytest → 850 passed, 24 skipped, 4 failed`), aclarando si algún fail es pre-existente / no relacionado.

---

## El vault (`notes/`) en el modelo nuevo

- Vive en disco (`C:\proyectos\ppc-manager\notes\`) y se edita en Obsidian.
- **No se pushea.** "Consolidar" o "cerrar" el vault ahora significa **escribir a disco**, no hacer git push.
- Los chats que quieran documentar en el vault escriben el `.md` en disco; ese archivo no viaja por git.
- Si un cierre de sesión pide "pushear el vault", eso ya no aplica — es escritura local.

---

## Pendiente de definir con Juan (meet del jueves)

Este documento refleja lo acordado hasta el 20/08. Quedan por cerrar:

- ¿El push de cada chat va a `main` directo, o a una rama que luego se integra? (afecta el paso 4)
- Cómo se comparte el vault entre el equipo ahora que no viaja por git (¿Obsidian sync? ¿otra vía?)
- Modelo de accesos a la VPS (Jenkins / pgAdmin / SSH) para monitoreo.
- Agente reviewer automático que Juan va a montar (reemplaza el PR manual).

Hasta que eso se cierre, ante la duda: **commiteá local, y coordiná el push por Slack
antes de tocar `main`.**
