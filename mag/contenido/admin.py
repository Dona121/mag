"""
Admin de la aplicacion, configurado con django-unfold.

Cada modelo se registra extendiendo `unfold.admin.ModelAdmin` para heredar el
estilo del paquete y se enriquece con list_display, list_filter, search_fields,
fieldsets e inlines acordes a la jerarquia del modelo de evaluacion.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import (
    Categoria,
    Criterio,
    Dependencia,
    DependenciaModelo,
    Evaluacion,
    EvaluacionResultado,
    EvaluacionResultadoDetalle,
    Indicador,
    IndicadorCategoria,
    ModeloEvaluacion,
    PerfilUsuario,
    Periodo,
    Pilar,
    PilarCategoria,
    Subindicador,
    SubindicadorCategoria,
)


class PerfilUsuarioInline(StackedInline):
    model = PerfilUsuario
    can_delete = False
    filter_horizontal = ("indicadores",)


class UsuarioAdmin(BaseUserAdmin, ModelAdmin):
    inlines = [PerfilUsuarioInline]
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


admin.site.unregister(User)
admin.site.register(User, UsuarioAdmin)


# ============================================================== Inlines


class PilarInline(TabularInline):
    model = Pilar
    extra = 0
    fields = ("orden", "nombre", "peso")
    show_change_link = True
    ordering = ("orden", "nombre")


class IndicadorInline(TabularInline):
    model = Indicador
    extra = 0
    fields = ("orden", "nombre", "peso")
    show_change_link = True
    ordering = ("orden", "nombre")


class SubindicadorInline(TabularInline):
    model = Subindicador
    extra = 0
    # Incluye tipo_calculo para diferenciar mensual / directo
    fields = ("orden", "nombre", "peso", "tipo_calculo")
    show_change_link = True
    ordering = ("orden", "nombre")


class CriterioInline(TabularInline):
    model = Criterio
    extra = 0
    # Bugfix: el modelo Criterio tiene `rango`, no `peso`
    fields = ("orden", "nombre", "rango")
    show_change_link = True
    ordering = ("orden", "nombre")


class DependenciaModeloInline(TabularInline):
    model = DependenciaModelo
    extra = 0
    fields = ("dependencia", "activo")
    autocomplete_fields = ("dependencia",)
    show_change_link = True


class EvaluacionResultadoDetalleInline(TabularInline):
    """Detalle mensual de un resultado (para subindicadores tipo 'mensual')."""

    model = EvaluacionResultadoDetalle
    extra = 0
    fields = ("mes", "puntaje", "ponderacion")
    ordering = ("mes",)


class EvaluacionResultadoInline(StackedInline):
    model = EvaluacionResultado
    extra = 0
    fields = ("subindicador", "puntaje", "ponderacion", "observaciones")
    autocomplete_fields = ("subindicador",)


# ============================================================== Modelos
@admin.register(ModeloEvaluacion)
class ModeloEvaluacionAdmin(ModelAdmin):
    list_display = ("nombre", "version", "activo", "creado_en", "actualizado_en")
    list_filter = ("activo",)
    search_fields = ("nombre",)
    ordering = ("-activo", "-version", "nombre")
    list_editable = ("activo",)
    fieldsets = (("Informacion general", {"fields": ("nombre", "version", "activo")}),)
    inlines = [PilarInline, DependenciaModeloInline]


@admin.register(Categoria)
class CategoriaAdmin(ModelAdmin):
    list_display = ("orden", "nombre", "creado_en")
    list_editable = ("nombre",)
    search_fields = ("nombre",)
    ordering = ("orden", "nombre")
    fieldsets = (("Categoria", {"fields": ("orden", "nombre")}),)


@admin.register(Dependencia)
class DependenciaAdmin(ModelAdmin):
    list_display = ("nombre", "creado_en")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    fieldsets = (("Dependencia", {"fields": ("nombre",)}),)


@admin.register(DependenciaModelo)
class DependenciaModeloAdmin(ModelAdmin):
    list_display = ("dependencia", "modelo", "activo", "creado_en")
    list_filter = ("activo", "modelo")
    search_fields = ("dependencia__nombre", "modelo__nombre")
    autocomplete_fields = ("dependencia", "modelo")
    list_editable = ("activo",)
    fieldsets = (("Asignacion", {"fields": ("modelo", "dependencia", "activo")}),)


# --- Catalogos de nombres (nombre de pilar/indicador/subindicador es FK aqui)
@admin.register(PilarCategoria)
class PilarCategoriaAdmin(ModelAdmin):
    list_display = ("nombre", "creado_en")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    fieldsets = (("Categoría de pilar", {"fields": ("nombre",)}),)


@admin.register(IndicadorCategoria)
class IndicadorCategoriaAdmin(ModelAdmin):
    list_display = ("nombre", "creado_en")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    fieldsets = (("Categoría de indicador", {"fields": ("nombre",)}),)


@admin.register(SubindicadorCategoria)
class SubindicadorCategoriaAdmin(ModelAdmin):
    list_display = ("nombre", "creado_en")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    fieldsets = (("Categoría de subindicador", {"fields": ("nombre",)}),)


@admin.register(Pilar)
class PilarAdmin(ModelAdmin):
    list_display = ("orden", "nombre", "peso", "modelo_evaluacion", "creado_en")
    list_filter = ("modelo_evaluacion",)
    search_fields = ("nombre__nombre", "modelo_evaluacion__nombre")
    autocomplete_fields = ("modelo_evaluacion", "nombre")
    ordering = ("modelo_evaluacion", "orden", "nombre__nombre")
    inlines = [IndicadorInline]
    fieldsets = (
        ("Pilar", {"fields": ("modelo_evaluacion", "orden", "nombre", "peso")}),
    )


@admin.register(Indicador)
class IndicadorAdmin(ModelAdmin):
    list_display = ("orden", "nombre", "peso", "pilar", "creado_en")
    list_filter = ("pilar__modelo_evaluacion", "pilar")
    search_fields = ("nombre__nombre", "pilar__nombre__nombre")
    autocomplete_fields = ("pilar", "nombre")
    ordering = ("pilar", "orden", "nombre__nombre")
    inlines = [SubindicadorInline]
    fieldsets = (("Indicador", {"fields": ("pilar", "orden", "nombre", "peso")}),)


@admin.register(Subindicador)
class SubindicadorAdmin(ModelAdmin):
    list_display = ("orden", "nombre", "peso", "tipo_calculo", "indicador", "creado_en")
    list_filter = (
        "tipo_calculo",
        "indicador__pilar__modelo_evaluacion",
        "indicador__pilar",
    )
    search_fields = ("nombre__nombre", "indicador__nombre__nombre")
    autocomplete_fields = ("indicador", "nombre")
    ordering = ("indicador", "orden", "nombre__nombre")
    list_editable = ("tipo_calculo",)
    inlines = [CriterioInline]
    fieldsets = (
        (
            "Subindicador",
            {
                "fields": ("indicador", "orden", "nombre", "peso", "tipo_calculo"),
                "description": "Si el tipo de calculo es 'mensual' los puntajes se "
                "diligencian por mes y se almacenan en EvaluacionResultadoDetalle.",
            },
        ),
    )


@admin.register(Criterio)
class CriterioAdmin(ModelAdmin):
    list_display = ("orden", "nombre", "rango", "subindicador", "creado_en")
    list_filter = ("subindicador__indicador__pilar__modelo_evaluacion",)
    search_fields = ("nombre", "rango", "subindicador__nombre__nombre")
    autocomplete_fields = ("subindicador",)
    ordering = ("subindicador", "orden", "nombre")
    fieldsets = (
        (
            "Criterio (guia descriptiva)",
            {"fields": ("subindicador", "orden", "nombre", "rango")},
        ),
    )


@admin.register(Periodo)
class PeriodoAdmin(ModelAdmin):
    list_display = ("orden", "nombre", "activo", "publico", "creado_en")
    list_filter = ("activo", "publico")
    list_editable = ("activo", "publico")
    search_fields = ("nombre",)
    ordering = ("-activo", "orden", "-creado_en")
    actions = (
        "activar_periodos", "desactivar_periodos",
        "publicar_periodos", "despublicar_periodos",
    )
    fieldsets = (
        (
            "Periodo",
            {
                "fields": ("orden", "nombre", "activo", "publico"),
                "description": "Tip: incluya en el nombre los meses del periodo "
                "(p.ej. 'Enero - Febrero - Marzo') para que el "
                "diligenciamiento de subindicadores mensuales muestre "
                "solo esos meses. Desactivar un periodo oculta sus "
                "evaluaciones del flujo operativo (sin borrar datos). "
                "«Público» controla la visibilidad en el reporte público "
                "(/reporte/): mientras esté en falso, los datos del periodo "
                "no se ven afuera aunque ya estén diligenciados; el dashboard "
                "interno los muestra siempre.",
            },
        ),
    )

    @admin.action(description="Activar periodos seleccionados")
    def activar_periodos(self, request, queryset):
        actualizados = queryset.update(activo=True)
        self.message_user(request, f"{actualizados} periodo(s) activado(s).")

    @admin.action(description="Desactivar periodos seleccionados")
    def desactivar_periodos(self, request, queryset):
        actualizados = queryset.update(activo=False)
        self.message_user(request, f"{actualizados} periodo(s) desactivado(s).")

    @admin.action(description="Publicar en el reporte público")
    def publicar_periodos(self, request, queryset):
        actualizados = queryset.update(publico=True)
        self.message_user(request, f"{actualizados} periodo(s) publicado(s).")

    @admin.action(description="Quitar del reporte público")
    def despublicar_periodos(self, request, queryset):
        actualizados = queryset.update(publico=False)
        self.message_user(request, f"{actualizados} periodo(s) retirado(s) del reporte público.")


@admin.register(Evaluacion)
class EvaluacionAdmin(ModelAdmin):
    list_display = ("periodo", "dependencia", "modelo_evaluacion", "creado_en")
    list_filter = ("periodo", "dependencia", "modelo_evaluacion")
    search_fields = (
        "periodo__nombre",
        "dependencia__nombre",
        "modelo_evaluacion__nombre",
    )
    autocomplete_fields = ("periodo", "dependencia", "modelo_evaluacion")
    readonly_fields = ("creado_en", "actualizado_en")
    inlines = [EvaluacionResultadoInline]
    fieldsets = (
        (
            "Identificacion",
            {"fields": ("periodo", "dependencia", "modelo_evaluacion")},
        ),
        (
            "Auditoria",
            {"fields": ("creado_en", "actualizado_en"), "classes": ("collapse",)},
        ),
    )


@admin.register(EvaluacionResultado)
class EvaluacionResultadoAdmin(ModelAdmin):
    list_display = ("evaluacion", "subindicador", "puntaje", "ponderacion", "creado_en")
    list_filter = (
        "evaluacion__periodo",
        "evaluacion__dependencia",
        "subindicador__tipo_calculo",
    )
    search_fields = (
        "evaluacion__periodo__nombre",
        "evaluacion__dependencia__nombre",
        "subindicador__nombre__nombre",
    )
    autocomplete_fields = ("evaluacion", "subindicador")
    inlines = [EvaluacionResultadoDetalleInline]
    fieldsets = (
        (
            "Resultado consolidado",
            {"fields": ("evaluacion", "subindicador", "puntaje", "ponderacion")},
        ),
        ("Notas", {"fields": ("observaciones",)}),
    )


@admin.register(EvaluacionResultadoDetalle)
class EvaluacionResultadoDetalleAdmin(ModelAdmin):
    """Detalle por mes de un resultado mensual (Sub.tipo_calculo='mensual')."""

    list_display = ("resultado", "mes", "puntaje", "ponderacion")
    list_filter = ("mes", "resultado__evaluacion__periodo")
    search_fields = (
        "resultado__evaluacion__periodo__nombre",
        "resultado__subindicador__nombre__nombre",
    )
    autocomplete_fields = ("resultado",)
    ordering = ("resultado", "mes")
    fieldsets = (
        ("Detalle mensual", {"fields": ("resultado", "mes", "puntaje", "ponderacion")}),
    )
