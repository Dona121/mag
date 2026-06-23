"""Context processors de la app contenido."""

from .roles import es_evaluador


def roles(request):
    """Expone `es_evaluador` a todas las plantillas (para ocultar modulos del
    sidebar segun el rol)."""
    return {"es_evaluador": es_evaluador(getattr(request, "user", None))}
