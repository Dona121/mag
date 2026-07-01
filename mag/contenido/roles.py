"""
Rol "Evaluador".

Un Evaluador (grupo de Django `Evaluador`) solo gestiona evaluaciones: ve las
evaluaciones activas y asigna/modifica el puntaje de los indicadores que tiene
asignados en su PerfilUsuario. En el panel solo accede a los modulos General
(Inicio + Dashboard), Operacion > Evaluaciones y Cuenta.

El control se aplica en dos capas:
  - `RolEvaluadorMiddleware` (server-side): bloquea cualquier URL fuera de la
    lista permitida.
  - Context processor `es_evaluador` + plantillas: oculta del sidebar los modulos
    a los que no tiene acceso.

Los superusuarios nunca se ven afectados por estas restricciones.
"""

GRUPO_EVALUADOR = "Evaluador"

# url_names (namespace 'contenido') a los que el rol Evaluador puede acceder.
EVALUADOR_URLS_PERMITIDAS = frozenset({
    # General
    "dashboard", "dashboard_imag", "dashboard_desempeno",
    "dashboard_ranking", "dashboard_variaciones",
    # Reportes (compositor de informes Excel/PDF)
    "reportes", "reporte_generar",
    # Operacion > Evaluaciones (ver listado y diligenciar; NO crear)
    "evaluacion_list", "evaluacion_diligenciar",
    # Cuenta / autenticacion
    "login", "logout", "password_change", "password_change_done",
    # Reporte publico (sin login; se permite por consistencia)
    "reporte_publico", "reporte_desempeno", "reporte_ranking", "reporte_variaciones",
})


def es_evaluador(user):
    """True si `user` pertenece al grupo Evaluador (los superusuarios -> False).

    El resultado se memoiza en el propio objeto `user` para no repetir la consulta
    en el mismo request (middleware + context processor + vistas)."""
    if not (user and user.is_authenticated and not user.is_superuser):
        return False
    cached = getattr(user, "_es_evaluador", None)
    if cached is None:
        cached = user.groups.filter(name=GRUPO_EVALUADOR).exists()
        user._es_evaluador = cached
    return cached
