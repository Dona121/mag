"""
URLs de la app contenido.
"""
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "contenido"

urlpatterns = [
    # ----------------------------------------------------------- Auth
    path(
        "auth/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path(
        "auth/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "auth/password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url=reverse_lazy("contenido:password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "auth/password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html",
        ),
        name="password_change_done",
    ),

    # --------------------------------------------------------------- Inicio
    path("", views.dashboard, name="dashboard"),

    # Dashboard interno (con login): mismas 4 vistas del reporte, dentro del shell
    # y SIN la restriccion de periodo publico (el equipo ve todos los periodos).
    path("dashboard/", views.dashboard_imag, name="dashboard_imag"),
    path("dashboard/desempeno/", views.dashboard_desempeno, name="dashboard_desempeno"),
    path("dashboard/ranking/", views.dashboard_ranking, name="dashboard_ranking"),
    path("dashboard/variaciones/", views.dashboard_variaciones, name="dashboard_variaciones"),

    # ------------------------------------------------------------- Reportes
    # Compositor de informes descargables (Excel/PDF) por dependencia.
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/generar/", views.reporte_generar, name="reporte_generar"),

    # ----------------------------------------------- Reporte publico (sin login)
    # Replica del Power BI: IMAG · Desempeno · Ranking · Variaciones.
    path("reporte/", views.reporte_publico, name="reporte_publico"),
    path("reporte/desempeno/", views.reporte_desempeno, name="reporte_desempeno"),
    path("reporte/ranking/", views.reporte_ranking, name="reporte_ranking"),
    path("reporte/variaciones/", views.reporte_variaciones, name="reporte_variaciones"),

    # ----------------------------------------------------- Parametrizacion
    path("categorias/<str:tipo>/", views.categoria_list, name="categoria_list"),
    path("categorias/<str:tipo>/nueva/", views.categoria_create, name="categoria_create"),
    path("categorias/<str:tipo>/<int:pk>/editar/", views.categoria_editar, name="categoria_editar"),
    path("modelos/", views.ModeloEvaluacionListView.as_view(), name="modelo_list"),
    path("modelos/nuevo/", views.ModeloEvaluacionCreateView.as_view(), name="modelo_create"),
    path("modelos/<int:pk>/", views.modelo_detalle, name="modelo_detalle"),
    path("modelos/<int:pk>/editar/", views.ModeloEvaluacionUpdateView.as_view(), name="modelo_editar"),
    path("modelos/<int:pk>/activar/", views.modelo_activar, name="modelo_activar"),
    path("modelos/<int:pk>/dependencias/asignar/", views.dependencia_modelo_asignar, name="dependencia_modelo_asignar"),
    path("modelos/<int:pk>/pilares/nuevo/", views.pilar_create, name="pilar_create"),
    path("pilares/<int:pk>/editar/", views.pilar_editar, name="pilar_editar"),
    path("pilares/<int:pk>/indicadores/nuevo/", views.indicador_create, name="indicador_create"),
    path("indicadores/<int:pk>/editar/", views.indicador_editar, name="indicador_editar"),
    path("indicadores/<int:pk>/subindicadores/nuevo/", views.subindicador_create, name="subindicador_create"),
    path("subindicadores/<int:pk>/editar/", views.subindicador_editar, name="subindicador_editar"),
    path("subindicadores/<int:pk>/criterios/nuevo/", views.criterio_create, name="criterio_create"),
    path("criterios/<int:pk>/editar/", views.criterio_editar, name="criterio_editar"),

    # ---------------------------------------------------------- Evaluacion
    path("evaluaciones/", views.EvaluacionListView.as_view(), name="evaluacion_list"),
    path("evaluaciones/nueva/", views.EvaluacionCreateView.as_view(), name="evaluacion_create"),
    path("evaluaciones/<int:pk>/diligenciar/", views.evaluacion_diligenciar, name="evaluacion_diligenciar"),

    # ------------------------------------------------------------ Periodos
    path("periodos/", views.PeriodoListView.as_view(), name="periodo_list"),
    path("periodos/<int:pk>/activar/", views.periodo_activar, name="periodo_activar"),
    path("periodos/<int:pk>/desactivar/", views.periodo_desactivar, name="periodo_desactivar"),
    path("periodos/<int:pk>/umbral/", views.periodo_umbral_editar, name="periodo_umbral_editar"),
    path("periodos/<int:pk>/publicar/", views.periodo_publicar, name="periodo_publicar"),
    path("periodos/<int:pk>/despublicar/", views.periodo_despublicar, name="periodo_despublicar"),
]
