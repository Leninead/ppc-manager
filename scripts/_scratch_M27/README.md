# Scratch M27 — Flat File Migrator

Archivos de discovery / scratch tests del chat M27 (Flat File Migrator
v1.1, B5-b row extractor). Movidos acá desde el root del repo el
2026-05-20 para mantener root limpio.

Estos archivos NO son código de producción. Son notebooks de discovery
o tests ad-hoc del proceso de desarrollo. El chat M27 los maneja en su
próxima sesión: revisar, integrar a tests/, o borrar.

## Inventario

- `discovery_b5b_required.py` — discovery del schema Required en B5-b
  (D3 cerrado con data real, ver daily 2026-05-20)
- `test_b5b_extract.py` — scratch test del row extractor B5-b
  (validó OLD/fptcustom + NEW/ptd contra archivos reales Gamboa/COAT)

## Decisión cierre 2026-05-20

M27 sugirió borrar. Lenin decidió mantener (criterio "no borrar nada
hasta validar manualmente"). Próxima sesión M27 decide qué hacer con
ellos.
