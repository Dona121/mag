"""Control de acceso: login requerido, rol Evaluador y reporte publico.

- Vistas internas exigen sesion (redirigen a login si anonimo).
- El reporte publico (/reporte/) es accesible sin login.
- El rol Evaluador solo navega su lista permitida (middleware deny-by-default):
  ve Evaluaciones y dashboards, pero se le bloquea Parametrizacion/Periodos.
- El compositor de Reportes carga y genera archivos Excel/PDF.
"""
from django.urls import reverse

from .base import BaseMagTestCase


class AccesoAnonimoTests(BaseMagTestCase):
    def test_vista_interna_redirige_a_login(self):
        resp = self.client.get(reverse("contenido:modelo_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp["Location"])

    def test_reporte_publico_accesible_sin_login(self):
        for name in ("reporte_publico", "reporte_desempeno", "reporte_ranking", "reporte_variaciones"):
            resp = self.client.get(reverse("contenido:" + name))
            self.assertEqual(resp.status_code, 200, name)


class RolEvaluadorTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.crear_evaluador(indicadores=[self.indicador])
        self.assertTrue(self.client.login(username="evaluador", password="clave-de-prueba-123"))

    def test_evaluador_ve_evaluaciones(self):
        self.assertEqual(
            self.client.get(reverse("contenido:evaluacion_list")).status_code, 200
        )

    def test_evaluador_puede_diligenciar(self):
        ev = self.crear_evaluacion()
        resp = self.client.get(reverse("contenido:evaluacion_diligenciar", args=[ev.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_evaluador_bloqueado_en_parametrizacion(self):
        resp = self.client.get(reverse("contenido:modelo_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("contenido:evaluacion_list"), resp["Location"])

    def test_evaluador_bloqueado_en_periodos(self):
        resp = self.client.get(reverse("contenido:periodo_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("contenido:evaluacion_list"), resp["Location"])


class ReportesTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()
        self.crear_evaluacion()  # deja la dependencia en alcance

    def test_pantalla_reportes_carga(self):
        self.assertEqual(self.client.get(reverse("contenido:reportes")).status_code, 200)

    def test_generar_excel(self):
        resp = self.client.post(reverse("contenido:reporte_generar"), {
            "modelo": self.modelo.version, "categoria": self.categoria.pk,
            "periodo": self.periodo.pk, "formato": "excel",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertGreater(len(resp.content), 0)

    def test_generar_pdf(self):
        resp = self.client.post(reverse("contenido:reporte_generar"), {
            "modelo": self.modelo.version, "categoria": self.categoria.pk,
            "periodo": self.periodo.pk, "formato": "pdf",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
