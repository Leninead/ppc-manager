"""The kind of each Business Report day in Account Pulse: working day, weekend or Mexican holiday."""
from datetime import date

MX_HOLIDAYS = {
    (1, 1): "Año Nuevo", (2, 3): "Constitución", (3, 17): "Juárez",
    (5, 1): "Día del Trabajo", (9, 16): "Independencia",
    (11, 2): "Día de Muertos", (11, 18): "Revolución", (12, 25): "Navidad",
}


def day_type(day: date) -> tuple[str, str | None]:
    """("Festivo", the holiday's name), ("Finde", None) or ("Laboral", None)."""
    key = (day.month, day.day)
    if key in MX_HOLIDAYS:
        return "Festivo", MX_HOLIDAYS[key]
    if day.weekday() >= 5:
        return "Finde", None
    return "Laboral", None
