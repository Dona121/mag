"""Filtros de formato numérico para las plantillas.

`decimales` muestra un mínimo de decimales (por defecto 2) y hasta un máximo
(por defecto 5, el tope real de los `DecimalField` del modelo), recortando los
ceros sobrantes. Así un peso 12,50000 se ve "12,50" pero uno de 33,33333 se ve
completo. Localiza con `floatformat`, que respeta la coma decimal de es-col.
"""
from decimal import Decimal, InvalidOperation

from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def decimales(value, bounds="2,5"):
    """Uso: ``{{ valor|decimales }}`` o ``{{ valor|decimales:"2,4" }}``.

    - Mínimo ``minp`` decimales (rellena con ceros).
    - Hasta ``maxp`` decimales cuando el valor los usa; recorta los ceros finales.
    """
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    try:
        minp, maxp = (int(x) for x in str(bounds).split(","))
    except (ValueError, TypeError):
        minp, maxp = 2, 5
    # Decimales significativos = exponente (negativo) del valor sin ceros finales.
    exp = d.normalize().as_tuple().exponent
    usados = -exp if isinstance(exp, int) and exp < 0 else 0
    return floatformat(d, max(minp, min(maxp, usados)))
