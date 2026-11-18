"""IMAG de una categoría que mezcla estructuras con pesos de pilar distintos.

Caso real: en la Categoría 3 (v2) Tránsito no tiene "Gerencia de los Proyectos" y repartió
ese peso, así que su "Reportes de Información" pesa 40 mientras en el resto de la categoría
pesa 30. Promediar PUNTOS mezclaba escalas e inflaba el pilar (podía pasar del 100 %).
Ahora cada dependencia se lleva al peso de referencia (el más frecuente) conservando su %
de cumplimiento. En categorías homogéneas el resultado no cambia.
"""
from decimal import Decimal

from django.test import TestCase

from contenido.models import (
    Categoria, Dependencia, Evaluacion, EvaluacionResultado, Indicador,
    IndicadorCategoria, ModeloEvaluacion, Periodo, Pilar, PilarCategoria, Subindicador,
    SubindicadorCategoria,
)
from contenido.views import _promedios_por_pilar, _puntajes_por_dependencia

D = Decimal
VERSION = 2


class EstructurasMixtasTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(orden=1, nombre="Categoría 3")
        self.periodo = Periodo.objects.create(orden=1, vigencia=2026, nombre="Abril - Mayo - Junio",
                                              umbral=D("60"), activo=True)
        self.pX = PilarCategoria.objects.create(nombre="Reportes")
        self.pY = PilarCategoria.objects.create(nombre="Metas")
        self.icat = IndicadorCategoria.objects.create(nombre="Ind")
        self.scat = SubindicadorCategoria.objects.create(nombre="Sub")
        # Estructura estándar (2 dependencias): X=30, Y=70. Estructura "Tránsito" (1): X=40, Y=60.
        self.estandar = self._estructura("Estándar", D("30"), D("70"))
        self.transito = self._estructura("Tránsito", D("40"), D("60"))

    def _estructura(self, nombre, peso_x, peso_y):
        m = ModeloEvaluacion.objects.create(nombre=nombre, version=VERSION, activo=True)
        subs = {}
        for orden, (pcat, peso) in enumerate(((self.pX, peso_x), (self.pY, peso_y)), start=1):
            p = Pilar.objects.create(orden=orden, modelo_evaluacion=m, nombre=pcat, peso=peso)
            i = Indicador.objects.create(orden=1, pilar=p, nombre=self.icat, peso=peso)
            subs[pcat.pk] = Subindicador.objects.create(orden=1, indicador=i, nombre=self.scat,
                                                        peso=peso, tipo_calculo="directo")
        return m, subs

    def _evaluar(self, nombre_dep, estructura, pct_x, pct_y):
        """Crea la evaluación de una dependencia con el % de cumplimiento de cada pilar."""
        modelo, subs = estructura
        dep = Dependencia.objects.create(nombre=nombre_dep)
        ev = Evaluacion.objects.create(periodo=self.periodo, dependencia=dep,
                                       modelo_evaluacion=modelo, categoria=self.cat)
        for pcat, pct in ((self.pX, pct_x), (self.pY, pct_y)):
            sub = subs[pcat.pk]
            EvaluacionResultado.objects.create(evaluacion=ev, subindicador=sub, puntaje=D(pct),
                                               ponderacion=D(pct) * sub.peso / 100, observaciones="")
        return dep

    def _promedios(self):
        return _promedios_por_pilar(self.cat, VERSION, self.periodo)

    def test_pilar_no_supera_su_peso_con_estructura_que_pondera_mas(self):
        # Todas cumplen el 100 % de X: antes el promedio daba (30+30+40)/3 = 33,33 sobre 30.
        self._evaluar("Salud", self.estandar, 100, 0)
        self._evaluar("Interior", self.estandar, 100, 0)
        self._evaluar("Tránsito", self.transito, 100, 0)
        x = self._promedios()[self.pX.pk]
        self.assertEqual(x["peso"], D("30"))          # peso de referencia = el más frecuente
        self.assertEqual(x["promedio"], D("30"))      # 100 % de cumplimiento, no 111 %

    def test_imag_mixto_promedia_porcentajes(self):
        self._evaluar("Salud", self.estandar, 100, 50)     # X 100 %, Y 50 %
        self._evaluar("Interior", self.estandar, 50, 100)  # X 50 %,  Y 100 %
        self._evaluar("Tránsito", self.transito, 25, 50)   # X 25 %,  Y 50 %
        prom = self._promedios()
        # X: (100+50+25)/3 % de 30 = 17,5 ; Y: (50+100+50)/3 % de 70 = 46,666…
        self.assertEqual(prom[self.pX.pk]["promedio"], D("17.5"))
        self.assertAlmostEqual(float(prom[self.pY.pk]["promedio"]), 70 * 200 / 300, places=6)
        imag = sum(p["promedio"] for p in prom.values())
        self.assertLessEqual(imag, sum(p["peso"] for p in prom.values()))  # nunca > máximo

    def test_categoria_homogenea_no_cambia(self):
        # Solo la estructura estándar: debe dar exactamente el promedio simple de puntos.
        self._evaluar("Salud", self.estandar, 80, 40)
        self._evaluar("Interior", self.estandar, 60, 20)
        prom = self._promedios()
        self.assertEqual(prom[self.pX.pk]["promedio"], (D("24") + D("18")) / 2)
        self.assertEqual(prom[self.pY.pk]["promedio"], (D("28") + D("14")) / 2)
        self.assertEqual(prom[self.pX.pk]["peso"], D("30"))

    def test_ranking_por_pilar_compara_en_la_misma_escala(self):
        salud = self._evaluar("Salud", self.estandar, 100, 0)       # 30 de 30
        transito = self._evaluar("Tránsito", self.transito, 75, 0)  # 30 de 40 = 75 %
        self._evaluar("Interior", self.estandar, 50, 0)
        pilar_x = Pilar.objects.filter(nombre=self.pX).first()
        pun = _puntajes_por_dependencia(self.cat, VERSION, self.periodo, pilar_x)
        self.assertEqual(pun[salud.pk][1], D("30"))
        self.assertEqual(pun[transito.pk][1], D("22.5"))  # 75 % de 30, no 30 "puntos" empatados
        # Sin filtro de pilar, el total es el IMAG propio de cada dependencia (sobre 100).
        total = _puntajes_por_dependencia(self.cat, VERSION, self.periodo)
        self.assertEqual(total[transito.pk][1], D("30"))
