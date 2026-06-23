"""Middleware de control de acceso para el rol Evaluador."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import Resolver404, resolve

from .roles import EVALUADOR_URLS_PERMITIDAS, es_evaluador


class RolEvaluadorMiddleware:
    """Restringe la navegacion del rol Evaluador.

    Solo puede acceder a las URLs de `EVALUADOR_URLS_PERMITIDAS` (evaluaciones +
    dashboards + cuenta). Cualquier otra ruta del sistema lo redirige al listado
    de evaluaciones con un aviso. Es la defensa server-side que complementa el
    ocultamiento de modulos en el sidebar (un Evaluador no puede saltarse la
    restriccion escribiendo la URL a mano).

    Debe ir despues de AuthenticationMiddleware y MessageMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if es_evaluador(user):
            try:
                match = resolve(request.path_info)
            except Resolver404:
                match = None
            permitido = match is not None and (
                match.namespace == "contenido"
                and match.url_name in EVALUADOR_URLS_PERMITIDAS
            )
            # match None -> rutas no resueltas por la app (static/media/admin assets):
            # no las tocamos. Lo que SI bloqueamos son URLs resueltas y no permitidas.
            if match is not None and not permitido:
                messages.warning(
                    request,
                    "Tu rol Evaluador solo tiene acceso a Evaluaciones; "
                    "se te redirigio al listado.",
                )
                return redirect("contenido:evaluacion_list")
        return self.get_response(request)
