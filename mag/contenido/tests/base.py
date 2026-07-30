"""Fixtures compartidas por la suite.

`BaseMagTestCase` arma una estructura minima pero completa que refleja el
arbol real de la app y las reglas de la BD (constraints y clean()):

    ModeloEvaluacion(v1, activo)
      Pilar -> Indicador -> Subindicador(directo) + Subindicador(mensual)
                              Criterio
    Dependencia --(DependenciaModelo activo)--> Modelo
    Categoria (clasificacion de dependencia)  +  Periodo(activo, con meses)
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase

from contenido.models import (
    Categoria,
    Criterio,
    Dependencia,
    DependenciaModelo,
    Evaluacion,
    Indicador,
    IndicadorCategoria,
    ModeloEvaluacion,
    Periodo,
    Pilar,
    PilarCategoria,
    Subindicador,
    SubindicadorCategoria,
)
from contenido.roles import GRUPO_EVALUADOR

PASSWORD = "clave-de-prueba-123"


class BaseMagTestCase(TestCase):
    def setUp(self):
        # --- Usuarios
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", PASSWORD
        )

        # --- Modelo + estructura
        self.modelo = ModeloEvaluacion.objects.create(
            nombre="Modelo de Prueba", version=1, activo=True
        )
        self.pcat = PilarCategoria.objects.create(nombre="Pilar A")
        self.icat = IndicadorCategoria.objects.create(nombre="Indicador A")
        self.scat_directo = SubindicadorCategoria.objects.create(nombre="Sub Directo")
        self.scat_mensual = SubindicadorCategoria.objects.create(nombre="Sub Mensual")

        self.pilar = Pilar.objects.create(
            orden=1, modelo_evaluacion=self.modelo, nombre=self.pcat, peso=Decimal("100")
        )
        self.indicador = Indicador.objects.create(
            orden=1, pilar=self.pilar, nombre=self.icat, peso=Decimal("100")
        )
        self.sub_directo = Subindicador.objects.create(
            orden=1, indicador=self.indicador, nombre=self.scat_directo,
            peso=Decimal("10"), tipo_calculo="directo",
        )
        self.sub_mensual = Subindicador.objects.create(
            orden=2, indicador=self.indicador, nombre=self.scat_mensual,
            peso=Decimal("10"), tipo_calculo="mensual",
        )
        self.criterio = Criterio.objects.create(
            orden=1, subindicador=self.sub_directo, nombre="Cumple", rango="0-100"
        )

        # --- Dependencia con modelo activo asignado
        self.dep = Dependencia.objects.create(nombre="Secretaria de Prueba")
        DependenciaModelo.objects.create(
            modelo=self.modelo, dependencia=self.dep, activo=True
        )

        # --- Categoria (clasificacion) y Periodo con meses en el nombre
        self.categoria = Categoria.objects.create(orden=1, nombre="Despacho")
        self.periodo = Periodo.objects.create(
            orden=1, vigencia=2026, nombre="Enero - Febrero - Marzo",
            umbral=Decimal("60.00"), activo=True, publico=False,
        )

    # ------------------------------------------------------------------ helpers
    def login_admin(self):
        self.assertTrue(self.client.login(username="admin", password=PASSWORD))

    def crear_evaluador(self, indicadores=None):
        """Crea un usuario del grupo Evaluador (con PerfilUsuario opcional)."""
        from contenido.models import PerfilUsuario

        user = User.objects.create_user("evaluador", password=PASSWORD)
        grupo, _ = Group.objects.get_or_create(name=GRUPO_EVALUADOR)
        user.groups.add(grupo)
        perfil = PerfilUsuario.objects.create(usuario=user)
        if indicadores:
            perfil.indicadores.set(indicadores)
        return user

    def crear_evaluacion(self):
        return Evaluacion.objects.create(
            periodo=self.periodo, dependencia=self.dep,
            modelo_evaluacion=self.modelo, categoria=self.categoria,
        )
