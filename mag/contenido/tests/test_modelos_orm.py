"""CRUD completo a nivel ORM y reglas de integridad de los modelos.

La capa web no expone borrado para casi ningun modelo, asi que aqui se cubre
el Delete (y la cascada) directamente sobre el ORM, ademas de las restricciones
declaradas en Meta (unique constraints) y en clean().
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from contenido.models import (
    Criterio,
    DependenciaModelo,
    Evaluacion,
    EvaluacionResultado,
    Pilar,
    Subindicador,
)

from .base import BaseMagTestCase


class BorradoEnCascadaTests(BaseMagTestCase):
    def test_borrar_pilar_cascadea_hijos(self):
        pilar_pk = self.pilar.pk
        self.pilar.delete()
        self.assertFalse(Pilar.objects.filter(pk=pilar_pk).exists())
        # Indicadores/Subindicadores/Criterios del pilar tambien desaparecen
        self.assertFalse(Subindicador.objects.filter(indicador__pilar_id=pilar_pk).exists())
        self.assertFalse(Criterio.objects.filter(subindicador__indicador__pilar_id=pilar_pk).exists())

    def test_borrar_evaluacion_cascadea_resultados(self):
        ev = self.crear_evaluacion()
        EvaluacionResultado.objects.create(
            evaluacion=ev, subindicador=self.sub_directo,
            puntaje=Decimal("50"), ponderacion=Decimal("5"), observaciones="",
        )
        ev.delete()
        self.assertFalse(EvaluacionResultado.objects.filter(evaluacion__pk=ev.pk).exists())

    def test_borrar_subindicador(self):
        pk = self.sub_directo.pk
        self.sub_directo.delete()
        self.assertFalse(Subindicador.objects.filter(pk=pk).exists())
        self.assertFalse(Criterio.objects.filter(subindicador_id=pk).exists())


class IntegridadTests(BaseMagTestCase):
    def test_evaluacion_unica_por_periodo_dependencia(self):
        self.crear_evaluacion()
        # Evaluacion.save() llama full_clean(), que valida el UniqueConstraint
        # antes de llegar a la BD -> ValidationError (no IntegrityError).
        with self.assertRaises(ValidationError):
            Evaluacion.objects.create(
                periodo=self.periodo, dependencia=self.dep,
                modelo_evaluacion=self.modelo, categoria=self.categoria,
            )

    def test_no_cambiar_modelo_de_evaluacion(self):
        from contenido.models import ModeloEvaluacion

        ev = self.crear_evaluacion()
        otro = ModeloEvaluacion.objects.create(nombre="Otro", version=9, activo=False)
        ev.modelo_evaluacion = otro
        with self.assertRaises(ValidationError):
            ev.save()  # clean() prohibe cambiar el modelo

    def test_resultado_debe_pertenecer_al_modelo(self):
        """Un subindicador de otro modelo no puede evaluarse en esta evaluacion."""
        from contenido.models import (
            IndicadorCategoria,
            ModeloEvaluacion,
            PilarCategoria,
            SubindicadorCategoria,
        )

        otro_modelo = ModeloEvaluacion.objects.create(nombre="Otro", version=8, activo=False)
        p = Pilar.objects.create(
            orden=1, modelo_evaluacion=otro_modelo,
            nombre=PilarCategoria.objects.create(nombre="P otro"), peso=Decimal("100"),
        )
        from contenido.models import Indicador

        ind = Indicador.objects.create(
            orden=1, pilar=p,
            nombre=IndicadorCategoria.objects.create(nombre="I otro"), peso=Decimal("100"),
        )
        sub_ajeno = Subindicador.objects.create(
            orden=1, indicador=ind,
            nombre=SubindicadorCategoria.objects.create(nombre="S otro"),
            peso=Decimal("10"), tipo_calculo="directo",
        )
        ev = self.crear_evaluacion()
        with self.assertRaises(ValidationError):
            EvaluacionResultado.objects.create(
                evaluacion=ev, subindicador=sub_ajeno,
                puntaje=Decimal("50"), ponderacion=Decimal("5"), observaciones="",
            )

    def test_una_sola_asignacion_activa_por_dependencia(self):
        from contenido.models import ModeloEvaluacion

        otro = ModeloEvaluacion.objects.create(nombre="Otro", version=7, activo=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DependenciaModelo.objects.create(
                    modelo=otro, dependencia=self.dep, activo=True
                )
