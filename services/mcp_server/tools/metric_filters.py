"""How the chat asks for rows by their figures and in what order, the same in every tool that lists them."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, get_args, get_origin, get_type_hints

from pydantic import ConfigDict, WithJsonSchema, with_config
# Pydantic reads typing.TypedDict only from Python 3.12; the image and CI run 3.11.
from typing_extensions import TypedDict

# The figures a row carries that a filter can bound; bid_gap only exists on keywords and product targets.
FILTER_METRICS = ("spend", "sales", "orders", "clicks", "impressions", "acos", "cvr", "roas", "cpc", "bid_gap")
# What a list can be ordered by. ctr and aov travel in a row only when it is ordered by them.
SORT_METRICS = ("spend", "sales", "orders", "clicks", "impressions", "acos", "cvr", "roas", "cpc", "ctr", "aov")
SortMetric = Literal["spend", "sales", "orders", "clicks", "impressions", "acos", "cvr", "roas", "cpc", "ctr", "aov"]
SortOrder = Literal["desc", "asc"]
FILTERS_NOTE = ("Sólo vienen las filas que cumplen filters, y total las cuenta; totals, counts y leaders son de todas "
                "las filas. Una fila sin el valor de una métrica (ACoS sin ventas, CVR sin clicks) no cumple un "
                "filtro sobre esa métrica.")


@with_config(ConfigDict(extra="forbid"))
class MetricFilters(TypedDict, total=False):
    """Bounds on a row's figures; combine=any keeps a row that meets one of them, all (the default) every one."""

    min_spend: float
    max_spend: float
    min_sales: float
    max_sales: float
    min_orders: int
    max_orders: int
    min_clicks: int
    max_clicks: int
    min_impressions: int
    max_impressions: int
    min_acos: float
    max_acos: float
    min_cvr: float
    max_cvr: float
    min_roas: float
    max_roas: float
    min_cpc: float
    max_cpc: float
    min_bid_gap: float
    max_bid_gap: float
    without_sales: bool
    combine: Literal["all", "any"]


def _filters_schema() -> dict:
    """MetricFilters as a plain typed object: a property without its own type never reaches the model typed."""
    json_types = {int: "integer", float: "number", bool: "boolean"}
    properties = {}
    for key, kind in get_type_hints(MetricFilters).items():
        if get_origin(kind) is Literal:
            properties[key] = {"type": "string", "enum": list(get_args(kind))}
        else:
            properties[key] = {"type": json_types[kind]}
    return {"type": "object", "properties": properties, "additionalProperties": False}


# The parameter's type: validated as MetricFilters, published as a typed object.
FiltersParam = Annotated[MetricFilters | None, WithJsonSchema(_filters_schema())]


@dataclass(frozen=True)
class RowFilter:
    """The bounds of a MetricFilters, applied to rows."""

    bounds: tuple[tuple[str, str, float], ...] = ()
    without_sales: bool = False
    combine: str = "all"

    @classmethod
    def from_request(cls, filters: MetricFilters | dict | None, *,
                     metrics: tuple[str, ...] = FILTER_METRICS) -> RowFilter:
        """The filter asked for, checked against the metrics the rows of that tool carry."""
        filters = dict(filters or {})
        combine = filters.pop("combine", "all")
        if combine not in ("all", "any"):
            raise ValueError("filters.combine tiene que ser all o any.")
        without_sales = bool(filters.pop("without_sales", False))
        bounds = []
        for key, value in filters.items():
            side, _, metric = key.partition("_")
            if side not in ("min", "max") or metric not in FILTER_METRICS:
                raise ValueError(f"filters no conoce {key!r}: van min_ y max_ de {', '.join(FILTER_METRICS)}, "
                                 "without_sales y combine.")
            if metric not in metrics:
                raise ValueError(f"{key} no se puede usar acá: estas filas filtran por {', '.join(metrics)}.")
            if value is None:
                continue
            bounds.append((side, metric, float(value)))
        return cls(tuple(bounds), without_sales, combine)

    def applied(self) -> bool:
        return bool(self.bounds) or self.without_sales

    def keeps(self, row: dict) -> bool:
        conditions = [_within(row.get(metric), side, bound) for side, metric, bound in self.bounds]
        if self.without_sales:
            conditions.append(bool(row.get("spend")) and not row.get("sales"))
        if not conditions:
            return True
        return any(conditions) if self.combine == "any" else all(conditions)

    def described(self) -> dict:
        if not self.applied():
            return {}
        asked = {f"{side}_{metric}": _plain(bound) for side, metric, bound in self.bounds}
        if self.without_sales:
            asked["without_sales"] = True
        if self.combine == "any":
            asked["combine"] = "any"
        return {"filters": asked, "filters_note": FILTERS_NOTE}


def _within(value, side: str, bound: float) -> bool:
    if value is None:
        return False
    return value >= bound if side == "min" else value <= bound


def sort_rows(rows: list[dict], metric: str, order: str = "desc") -> list[dict]:
    """Rows by one figure, highest first or lowest first; the ones without it always go last."""
    if order not in ("desc", "asc"):
        raise ValueError("sort_order tiene que ser desc (de mayor a menor) o asc (de menor a mayor).")
    known = [row for row in rows if row.get(metric) is not None]
    unknown = [row for row in rows if row.get(metric) is None]
    return sorted(known, key=lambda row: row[metric], reverse=order == "desc") + unknown


def with_sort_figure(rows: list[dict], metric: str) -> list[dict]:
    """Each row with ctr or aov when the list is ordered by it: they only travel then, to keep rows short."""
    if metric == "ctr":
        for row in rows:
            row["ctr"] = ctr(row.get("clicks"), row.get("impressions"))
    elif metric == "aov":
        for row in rows:
            row["aov"] = aov(row.get("sales"), row.get("orders"))
    return rows


def ctr(clicks, impressions) -> float | None:
    return round(clicks / impressions * 100, 2) if clicks is not None and impressions else None


def aov(sales, orders) -> float | None:
    return round(sales / orders, 2) if sales is not None and orders else None


def check_sort(metric: str, allowed: tuple[str, ...] = SORT_METRICS) -> None:
    if metric not in allowed:
        raise ValueError(f"sort_by tiene que ser uno de: {', '.join(allowed)}")


def _plain(value: float):
    return int(value) if float(value).is_integer() else value
