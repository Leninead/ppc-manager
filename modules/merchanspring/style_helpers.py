def _s_acos(val):
    try:
        v = float(val)
        if v < 30:  return "background-color:#C6EFCE;color:#276221"
        if v < 60:  return "background-color:#FFEB9C;color:#9C5700"
        return "background-color:#FFC7CE;color:#9C0006"
    except: return ""


def _s_margin(val):
    try:
        v = float(val)
        if v >= 40: return "background-color:#C6EFCE;color:#276221"
        if v >= 20: return "background-color:#FFEB9C;color:#9C5700"
        return "background-color:#FFC7CE;color:#9C0006"
    except: return ""


def _s_delta(val):
    try:
        v = float(val)
        if v > 5:   return "background-color:#C6EFCE;color:#276221"
        if v < -5:  return "background-color:#FFC7CE;color:#9C0006"
        return "background-color:#FFEB9C;color:#9C5700"
    except: return ""


def _s_eff(val):
    vl = str(val).lower()
    if "poor" in vl:              return "background-color:#FFC7CE;color:#9C0006"
    if "good" in vl or "great" in vl: return "background-color:#C6EFCE;color:#276221"
    if "average" in vl:           return "background-color:#FFEB9C;color:#9C5700"
    return ""


def _s_stock(val):
    vl = str(val).lower()
    if "in stock"  in vl: return "background-color:#C6EFCE;color:#276221"
    if "slow"      in vl: return "background-color:#FFEB9C;color:#9C5700"
    if "no stock"  in vl or "out" in vl or "critical" in vl:
        return "background-color:#FFC7CE;color:#9C0006"
    if "partial"   in vl: return "background-color:#FFE0B2;color:#BF360C"
    return ""
