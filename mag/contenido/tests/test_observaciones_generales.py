"""Observaciones generales de la evaluación (`Evaluacion.observaciones`).

Sirven para casos como "este subindicador no aplica en el periodo" (sus puntajes quedan
vacíos y por eso no se crea resultado). Se cubre:
  - se guardan aunque ningún subindicador tenga puntaje;
  - no pisan el aporte de otra persona (varias diligencian la misma evaluación);
  - el aviso cuando una observación de subindicador se descarta por no tener puntaje;
  - un usuario sin indicadores asignados no puede cambiarlas;
  - salen en el informe Excel/PDF solo cuando hay texto.
"""
from io import BytesIO

from django.contrib.messages import get_messages
from django.urls import reverse
from openpyxl import load_workbook

from contenido.models import Evaluacion, EvaluacionResultado

from .base import PASSWORD, BaseMagTestCase


class ObservacionesGeneralesTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()
        self.evaluacion = self.crear_evaluacion()
        self.url = reverse("contenido:evaluacion_diligenciar", args=[self.evaluacion.pk])

    def _post(self, nuevo, original="", **extra):
        datos = {"observaciones_generales": nuevo, "observaciones_generales_original": original}
        datos.update(extra)
        return self.client.post(self.url, datos, follow=True)

    def _obs(self):
        return Evaluacion.objects.get(pk=self.evaluacion.pk).observaciones

    @staticmethod
    def _mensajes(resp):
        return [str(m) for m in get_messages(resp.wsgi_request)]

    def test_se_guardan_sin_ningun_puntaje(self):
        texto = "El subindicador mensual no aplica en este periodo."
        resp = self._post(texto)
        self.assertEqual(self._obs(), texto)
        self.assertFalse(EvaluacionResultado.objects.filter(evaluacion=self.evaluacion).exists())
        self.assertContains(resp, texto)  # se muestran al volver a la pantalla

    def test_normaliza_saltos_de_linea_del_navegador(self):
        self._post("Línea 1\r\nLínea 2\r\n")
        self.assertEqual(self._obs(), "Línea 1\nLínea 2")

    def test_no_pisa_el_aporte_de_otra_persona(self):
        # Ambos abrieron la página con el texto vacío; otra persona guardó primero.
        Evaluacion.objects.filter(pk=self.evaluacion.pk).update(observaciones="Aporte de Ana")
        resp = self._post("Aporte de Luis", original="")
        self.assertEqual(self._obs(), "Aporte de Ana")
        self.assertTrue(any("otra persona" in m for m in self._mensajes(resp)))

    def test_si_no_las_cambio_no_borra_lo_que_otro_escribio(self):
        Evaluacion.objects.filter(pk=self.evaluacion.pk).update(observaciones="Aporte de Ana")
        self._post("", original="")  # su página cargó vacía y no tocó el campo
        self.assertEqual(self._obs(), "Aporte de Ana")

    def test_edita_sobre_el_texto_vigente(self):
        Evaluacion.objects.filter(pk=self.evaluacion.pk).update(observaciones="Aporte de Ana")
        self._post("Aporte de Ana\nAporte de Luis", original="Aporte de Ana")
        self.assertEqual(self._obs(), "Aporte de Ana\nAporte de Luis")

    def test_avisa_observacion_de_subindicador_descartada(self):
        resp = self._post("", **{
            "puntaje_{}".format(self.sub_directo.pk): "",
            "observaciones_{}".format(self.sub_directo.pk): "No aplica",
        })
        mensajes = self._mensajes(resp)
        self.assertTrue(any("Sub Directo" in m and "Observaciones generales" in m for m in mensajes),
                        mensajes)

    def test_diligenciar_sigue_exigiendo_login(self):
        self.client.logout()
        resp = self.client.post(self.url, {"observaciones_generales": "x",
                                           "observaciones_generales_original": ""})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("contenido:login"), resp["Location"])
        self.assertEqual(self._obs(), "")

    def test_evaluador_sin_indicadores_no_las_cambia(self):
        self.crear_evaluador(indicadores=None)
        self.client.logout()
        self.assertTrue(self.client.login(username="evaluador", password=PASSWORD))
        self._post("Intento de cambio")
        self.assertEqual(self._obs(), "")

    def test_informe_incluye_observaciones_solo_si_hay(self):
        datos = {"modelo": self.modelo.version, "categoria": self.categoria.pk,
                 "periodo": self.periodo.pk}
        # sin observaciones: no aparece la sección
        xl = self.client.post(reverse("contenido:reporte_generar"), dict(datos, formato="excel"))
        celdas = [c.value for row in load_workbook(BytesIO(xl.content)).worksheets[0].iter_rows()
                  for c in row]
        self.assertNotIn("OBSERVACIONES GENERALES", celdas)
        # con observaciones: título + texto en el Excel, y el PDF se genera
        Evaluacion.objects.filter(pk=self.evaluacion.pk).update(observaciones="No aplica X.")
        xl = self.client.post(reverse("contenido:reporte_generar"), dict(datos, formato="excel"))
        celdas = [c.value for row in load_workbook(BytesIO(xl.content)).worksheets[0].iter_rows()
                  for c in row]
        self.assertIn("OBSERVACIONES GENERALES", celdas)
        self.assertIn("No aplica X.", celdas)
        pdf = self.client.post(reverse("contenido:reporte_generar"), dict(datos, formato="pdf"))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
