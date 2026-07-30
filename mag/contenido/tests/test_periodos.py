"""Modulo de Periodos: activar/desactivar, publicar/despublicar y umbral/vigencia.

Estas acciones cambian estado (no son un CRUD clasico) y solo deben operar por
POST; un GET no debe modificar nada.
"""
from decimal import Decimal

from django.urls import reverse

from .base import BaseMagTestCase


class PeriodoEstadoTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def test_listado(self):
        self.assertEqual(
            self.client.get(reverse("contenido:periodo_list")).status_code, 200
        )

    def test_desactivar_y_activar(self):
        self.client.post(reverse("contenido:periodo_desactivar", args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.activo)
        self.client.post(reverse("contenido:periodo_activar", args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.activo)

    def test_get_no_cambia_estado(self):
        self.client.get(reverse("contenido:periodo_desactivar", args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.activo)  # sigue activo

    def test_publicar_y_despublicar(self):
        self.client.post(reverse("contenido:periodo_publicar", args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.publico)
        self.client.post(reverse("contenido:periodo_despublicar", args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.publico)

    def test_editar_umbral_y_vigencia(self):
        self.client.post(
            reverse("contenido:periodo_umbral_editar", args=[self.periodo.pk]),
            {"umbral": "70", "vigencia": "2026"},
        )
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.umbral, Decimal("70.00"))
        self.assertEqual(self.periodo.vigencia, 2026)

    def test_umbral_vacio_queda_none(self):
        self.client.post(
            reverse("contenido:periodo_umbral_editar", args=[self.periodo.pk]),
            {"umbral": "", "vigencia": "2026"},
        )
        self.periodo.refresh_from_db()
        self.assertIsNone(self.periodo.umbral)

    def test_vigencia_invalida_no_guarda(self):
        self.client.post(
            reverse("contenido:periodo_umbral_editar", args=[self.periodo.pk]),
            {"umbral": "70", "vigencia": "abcd"},
        )
        self.periodo.refresh_from_db()
        # vigencia sigue siendo la original (2026), no se corrompio
        self.assertEqual(self.periodo.vigencia, 2026)
