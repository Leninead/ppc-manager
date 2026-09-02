"""Read-only smoke of the DataDive API with a real key (pytest never runs it).

Checks against the live server what cannot be verified locally: the key
(quota), the niche listing, the /keywords contract with the real relevancy
distribution, and probes /roots and /ranking-juices. GETs only — consumes no
billable tokens.

Usage:
    set DATADIVE_API_KEY=...   (or export in bash)
    python scripts/smoke_datadive_api.py [nicheId]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_launch_score_drift
from core.datadive import DataDiveClient, DataDiveError, keywords_to_mkl_df


def main() -> int:
    key = os.environ.get("DATADIVE_API_KEY", "").strip()
    if not key:
        print("FALTA DATADIVE_API_KEY en el entorno — abortando (smoke no corrida).")
        return 2
    client = DataDiveClient(key)

    print("== /v1/quota ==")
    quota = client.quota()
    for name, usage in (quota.get("features") or {}).items():
        print(f"  {name}: {usage}")
    print(f"  nextRefreshDate: {quota.get('nextRefreshDate')}")

    print("\n== /v1/niches ==")
    niches = client.list_niches()
    print(f"  {len(niches)} niches")
    if not niches:
        print("  Sin niches — nada más que validar.")
        return 1

    niche_id = sys.argv[1] if len(sys.argv) > 1 else niches[0]["nicheId"]
    label = next((n.get("nicheLabel") for n in niches
                  if n.get("nicheId") == niche_id), niche_id)
    print(f"\n== /v1/niches/{niche_id}/keywords ({label}) ==")
    payload = client.niche_keywords(niche_id)
    df, asins = keywords_to_mkl_df(payload)
    print(f"  {len(df)} keywords · {len(asins)} ASINs competidores")
    if not df.empty:
        rel = df["Relevance"]
        print(f"  Relevance (post ×10): min={rel.min():.2f} p50={rel.median():.2f} "
              f"max={rel.max():.2f}  -> esperado dentro de 0-10")
        print(f"  SV: min={df['SV'].min()} max={df['SV'].max()}")
        print(f"  Sugg. Bid: min={df['Sugg. Bid'].min():.2f} "
              f"max={df['Sugg. Bid'].max():.2f}  -> esperado en dólares, no centavos")

    for probe in ("roots", "ranking-juices"):
        print(f"\n== sonda GET /v1/niches/{niche_id}/{probe} ==")
        try:
            body = client.request(f"/v1/niches/{niche_id}/{probe}")
            data = body.get("data")
            size = len(data) if isinstance(data, (list, dict)) else "?"
            print(f"  200 OK — data ({type(data).__name__}, {size} items)")
        except DataDiveError as e:
            print(f"  {e}")

    print()
    drift = check_launch_score_drift.main()   # 0 = no drift
    print("\nSmoke OK." if drift == 0 else
          "\nSmoke con ADVERTENCIA: revisar el drift del Launch Score arriba.")
    return 0 if drift == 0 else 1
