"""The ASINs losing the Buy Box in Account Pulse, with the sales the module estimates they lose."""
from __future__ import annotations

BUYBOX_ALERT_PERCENT = 95.0


def buybox_alerts(br_child: dict) -> list[dict]:
    """The by-Child ASINs with sessions and a Buy Box below 95%, most estimated lost sales first.

    The lost sales are the ASIN's sales times the share of time without the Buy Box: an estimate, not a measure."""
    alerts = [{"asin": asin, "title": row.get("Title", ""), "sales": row["Sales"], "sessions": row["Sessions"],
               "buybox": row["BuyBox"], "lost_sales": round(row["Sales"] * (1 - row["BuyBox"] / 100), 2)}
              for asin, row in br_child.items()
              if row.get("BuyBox") is not None and row["BuyBox"] < BUYBOX_ALERT_PERCENT and row.get("Sessions", 0) > 0]
    return sorted(alerts, key=lambda alert: (-alert["lost_sales"], alert["asin"]))
