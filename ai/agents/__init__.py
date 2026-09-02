"""AI agents (one package per slug: prompt.md + context.py)."""


def make_ids(prefix: str, n: int) -> list:
    """Positional row ids (N01, Q07, K12) for the rows sent to an agent."""
    return [f"{prefix}{i:02d}" for i in range(1, n + 1)]
