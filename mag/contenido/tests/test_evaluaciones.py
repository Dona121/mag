"""CRUD del modulo de Evaluaciones.

- Crear evaluacion (CBV): toma el modelo activo de la dependencia; rechaza
  duplicados (periodo+dependencia).
- Diligenciar: crea / actualiza / BORRA los EvaluacionResultado por subindicador,
  tanto directos como mensuales (con su detalle por mes).
  Incluye la regresion del bug: borrar un puntaje directo debe eliminar el
  resultado (antes lo dejaba intacto).
"""
from decimal import Decimal

from django.urls import reverse

from contenido.models import (
    Evaluacion,
    EvaluacionResultado,
    EvaluacionResultadoDetalle,
)

from .base import BaseMagTestCase


class EvaluacionCreacionTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def test_crear_evaluacion_asigna_modelo_activo(self):
        resp = self.client.post(
            reverse("contenido:evaluacion_create"),
            {"periodo": self.periodo.pk, "dependencia": self.dep.pk, "categoria": self.categoria.pk},
        )
        self.assertEqual(resp.status_code, 302)
        ev = Evaluacion.objects.get(periodo=self.periodo, dependencia=self.dep)
        self.assertEqual(ev.modelo_evaluacion_id, self.modelo.pk)
        # redirige a diligenciar
        self.assertIn(str(ev.pk), resp["Location"])

    def test_no_permite_duplicado_periodo_dependencia(self):
        self.crear_evaluacion()
        resp = self.client.post(
            reverse("contenido:evaluacion_create"),
            {"periodo": self.periodo.pk, "dependencia": self.dep.pk, "categoria": self.categoria.pk},
        )
        self.assertEqual(resp.status_code, 200)  # form invalido, re-render
        self.assertEqual(
            Evaluacion.objects.filter(periodo=self.periodo, dependencia=self.dep).count(), 1
        )

    def test_listado_evaluaciones(self):
        self.crear_evaluacion()
        resp = self.client.get(reverse("contenido:evaluacion_list"))
        self.assertEqual(resp.status_code, 200)


class DiligenciarDirectoTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()
        self.evaluacion = self.crear_evaluacion()
        self.url = reverse("contenido:evaluacion_diligenciar", args=[self.evaluacion.pk])

    def _post_directo(self, valor):
        data = {}
        if valor is not None:
            data["puntaje_{}".format(self.sub_directo.pk)] = valor
        return self.client.post(self.url, data)

    def test_crear_resultado_directo(self):
        self._post_directo("80")
        r = EvaluacionResultado.objects.get(
            evaluacion=self.evaluacion, subindicador=self.sub_directo
        )
        self.assertEqual(r.puntaje, Decimal("80.00000"))
        # ponderacion = puntaje * peso_sub / 100 = 80 * 10 / 100 = 8
        self.assertEqual(r.ponderacion, Decimal("8.00000"))

    def test_actualizar_resultado_directo(self):
        self._post_directo("80")
        self._post_directo("90")
        self.assertEqual(
            EvaluacionResultado.objects.filter(
                evaluacion=self.evaluacion, subindicador=self.sub_directo
            ).count(),
            1,
        )
        r = EvaluacionResultado.objects.get(subindicador=self.sub_directo)
        self.assertEqual(r.puntaje, Decimal("90.00000"))

    def test_borrar_resultado_directo_regresion(self):
        """Regresion: al borrar el puntaje directo el resultado debe eliminarse."""
        self._post_directo("80")
        self.assertTrue(
            EvaluacionResultado.objects.filter(subindicador=self.sub_directo).exists()
        )
        # POST con el campo vacio -> debe borrar (antes quedaba el valor viejo)
        self._post_directo("")
        self.assertFalse(
            EvaluacionResultado.objects.filter(subindicador=self.sub_directo).exists()
        )


class DiligenciarMensualTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()
        self.evaluacion = self.crear_evaluacion()
        self.url = reverse("contenido:evaluacion_diligenciar", args=[self.evaluacion.pk])

    def test_crear_resultado_mensual_promedia(self):
        self.client.post(self.url, {
            "puntaje_{}_{}".format(self.sub_mensual.pk, 1): "70",
            "puntaje_{}_{}".format(self.sub_mensual.pk, 2): "80",
        })
        r = EvaluacionResultado.objects.get(subindicador=self.sub_mensual)
        # promedio de los meses capturados (70, 80) = 75
        self.assertEqual(r.puntaje, Decimal("75.00000"))
        detalles = EvaluacionResultadoDetalle.objects.filter(resultado=r)
        self.assertEqual(detalles.count(), 2)

    def test_quitar_un_mes_borra_su_detalle(self):
        self.client.post(self.url, {
            "puntaje_{}_{}".format(self.sub_mensual.pk, 1): "70",
            "puntaje_{}_{}".format(self.sub_mensual.pk, 2): "80",
        })
        # segundo guardado deja solo el mes 1
        self.client.post(self.url, {
            "puntaje_{}_{}".format(self.sub_mensual.pk, 1): "70",
        })
        r = EvaluacionResultado.objects.get(subindicador=self.sub_mensual)
        meses = set(
            EvaluacionResultadoDetalle.objects
            .filter(resultado=r).values_list("mes", flat=True)
        )
        self.assertEqual(meses, {1})

    def test_borrar_todos_los_meses_elimina_resultado(self):
        self.client.post(self.url, {
            "puntaje_{}_{}".format(self.sub_mensual.pk, 1): "70",
        })
        self.assertTrue(
            EvaluacionResultado.objects.filter(subindicador=self.sub_mensual).exists()
        )
        # POST sin ningun mes -> se borra el resultado y sus detalles (cascada)
        self.client.post(self.url, {})
        self.assertFalse(
            EvaluacionResultado.objects.filter(subindicador=self.sub_mensual).exists()
        )
        self.assertEqual(EvaluacionResultadoDetalle.objects.count(), 0)
