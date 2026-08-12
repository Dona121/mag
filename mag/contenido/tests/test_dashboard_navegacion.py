"""El cascarón (dashboard interno y reporte público) arrastra los filtros del
query string al navegar entre secciones (IMAG / Desempeño / Ranking / Variaciones).

Regresión: antes las pestañas usaban `{% url %}` sin adjuntar `request.GET`, así que
al cambiar de sección se perdían los filtros. Ahora cada pestaña lleva
`?{{ request.GET.urlencode }}` (con guard para no dejar un "?" colgando sin filtros).
"""
from django.urls import reverse

from .base import BaseMagTestCase


class ArrastreFiltrosTests(BaseMagTestCase):
    def test_reporte_publico_arrastra_filtros_en_pestanas(self):
        resp = self.client.get(
            reverse("contenido:reporte_publico"), {"vigencia": "2026", "foo": "bar"}
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # las pestañas a las otras secciones incluyen el query string actual
        for name in ("reporte_desempeno", "reporte_ranking", "reporte_variaciones"):
            href = reverse("contenido:" + name)
            self.assertIn('href="{}?'.format(href), html, name)
        self.assertIn("vigencia=2026", html)
        self.assertIn("foo=bar", html)

    def test_dashboard_interno_arrastra_filtros_en_pestanas(self):
        self.login_admin()
        resp = self.client.get(
            reverse("contenido:dashboard_imag"), {"vigencia": "2026", "foo": "bar"}
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        for name in ("dashboard_desempeno", "dashboard_ranking", "dashboard_variaciones"):
            href = reverse("contenido:" + name)
            self.assertIn('href="{}?'.format(href), html, name)
        self.assertIn("vigencia=2026", html)
        self.assertIn("foo=bar", html)

    def test_ranking_pestanas_de_categoria_conservan_los_demas_filtros(self):
        # En Ranking, las pestañas de categoría (?categoria=X) deben preservar
        # versión/vigencia/periodo/pilar (via {% querystring %}), no reiniciarlos.
        resp = self.client.get(
            reverse("contenido:reporte_ranking"), {"vigencia": "2026", "foo": "bar"}
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # la pestaña "Todas las categorías" cambia categoria pero mantiene lo demás
        self.assertIn("categoria=todas", html)
        self.assertIn("vigencia=2026", html)
        self.assertIn("foo=bar", html)
        # ya no quedan enlaces que reinicien el query string a solo categoria
        self.assertNotIn('href="?categoria=', html)

    def test_sin_filtros_no_deja_interrogacion_colgando(self):
        # Sin query string, el href de la pestaña queda limpio (sin "?").
        resp = self.client.get(reverse("contenido:reporte_publico"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        href = reverse("contenido:reporte_ranking")
        self.assertIn('href="{}"'.format(href), html)
        self.assertNotIn('href="{}?"'.format(href), html)
