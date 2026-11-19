"""Reporte de Ranking de dependencias en Excel (/reportes/, tipo=ranking).

Estructura esperada: una hoja con el nombre del periodo; fila 1 = versión del modelo;
fila 2 = cabecera Categoría | Dependencia | Puntaje | Ranking; luego una fila por
dependencia ordenada por puesto. El cálculo es el mismo del Ranking del dashboard.
"""
from decimal import Decimal
from io import BytesIO

from django.urls import reverse
from openpyxl import load_workbook

from contenido.models import (
    Categoria, Dependencia, DependenciaModelo, Evaluacion, EvaluacionResultado,
)
from contenido.views import _puntajes_por_dependencia, _ranking

from .base import BaseMagTestCase

D = Decimal


class ReporteRankingTests(BaseMagTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()
        self.otra_cat = Categoria.objects.create(orden=2, nombre="Categoría B")
        # puntajes (sobre el subindicador directo de peso 10): 10 x puntaje / 100
        self.deps = {}
        for nombre, puntaje, cat in (("Secretaria de Prueba", 80, self.categoria),
                                     ("Zeta", 50, self.categoria),
                                     ("Alfa", 50, self.categoria),          # empate con Zeta
                                     ("Otra categoría", 100, self.otra_cat)):
            dep = self.dep if nombre == "Secretaria de Prueba" else Dependencia.objects.create(nombre=nombre)
            if dep is not self.dep:
                DependenciaModelo.objects.create(modelo=self.modelo, dependencia=dep, activo=True)
            ev = Evaluacion.objects.create(periodo=self.periodo, dependencia=dep,
                                           modelo_evaluacion=self.modelo, categoria=cat)
            EvaluacionResultado.objects.create(
                evaluacion=ev, subindicador=self.sub_directo, puntaje=D(puntaje),
                ponderacion=D(puntaje) * self.sub_directo.peso / 100, observaciones="")
            self.deps[nombre] = dep

    def _generar(self, categoria, **extra):
        datos = {"modelo": self.modelo.version, "categoria": categoria,
                 "periodo": self.periodo.pk, "tipo": "ranking", "formato": "excel"}
        datos.update(extra)
        resp = self.client.post(reverse("contenido:reporte_generar"), datos)
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertIn("Ranking_MAG_v1", resp["Content-Disposition"])
        return load_workbook(BytesIO(resp.content))

    @staticmethod
    def _filas(ws):
        return [tuple(c.value for c in row) for row in ws.iter_rows(min_row=3, max_col=4)]

    def test_estructura_de_la_hoja(self):
        wb = self._generar(self.categoria.pk)
        self.assertEqual(len(wb.worksheets), 1)
        ws = wb.worksheets[0]
        self.assertEqual(ws.title, self.periodo.nombre)                 # hoja = periodo
        self.assertEqual(ws["A1"].value, "Versión del modelo: 1")       # fila 1 = versión
        self.assertEqual([c.value for c in ws[2]][:4],
                         ["Categoría", "Dependencia", "Puntaje", "Ranking"])

    def test_orden_puntajes_y_desempate_alfabetico(self):
        filas = self._filas(self._generar(self.categoria.pk).worksheets[0])
        self.assertEqual(filas, [
            ("Despacho", "Secretaria de Prueba", 8.0, 1),
            ("Despacho", "Alfa", 5.0, 2),     # empate a 5,00: alfabético
            ("Despacho", "Zeta", 5.0, 3),
        ])

    def test_coincide_con_el_ranking_del_dashboard(self):
        pun = _puntajes_por_dependencia(self.categoria, self.modelo.version, self.periodo)
        pos = _ranking(pun)
        filas = self._filas(self._generar(self.categoria.pk).worksheets[0])
        for _cat, dep, _p, puesto in filas:
            self.assertEqual(puesto, pos[self.deps[dep].pk])

    def test_todas_las_categorias_es_ranking_general_con_su_categoria(self):
        filas = self._filas(self._generar("todas").worksheets[0])
        self.assertEqual(filas[0], ("Categoría B", "Otra categoría", 10.0, 1))
        self.assertEqual([f[3] for f in filas], [1, 2, 3, 4])

    def test_dependencias_marcadas_conservan_su_puesto_real(self):
        wb = self._generar(self.categoria.pk, dependencia=[str(self.deps["Zeta"].pk)])
        self.assertEqual(self._filas(wb.worksheets[0]), [("Despacho", "Zeta", 5.0, 3)])

    def test_evaluada_sin_resultados_entra_con_cero_al_final(self):
        sin = Dependencia.objects.create(nombre="Sin resultados")
        DependenciaModelo.objects.create(modelo=self.modelo, dependencia=sin, activo=True)
        Evaluacion.objects.create(periodo=self.periodo, dependencia=sin,
                                  modelo_evaluacion=self.modelo, categoria=self.categoria)
        filas = self._filas(self._generar(self.categoria.pk).worksheets[0])
        self.assertEqual(filas[-1], ("Despacho", "Sin resultados", 0.0, 4))

    def test_ranking_ignora_pdf(self):
        # el ranking es solo Excel aunque llegue formato=pdf
        wb = self._generar(self.categoria.pk, formato="pdf")
        self.assertEqual(wb.worksheets[0]["A1"].value, "Versión del modelo: 1")

    def test_informe_por_dependencia_sigue_igual(self):
        resp = self.client.post(reverse("contenido:reporte_generar"), {
            "modelo": self.modelo.version, "categoria": self.categoria.pk,
            "periodo": self.periodo.pk, "formato": "excel"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Informe_MAG", resp["Content-Disposition"])
        self.assertEqual(len(load_workbook(BytesIO(resp.content)).worksheets), 3)

    def test_pantalla_conserva_el_tipo_elegido(self):
        resp = self.client.get(reverse("contenido:reportes"), {"tipo": "ranking"})
        self.assertContains(resp, "Generar ranking")
        self.assertContains(resp, 'value="ranking" checked')
