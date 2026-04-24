# SOP — VS Code: dos cuentas Claude Code + estrategia Git personal vs agencia

## Metadata
- **Categoría:** Estrategia
- **Subcategoría:** Setup dev · Workflow
- **Fecha de relevancia:** 2026
- **Autor:** Lenin Acosta
- **Fecha de creación:** 2026-03-21
- **Urgencia:** 🟡 Media — configurar antes de empezar proyectos personales

---

## Contexto

Lenin tiene dos cuentas de Claude.ai:
- **Cuenta personal** ($20/mes) — proyectos propios
- **Cuenta agencia** ($100/mes, pagada por Capybaras Agency) — PPC Manager y clientes

VS Code estaba vinculado solo a la cuenta de la agencia.
El repo de `ppc-manager` está en el GitHub personal de Lenin — la agencia no tiene acceso.

---

## PARTE 1 — Dos cuentas de Claude Code en VS Code (Perfiles)

### El problema
Claude Code en VS Code mantiene una sola sesión activa. Sin perfiles, hay que hacer sign out / sign in cada vez que cambiás de cuenta.

### La solución: Perfiles de VS Code (Plan B)

VS Code soporta perfiles nativos desde v1.75. Cada perfil tiene sus propias extensiones, configuraciones y autenticaciones — incluyendo Claude Code.

### Pasos para configurarlo (una sola vez)

**Paso 1 — Crear perfil "Agencia"**
1. Click en el ícono de perfil (abajo a la izquierda en la barra de estado) → `Create Profile`
2. Nombrarlo `Capybaras Agency`
3. Instalar Claude Code dentro de este perfil
4. Hacer Sign In con la cuenta de $100 (agencia)

**Paso 2 — Crear perfil "Personal"**
1. Mismo proceso → `Create Profile`
2. Nombrarlo `Personal`
3. Instalar Claude Code dentro de este perfil
4. Hacer Sign In con la cuenta de $20 (personal)

**Paso 3 — Switch entre perfiles**
- Click en el ícono de perfil (abajo a la izquierda) → seleccionar el perfil deseado
- VS Code recarga con las extensiones y autenticaciones del perfil seleccionado
- Un click, sin cerrar nada

### Regla de uso

| Contexto | Perfil activo |
|----------|--------------|
| PPC Manager, clientes, Capybaras | Capybaras Agency |
| Proyectos personales, experimentos | Personal |

---

## PARTE 2 — Estrategia Git: agencia vs proyectos personales

### El contexto
- El repo `ppc-manager` está en el GitHub personal de Lenin
- La agencia no tiene acceso ni conocimiento técnico del repo
- Se quiere mantener una versión agencia y una versión personal con features distintas

### La solución: dos ramas en el mismo repo
tu-github/ppc-manager
├── main          ← versión agencia (estado actual, producción)
└── personal      ← versión personal con features propias

No se necesita fork ni repo separado. Con ramas es suficiente mientras las versiones no diverjan completamente.

### Setup inicial (una sola vez)
```bash
# Desde el repo local, estando en main
git checkout -b personal    # crea la rama personal desde el estado actual
git push origin personal    # la sube a GitHub
```

### Flujo de trabajo diario

**Para trabajo de agencia:**
```bash
git checkout main
# trabajar normalmente
git add .
git commit -m "feat: descripción"
git push
```

**Para proyectos personales:**
```bash
git checkout personal
# trabajar normalmente
git add .
git commit -m "feat: descripción"
git push origin personal
```

**Para traer mejoras de agencia a la versión personal:**
```bash
git checkout personal
git merge main    # trae todo lo nuevo de main a personal
```

La dirección inversa (personal → main) es manual y opcional. Lenin decide qué sube a main y qué no.

### Regla de decisión: ¿cuándo separar en dos repos?

Separar en dos repos distintos solo cuando las versiones diverjan tanto que el mismo repo se vuelva confuso de mantener. Hoy no es el caso.

---

## PARTE 3 — Reglas de trabajo

1. **Antes de empezar sesión personal** → cambiar al perfil Personal en VS Code
2. **Antes de empezar sesión agencia** → cambiar al perfil Capybaras Agency
3. **Commits en rama correcta** — verificar con `git branch` antes de commitear
4. **Merge main → personal** cada vez que haya mejoras de agencia que también sirvan personalmente
5. **Nunca mergear personal → main** sin revisar qué features se están subiendo

---

## Tags
#sop #vscode #git #workflow #claudecode #cuentas #ramas #capybaras #personal #2026
