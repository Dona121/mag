"""CRUD del modulo de Parametrizacion (catalogos + estructura del modelo).

Cubre las vistas: categoria_list/create/editar, ModeloEvaluacion (CBV),
pilar/indicador/subindicador/criterio create+editar y modelo_detalle.
No hay vistas de borrado en la capa web (el borrado se prueba a nivel ORM en
test_modelos_orm).
"""
from decimal import Decimal

from django.urls import reverse

from contenido.models import (
    Criterio,
    Indicador,
    IndicadorCategoria,
    ModeloEvaluacion,
    Pilar,
    PilarCategoria,
    Subindicador,
    SubindicadorCategoria,
)

from .base import BaseMagTestCase


class CatalogoCategoriaTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def test_listar_cada_tipo(self):
        for tipo in ("pilar", "indicador", "subindicador"):
            resp = self.client.get(reverse("contenido:categoria_list", args=[tipo]))
            self.assertEqual(resp.status_code, 200, tipo)

    def test_tipo_invalido_devuelve_404(self):
        resp = self.client.get(reverse("contenido:categoria_list", args=["inexistente"]))
        self.assertEqual(resp.status_code, 404)

    def test_crear_categoria_pilar(self):
        resp = self.client.post(
            reverse("contenido:categoria_create", args=["pilar"]),
            {"nombre": "Pilar Nuevo"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(PilarCategoria.objects.filter(nombre="Pilar Nuevo").exists())

    def test_crear_categoria_sin_nombre_no_crea(self):
        antes = SubindicadorCategoria.objects.count()
        resp = self.client.post(
            reverse("contenido:categoria_create", args=["subindicador"]),
            {"nombre": "   "},
        )
        self.assertEqual(resp.status_code, 200)  # re-render con error
        self.assertEqual(SubindicadorCategoria.objects.count(), antes)

    def test_editar_categoria(self):
        resp = self.client.post(
            reverse("contenido:categoria_editar", args=["indicador", self.icat.pk]),
            {"nombre": "Indicador Renombrado"},
        )
        self.assertEqual(resp.status_code, 302)
        self.icat.refresh_from_db()
        self.assertEqual(self.icat.nombre, "Indicador Renombrado")


class ModeloCRUDTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def test_listar_y_detalle(self):
        self.assertEqual(
            self.client.get(reverse("contenido:modelo_list")).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                reverse("contenido:modelo_detalle", args=[self.modelo.pk])
            ).status_code,
            200,
        )

    def test_crear_modelo(self):
        resp = self.client.post(
            reverse("contenido:modelo_create"),
            {"nombre": "Modelo 2027", "version": "2", "activo": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ModeloEvaluacion.objects.filter(nombre="Modelo 2027", version=2).exists())

    def test_editar_modelo(self):
        resp = self.client.post(
            reverse("contenido:modelo_editar", args=[self.modelo.pk]),
            {"nombre": "Modelo Editado", "version": "1", "activo": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        self.modelo.refresh_from_db()
        self.assertEqual(self.modelo.nombre, "Modelo Editado")

    def test_activar_modelo_requiere_post(self):
        otro = ModeloEvaluacion.objects.create(nombre="Otro", version=3, activo=False)
        # GET no cambia estado
        self.client.get(reverse("contenido:modelo_activar", args=[otro.pk]))
        otro.refresh_from_db()
        self.assertFalse(otro.activo)
        # POST activa
        self.client.post(reverse("contenido:modelo_activar", args=[otro.pk]))
        otro.refresh_from_db()
        self.assertTrue(otro.activo)


class EstructuraCRUDTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def test_crear_pilar(self):
        resp = self.client.post(
            reverse("contenido:pilar_create", args=[self.modelo.pk]),
            {"nombre": self.pcat.pk, "peso": "50", "orden": "2"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Pilar.objects.filter(modelo_evaluacion=self.modelo, peso=Decimal("50")).exists()
        )

    def test_crear_pilar_sin_categoria_no_crea(self):
        antes = Pilar.objects.count()
        # Sin elegir categoria: el <select> no envia el campo 'nombre'.
        resp = self.client.post(
            reverse("contenido:pilar_create", args=[self.modelo.pk]),
            {"peso": "50"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Pilar.objects.count(), antes)

    def test_editar_pilar(self):
        resp = self.client.post(
            reverse("contenido:pilar_editar", args=[self.pilar.pk]),
            {"nombre": self.pcat.pk, "peso": "77", "orden": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.pilar.refresh_from_db()
        self.assertEqual(self.pilar.peso, Decimal("77.00000"))

    def test_crear_indicador(self):
        resp = self.client.post(
            reverse("contenido:indicador_create", args=[self.pilar.pk]),
            {"nombre": self.icat.pk, "peso": "30", "orden": "2"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Indicador.objects.filter(pilar=self.pilar, peso=Decimal("30")).exists()
        )

    def test_editar_indicador(self):
        resp = self.client.post(
            reverse("contenido:indicador_editar", args=[self.indicador.pk]),
            {"nombre": self.icat.pk, "peso": "40", "orden": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.indicador.refresh_from_db()
        self.assertEqual(self.indicador.peso, Decimal("40.00000"))

    def test_crear_subindicador_mensual(self):
        resp = self.client.post(
            reverse("contenido:subindicador_create", args=[self.indicador.pk]),
            {"nombre": self.scat_mensual.pk, "peso": "5", "tipo_calculo": "mensual", "orden": "3"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Subindicador.objects.filter(
                indicador=self.indicador, tipo_calculo="mensual", peso=Decimal("5")
            ).exists()
        )

    def test_crear_subindicador_tipo_invalido_cae_a_directo(self):
        resp = self.client.post(
            reverse("contenido:subindicador_create", args=[self.indicador.pk]),
            {"nombre": self.scat_directo.pk, "peso": "5", "tipo_calculo": "raro", "orden": "4"},
        )
        self.assertEqual(resp.status_code, 302)
        creado = Subindicador.objects.filter(indicador=self.indicador, orden=4).first()
        self.assertIsNotNone(creado)
        self.assertEqual(creado.tipo_calculo, "directo")

    def test_editar_subindicador_cambia_tipo(self):
        resp = self.client.post(
            reverse("contenido:subindicador_editar", args=[self.sub_directo.pk]),
            {"nombre": self.scat_directo.pk, "peso": "10", "tipo_calculo": "mensual", "orden": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.sub_directo.refresh_from_db()
        self.assertEqual(self.sub_directo.tipo_calculo, "mensual")

    def test_crear_criterio(self):
        resp = self.client.post(
            reverse("contenido:criterio_create", args=[self.sub_directo.pk]),
            {"nombre": "Nuevo criterio", "rango": "50-100", "orden": "2"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Criterio.objects.filter(subindicador=self.sub_directo, nombre="Nuevo criterio").exists()
        )

    def test_crear_criterio_incompleto_no_crea(self):
        antes = Criterio.objects.count()
        resp = self.client.post(
            reverse("contenido:criterio_create", args=[self.sub_directo.pk]),
            {"nombre": "Sin rango", "rango": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Criterio.objects.count(), antes)

    def test_editar_criterio(self):
        resp = self.client.post(
            reverse("contenido:criterio_editar", args=[self.criterio.pk]),
            {"nombre": "Cumple parcialmente", "rango": "0-50", "orden": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.criterio.refresh_from_db()
        self.assertEqual(self.criterio.nombre, "Cumple parcialmente")
        self.assertEqual(self.criterio.rango, "0-50")
