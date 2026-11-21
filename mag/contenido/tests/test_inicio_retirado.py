"""La portada "Inicio" se retiró del módulo General: la raíz del panel (`/`, destino del
login) lleva directo al Dashboard y el menú ya no muestra "Inicio"."""
from django.urls import reverse

from .base import PASSWORD, BaseMagTestCase


class InicioRetiradoTests(BaseMagTestCase):
    def test_raiz_redirige_al_dashboard(self):
        self.login_admin()
        resp = self.client.get(reverse("contenido:dashboard"))
        self.assertRedirects(resp, reverse("contenido:dashboard_imag"))

    def test_login_lleva_al_dashboard(self):
        resp = self.client.post(
            reverse("contenido:login"),
            {"username": "admin", "password": PASSWORD},
            follow=True,
        )
        self.assertEqual(resp.redirect_chain[-1][0], reverse("contenido:dashboard_imag"))

    def test_menu_sin_inicio(self):
        self.login_admin()
        resp = self.client.get(reverse("contenido:evaluacion_list"))
        html = resp.content.decode()
        self.assertNotIn('<span class="label">Inicio</span>', html)
        self.assertIn('<span class="label">Dashboard</span>', html)
        # La ruta de navegación ya no cae en "Inicio" por defecto.
        self.assertNotIn("</strong> - Inicio", html)

    def test_evaluador_tambien_entra_al_dashboard(self):
        self.crear_evaluador()
        self.client.login(username="evaluador", password=PASSWORD)
        resp = self.client.get("/", follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.redirect_chain[-1][0], reverse("contenido:dashboard_imag"))

    def test_sin_sesion_pide_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("contenido:login"), resp["Location"])
