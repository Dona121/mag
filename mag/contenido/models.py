from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Create your models here.


class Fechas(models.Model):
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Categoria(Fechas):
    orden = models.IntegerField(null=True, verbose_name="Orden")
    nombre = models.CharField(max_length=50, verbose_name="Nombre Categoría")

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        return f"{self.nombre}"


class ModeloEvaluacion(Fechas):
    nombre = models.CharField(max_length=150, verbose_name="Nombre Modelo")
    version = models.IntegerField(verbose_name="Versión del Modelo")
    activo = models.BooleanField(verbose_name="Activo")

    class Meta:
        verbose_name = "Modelo Evaluación"
        verbose_name_plural = "Modelos Evaluación"

    def __str__(self):
        return f"{self.nombre}"

class Dependencia(Fechas):
    nombre = models.CharField(max_length=150, verbose_name="Dependencia")

    class Meta:
        verbose_name = "Dependencia"
        verbose_name_plural = "Dependencias"

    def __str__(self):
        return f"{self.nombre}"


class DependenciaModelo(Fechas):
    modelo = models.ForeignKey(ModeloEvaluacion, on_delete=models.CASCADE)
    dependencia = models.ForeignKey(
        Dependencia, on_delete=models.CASCADE, verbose_name="Dependencia"
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Dependencia Modelo"
        verbose_name_plural = "Dependencias Modelo"
        constraints = [
            models.UniqueConstraint(
                fields=["dependencia"],
                condition=models.Q(activo=True),
                name="unique_modelo_activo_por_dependencia",
            ),
            models.UniqueConstraint(
                fields=["dependencia", "modelo"], name="unique_dependencia_modelo"
            ),
        ]

    def __str__(self):
        return f"{self.modelo} - {self.dependencia}"


class PilarCategoria(Fechas):
    nombre = models.CharField(max_length=150, verbose_name="Nombre de la Categoría")

    class Meta:
        verbose_name = "Categoría de Pilar"
        verbose_name_plural = "Categorías de Pilares"

    def __str__(self):
        return self.nombre


class IndicadorCategoria(Fechas):
    nombre = models.CharField(max_length=255, verbose_name="Nombre de la Categoría")

    class Meta:
        verbose_name = "Categoría de Indicador"
        verbose_name_plural = "Categorías de Indicadores"

    def __str__(self):
        return self.nombre


class SubindicadorCategoria(Fechas):
    nombre = models.CharField(max_length=255, verbose_name="Nombre de la Categoría")

    class Meta:
        verbose_name = "Categoría de Subindicador"
        verbose_name_plural = "Categorías de Subindicador"

    def __str__(self):
        return self.nombre


class Pilar(Fechas):
    orden = models.IntegerField(null=True, verbose_name="Orden")
    modelo_evaluacion = models.ForeignKey(ModeloEvaluacion, on_delete=models.CASCADE)
    nombre = models.ForeignKey(PilarCategoria, on_delete=models.CASCADE)
    peso = models.DecimalField(max_digits=10, decimal_places=5, verbose_name="Peso")

    class Meta:
        verbose_name = "Pilar"
        verbose_name_plural = "Pilares"

    def __str__(self):
        return f"{self.nombre}"


class Indicador(Fechas):
    orden = models.IntegerField(null=True, verbose_name="Orden")
    pilar = models.ForeignKey(Pilar, on_delete=models.CASCADE)
    nombre = models.ForeignKey(IndicadorCategoria, on_delete=models.CASCADE)
    peso = models.DecimalField(max_digits=10, decimal_places=5, verbose_name="Peso")

    class Meta:
        verbose_name = "Indicador"
        verbose_name_plural = "Indicadores"

    def __str__(self):
        return f"{self.nombre}"


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    indicadores = models.ManyToManyField(Indicador, blank=True)


class Subindicador(Fechas):
    orden = models.IntegerField(null=True, verbose_name="Orden")
    indicador = models.ForeignKey(Indicador, on_delete=models.CASCADE)
    nombre = models.ForeignKey(SubindicadorCategoria, on_delete=models.CASCADE)
    peso = models.DecimalField(max_digits=10, decimal_places=5, verbose_name="Peso")
    tipo_calculo = models.CharField(
        max_length=20,
        choices=(("mensual", "Mesual"), ("directo", "Directo")),
        null=True,
    )

    class Meta:
        verbose_name = "Subindicador"
        verbose_name_plural = "Subindicadores"

    def __str__(self):
        return f"{self.nombre}"


class Criterio(Fechas):
    orden = models.IntegerField(null=True, verbose_name="Orden")
    subindicador = models.ForeignKey(Subindicador, on_delete=models.CASCADE)
    nombre = models.TextField(verbose_name="Criterio")
    rango = models.CharField(max_length=255, verbose_name="Peso")

    class Meta:
        verbose_name = "Criterio"
        verbose_name_plural = "Criterios"

    def __str__(self):
        return f"{self.nombre}"


class Periodo(Fechas):
    orden = models.IntegerField(null=True, verbose_name="Orden")
    vigencia = models.PositiveIntegerField(null=True,blank=False)
    nombre = models.CharField(max_length=100, verbose_name="Periodo")
    umbral = models.DecimalField(max_digits=4,decimal_places=2, null=True, blank=False)
    activo = models.BooleanField(default=True)
    publico = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Periodo"
        verbose_name_plural = "Periodos"

    def __str__(self):
        return f"{self.nombre}"


class Evaluacion(Fechas):
    periodo = models.ForeignKey(
        Periodo, on_delete=models.CASCADE, verbose_name="Periodo"
    )
    dependencia = models.ForeignKey(
        Dependencia, on_delete=models.CASCADE, verbose_name="Dependencia"
    )
    modelo_evaluacion = models.ForeignKey(
        ModeloEvaluacion, on_delete=models.CASCADE, verbose_name="Modelo Evaluación"
    )
    categoria = models.ForeignKey(Categoria,on_delete=models.CASCADE, null=True,blank=False)

    class Meta:
        verbose_name = "Evaluacion"
        verbose_name_plural = "Evaluaciones"
        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "dependencia"], name="unique_periodo_dependencia"
            )
        ]

    def __str__(self):
        return f"{self.periodo} - {self.dependencia}"

    def clean(self):
        if self.pk:
            original = Evaluacion.objects.filter(pk=self.pk).first()
            if original and original.modelo_evaluacion_id != self.modelo_evaluacion_id:
                raise ValidationError(
                    "No se puede cambiar el modelo de una evaluación existente"
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class EvaluacionResultado(Fechas):
    evaluacion = models.ForeignKey(
        Evaluacion, on_delete=models.CASCADE, verbose_name="Evaluación"
    )
    subindicador = models.ForeignKey(
        Subindicador, on_delete=models.CASCADE, verbose_name="Subindicador"
    )
    puntaje = models.DecimalField(
        max_digits=10, decimal_places=5, verbose_name="Puntaje", blank=True
    )
    ponderacion = models.DecimalField(
        max_digits=10, decimal_places=5, verbose_name="Ponderación", blank=True
    )
    observaciones = models.TextField(verbose_name="Observaciones", blank=True)

    class Meta:
        verbose_name = "Evaluación Resultado"
        verbose_name_plural = "Evaluaciones Resultado"
        constraints = [
            models.UniqueConstraint(
                fields=["evaluacion", "subindicador"],
                name="unique_evaluacion_subindicador",
            ),
        ]
        indexes = [
            models.Index(fields=["evaluacion"], name="evaluacion"),
            models.Index(fields=["subindicador"], name="subindicador"),
        ]

    def __str__(self):
        return f"{self.evaluacion} - {self.subindicador}"

    def clean(self):
        if (
            not self.subindicador.indicador.pilar.modelo_evaluacion_id
            == self.evaluacion.modelo_evaluacion_id
        ):
            raise ValidationError(
                "El subindicador no pertenece al modelo de la evaluación"
            )
        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Meses(models.IntegerChoices):
    ENERO = 1, "Enero"
    FEBRERO = 2, "Febrero"
    MARZO = 3, "Marzo"
    ABRIL = 4, "Abril"
    MAYO = 5, "Mayo"
    JUNIO = 6, "Junio"
    JULIO = 7, "Julio"
    AGOSTO = 8, "Agosto"
    SEPTIEMBRE = 9, "Septiembre"
    OCTUBRE = 10, "Octubre"
    NOVIEMBRE = 11, "Noviembre"
    DICIEMBRE = 12, "Diciembre"


class EvaluacionResultadoDetalle(models.Model):
    resultado = models.ForeignKey(EvaluacionResultado, on_delete=models.CASCADE)

    mes = models.IntegerField(
        choices=Meses.choices, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )  # 1: Enero, 2: Febrero, 3: Marzo, etc
    puntaje = models.DecimalField(max_digits=10, decimal_places=5)
    ponderacion = models.DecimalField(max_digits=10, decimal_places=5)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["resultado", "mes"], name="unique_resultado_mes"
            )
        ]

    def __str__(self):
        return f"{self.mes} - {self.puntaje}"
