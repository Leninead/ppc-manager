"""The clients the Pricing Dashboard saves snapshots for, display name to the slug its snapshots are stored under.

There is no canonical Account Health catalog yet, so the Pricing Dashboard and the modules that read its snapshots
share this one.
"""

PRICING_CLIENTS: dict[str, str] = {
    "Dermaglos": "dermaglos",
    "LTD / Love To Dream": "ltd",
    "Setex": "setex",
    "Mott & Bow": "mott-bow",
    "OPTIPET": "optipet",
    "Gamboa": "gamboa",
}
