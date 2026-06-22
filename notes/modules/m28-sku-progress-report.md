---
tipo: modulo
modulo: M28
seccion: Account Health
actualizado: 2026-06-21
---

# M28 — SKU Progress Report

## 2026-06-21 — Vinculación a Supabase (vía capa compartida) + EN PRODUCCIÓN

M28 quedó wired a Supabase a través del swap de core/persistence.py (mismo mecanismo que M30). Con el flag global activo (Cloud), M28 persiste en Supabase; sin flag, disco local (paridad de path verificada).

- Tablas: ah_snapshots (snapshots), ah_logs (optimizations, append-only id surrogate), ah_client_configs (tracked-skus, PK area,cliente,modulo,name). + ah_configs no la usa M28.
- Módulo 100% backend-agnostic: las 4 escrituras fuera de banda (tracked-skus.json directo, shutil.rmtree, 2 unlink) + el escaneo de disco de _list_clientes → todas vía la capa. Grep de control limpio, cero I/O de disco.
- delete_cliente ACOTADO al módulo (borra snapshot+log+config del módulo, NO cross-módulo). Era bug latente el rmtree de carpeta entera.
- Smoke E2E verde contra Supabase real. 2 code-reviews MERGE. Suite 367.
- EN PRODUCCIÓN (flag global ya en Cloud, el merge a main 28d2905 fue la activación).
- Deudas viejas saldadas de paso: R1 (Path("data") relativo → DATA_ROOT vía la capa), R3 (unlink directo → _delete_snapshot/_delete_history).
