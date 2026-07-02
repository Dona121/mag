# -*- coding: utf-8 -*-
"""
Divide las estructuras de la **versión 1** en una estructura por vigencia, para que un
subindicador que solo apareció en un año no confunda en los demás.

Caso concreto: el subindicador "Estratégicos › Resultados 70%…" (SubindicadorCategoria
id 28) existe en varias estructuras v1 pero **solo se evaluó en 2026**; al consultar 2025
aparecía vacío. Este command separa cada estructura afectada en dos `ModeloEvaluacion`
(ambos `version=1`, así el filtro de versión sigue mostrando "Versión 1"):

  - `MAG v1-2025 - X`: copia del árbol **sin** el/los subindicadores objetivo.
  - la estructura original se renombra `MAG v1-<otras vigencias> - X` (conserva el árbol
    completo, con el subindicador).

Luego reasigna las evaluaciones de la vigencia separada a la copia y **remapea sus
resultados** al subindicador equivalente. No se pierde ningún dato y, como ese
subindicador aportaba 0 en 2025, **ningún cálculo cambia**.

Fase 2 (limpieza de fantasmas): tras dividir, en cada estructura v1 de **una sola
vigencia** elimina los subindicadores que quedaron con **0 resultados**. Esto quita el
caso espejo: el subindicador que solo aplicaba a 2025 (cat 17 "Indice de Cumplimiento…")
quedó vacío en las estructuras v1-2026 y se elimina; a la inversa, cat 28 ya se excluyó de
las v1-2025 en la fase 1. Es idempotente y no toca estructuras multi-vigencia (Bellas
Artes). Se puede desactivar con --no-limpiar. Antes de borrar revalida que el subindicador
no tenga ningún resultado.

Reglas de seguridad:
  - Solo divide una estructura si (a) contiene el/los subindicadores objetivo, (b) tiene
    evaluaciones en la vigencia a separar y (c) tiene evaluaciones en otra vigencia. Así
    Bellas Artes (que no tiene ese subindicador) queda fuera y el command es idempotente
    (una estructura ya dividida tiene una sola vigencia y no se vuelve a tocar).
  - Si algún resultado de la vigencia a separar usa realmente el subindicador objetivo
    (es decir, sí se evaluó ese año), aborta: sería un error quitarlo.
  - Usa `.update()` para saltar el `clean()` de Evaluacion (que bloquea cambiar el modelo)
    y el de EvaluacionResultado, dentro de una transacción.

Por defecto SIMULA (dry-run). Use --commit para aplicar.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from contenido.models import (
    Criterio, Evaluacion, EvaluacionResultado, Indicador, ModeloEvaluacion,
    Pilar, Subindicador, SubindicadorCategoria,
)

VERSION = 1


def _clonar_sin_categorias(modelo, excluir_cats, nuevo_nombre):
    """Clona el árbol (Pilar→Indicador→Subindicador→Criterio) de `modelo` en un
    ModeloEvaluacion nuevo, omitiendo los subindicadores cuya categoría esté en
    `excluir_cats`. Devuelve (modelo_nuevo, {sub_old_pk: sub_new})."""
    nuevo = ModeloEvaluacion.objects.create(
        nombre=nuevo_nombre, version=modelo.version, activo=modelo.activo)
    mapa = {}
    for p in Pilar.objects.filter(modelo_evaluacion=modelo).order_by("orden", "pk"):
        np = Pilar.objects.create(
            orden=p.orden, modelo_evaluacion=nuevo, nombre_id=p.nombre_id, peso=p.peso)
        for ind in Indicador.objects.filter(pilar=p).order_by("orden", "pk"):
            nind = Indicador.objects.create(
                orden=ind.orden, pilar=np, nombre_id=ind.nombre_id, peso=ind.peso)
            for s in Subindicador.objects.filter(indicador=ind).order_by("orden", "pk"):
                if s.nombre_id in excluir_cats:
                    continue
                ns = Subindicador.objects.create(
                    orden=s.orden, indicador=nind, nombre_id=s.nombre_id,
                    peso=s.peso, tipo_calculo=s.tipo_calculo)
                for c in Criterio.objects.filter(subindicador=s).order_by("orden", "pk"):
                    Criterio.objects.create(
                        orden=c.orden, subindicador=ns, nombre=c.nombre, rango=c.rango)
                mapa[s.pk] = ns
    return nuevo, mapa


def _base_nombre(nombre):
    """Nombre 'limpio' de la estructura, sin el prefijo de versión."""
    base = nombre
    for pref in ("MAG v1 - ", "MAG v1- ", "MAG v1-", "MAG v1 "):
        if base.startswith(pref):
            return base[len(pref):].strip()
    return base.strip()


class Command(BaseCommand):
    help = ("Divide las estructuras v1 en una por vigencia (separa el subindicador que "
            "solo apareció en un año). Simula salvo --commit.")

    def add_arguments(self, parser):
        parser.add_argument("--vigencia", type=int, default=2025,
                            help="Vigencia a separar (la que NO debe tener el subindicador). Def: 2025")
        parser.add_argument("--categoria", type=int, nargs="+", default=[28],
                            help="IDs de SubindicadorCategoria que NO deben existir en esa vigencia. Def: 28")
        parser.add_argument("--no-limpiar", action="store_true",
                            help="No ejecuta la fase de limpieza de subindicadores fantasma "
                                 "(los que quedan con 0 resultados en estructuras de una sola vigencia).")
        parser.add_argument("--commit", action="store_true",
                            help="Aplica los cambios. Sin este flag solo simula.")

    def handle(self, *args, **opts):
        vig = opts["vigencia"]
        cats = set(opts["categoria"])
        commit = opts["commit"]
        limpiar = not opts["no_limpiar"]

        modo = "ESCRITURA (--commit)" if commit else "SIMULACIÓN (dry-run)"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nDividir estructuras v{VERSION} por vigencia — modo {modo}"))

        nombres_cat = {c.pk: c.nombre for c in SubindicadorCategoria.objects.filter(pk__in=cats)}
        faltan = cats - set(nombres_cat)
        if faltan:
            raise CommandError(f"No existen SubindicadorCategoria con id: {sorted(faltan)}")
        self.stdout.write(f"Vigencia a separar: {vig}")
        self.stdout.write("Subindicador(es) objetivo (se excluyen de esa vigencia):")
        for pk, nom in nombres_cat.items():
            self.stdout.write(f"   [cat {pk}] {nom[:70]}")

        # --- Planificación (solo lectura) ---
        a_dividir = []   # dicts con lo necesario para ejecutar
        blockers = []
        self.stdout.write(self.style.MIGRATE_LABEL("\nEstructuras v1:"))
        for M in ModeloEvaluacion.objects.filter(version=VERSION).order_by("pk"):
            tiene = Subindicador.objects.filter(
                indicador__pilar__modelo_evaluacion=M, nombre_id__in=cats).exists()
            vigs = set(v for v in Evaluacion.objects.filter(modelo_evaluacion=M)
                       .values_list("periodo__vigencia", flat=True) if v is not None)
            evals_vig = Evaluacion.objects.filter(modelo_evaluacion=M, periodo__vigencia=vig)
            n_vig = evals_vig.count()
            otras = sorted(v for v in vigs if v != vig)

            if not (tiene and n_vig and otras):
                razon = ("no tiene el subindicador" if not tiene
                         else f"no tiene evals {vig}" if not n_vig
                         else "no tiene otra vigencia")
                self.stdout.write(f"   SIN CAMBIO  {M.nombre[:44]:44}  ({razon})")
                continue

            usados = EvaluacionResultado.objects.filter(
                evaluacion__in=evals_vig, subindicador__nombre_id__in=cats).count()
            if usados:
                blockers.append((M.nombre, usados))
            n_remap = EvaluacionResultado.objects.filter(evaluacion__in=evals_vig).count()
            base = _base_nombre(M.nombre)
            a_dividir.append({"modelo_id": M.pk, "base": base, "otras": otras,
                              "n_vig": n_vig, "n_remap": n_remap})
            self.stdout.write(self.style.SUCCESS(
                f"   DIVIDIR     {M.nombre[:44]:44}  evals{vig}={n_vig} remap={n_remap} "
                f"-> v1-{vig} + v1-{'-'.join(map(str, otras))}"))

        if blockers:
            self.stdout.write(self.style.ERROR(
                "\n>>> ABORTA: hay resultados que SÍ usan el subindicador objetivo en "
                f"{vig} (quitarlo perdería datos):"))
            for nom, n in blockers:
                self.stdout.write(f"   {nom}: {n} resultado(s)")
            raise CommandError("Revise los subindicadores objetivo o la vigencia.")

        self.stdout.write(self.style.HTTP_INFO(
            f"\nTOTAL estructuras a dividir: {len(a_dividir)} | "
            f"evaluaciones a reasignar: {sum(d['n_vig'] for d in a_dividir)} | "
            f"resultados a remapear: {sum(d['n_remap'] for d in a_dividir)}"))

        # --- Fase 2: limpieza de subindicadores fantasma (planificación, solo lectura) ---
        if limpiar:
            limpieza = self._planear_limpieza()
            self.stdout.write(self.style.MIGRATE_LABEL(
                "\nLimpieza de subindicadores fantasma (0 resultados, en estructuras de una sola vigencia):"))
            if limpieza:
                for M, unica_vig, subs in limpieza:
                    self.stdout.write(f"   {M.nombre[:44]:44} (vig {unica_vig}) -> quitar {len(subs)}:")
                    for s in subs:
                        self.stdout.write(self.style.WARNING(
                            f"       [{s.pk}] {s.indicador.pilar.nombre.nombre} > "
                            f"{s.indicador.nombre.nombre} > {s.nombre.nombre[:50]}"))
            else:
                self.stdout.write("   (nada que limpiar)")
            self.stdout.write(self.style.HTTP_INFO(
                f"TOTAL subindicadores fantasma a eliminar: {sum(len(s) for _m, _v, s in limpieza)}"))
            if a_dividir:
                self.stdout.write(self.style.WARNING(
                    "   Nota: hay divisiones pendientes; la limpieza definitiva se recalcula "
                    "tras dividir (este preview refleja el estado actual de la BD)."))

        if not commit:
            self.stdout.write(self.style.WARNING(
                "\n>>> SIMULACIÓN: no se escribió nada. Use --commit para aplicar."))
            return

        self._ejecutar(a_dividir, cats, vig, limpiar)
        self.stdout.write(self.style.SUCCESS("\n>>> Listo (división + limpieza)."))

    def _planear_limpieza(self):
        """Estructuras v1 de UNA sola vigencia con subindicadores de 0 resultados (fantasmas
        que quedan tras dividir: p. ej. cat 17, que solo aplicaba a 2025, en las v1-2026).
        Devuelve [(modelo, vigencia_unica, [subindicadores])]."""
        plan = []
        for M in ModeloEvaluacion.objects.filter(version=VERSION).order_by("pk"):
            vigs = set(v for v in Evaluacion.objects.filter(modelo_evaluacion=M)
                       .values_list("periodo__vigencia", flat=True) if v is not None)
            if len(vigs) != 1:
                continue  # multi-vigencia: no se puede decidir con seguridad (p. ej. Bellas Artes)
            subs = list(
                Subindicador.objects
                .filter(indicador__pilar__modelo_evaluacion=M)
                .annotate(n=Count("evaluacionresultado")).filter(n=0)
                .select_related("nombre", "indicador__nombre", "indicador__pilar__nombre")
                .order_by("indicador__pilar__orden", "indicador__orden", "orden"))
            if subs:
                plan.append((M, next(iter(vigs)), subs))
        return plan

    @transaction.atomic
    def _ejecutar(self, a_dividir, cats, vig, limpiar):
        # Fase 1: dividir por vigencia.
        for d in a_dividir:
            M = ModeloEvaluacion.objects.get(pk=d["modelo_id"])
            nombre_2025 = f"MAG v1-{vig} - {d['base']}"
            nombre_orig = f"MAG v1-{'-'.join(map(str, d['otras']))} - {d['base']}"

            nuevo, mapa = _clonar_sin_categorias(M, cats, nombre_2025)
            ModeloEvaluacion.objects.filter(pk=M.pk).update(nombre=nombre_orig)

            evals_vig = Evaluacion.objects.filter(modelo_evaluacion=M, periodo__vigencia=vig)
            for ev in evals_vig:
                for r in EvaluacionResultado.objects.filter(evaluacion=ev):
                    dest = mapa.get(r.subindicador_id)
                    if dest is None:
                        # No debería pasar (blocker ya lo descartó); por seguridad, aborta.
                        raise CommandError(
                            f"Resultado {r.pk} usa un subindicador excluido; se aborta.")
                    EvaluacionResultado.objects.filter(pk=r.pk).update(subindicador=dest)
                Evaluacion.objects.filter(pk=ev.pk).update(modelo_evaluacion=nuevo)

        # Fase 2: limpieza de fantasmas (se recalcula tras dividir).
        if limpiar:
            for M, _unica_vig, subs in self._planear_limpieza():
                for s in subs:
                    if EvaluacionResultado.objects.filter(subindicador=s).exists():
                        raise CommandError(
                            f"Subindicador {s.pk} tiene resultados; no se elimina (aborta).")
                    s.delete()  # cascada elimina sus Criterio
