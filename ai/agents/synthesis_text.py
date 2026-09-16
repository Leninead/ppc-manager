"""The canonical synthesis every agent emits, as plain text for a chat document."""


def synthesis_text(synthesis: dict) -> str:
    lines = [f"Situación: {synthesis.get('situation', '')}"]
    if synthesis.get("week_actions"):
        lines.append("Acciones sugeridas para la semana:")
        lines += [f"{index}. {action}" for index, action in enumerate(synthesis["week_actions"], 1)]
    if synthesis.get("mid_term"):
        lines.append("Mediano plazo:")
        lines += [f"- {item}" for item in synthesis["mid_term"]]
    if synthesis.get("risks"):
        lines.append("Riesgos:")
        lines += [f"- {risk.get('type', '')} ({risk.get('urgency', '')}): {risk.get('detail', '')}"
                  for risk in synthesis["risks"]]
    if synthesis.get("executive_summary"):
        lines.append(f"Resumen ejecutivo: {synthesis['executive_summary']}")
    return "\n".join(lines)
