# -*- coding: utf-8 -*-
"""
Ajustes a las estructuras de la **versión 2** (noviembre 2026).

Parte 1 — Bellas Artes y Oficina TIC salen de la estructura compartida
  "MAG v2 - (Salud, Inclusión, Bellas Artes, Oficina TIC, ...)" porque el indicador
  **Estratégicos** no aplica para ellas:
    - Se crea una estructura v2 nueva (copia del árbol, con criterios) **sin** Estratégicos.
      Su peso se suma al indicador **POAI** y se reparte entre los subindicadores de POAI en
      la misma proporción que ya tenían (13,336/3,334 = 80/20 -> 24/6).
    - Sus evaluaciones (todos los periodos) pasan a la estructura nueva: cada resultado se
      remapea al subindicador equivalente y se recalcula la ponderación con el peso nuevo.
    - La asignación DependenciaModelo de ambas dependencias apunta a la estructura nueva.
    - Los usuarios que tenían asignado un indicador de la estructura original reciben
      también su equivalente en la nueva (PerfilUsuario).
    - La estructura original se renombra sin esas dos dependencias; su árbol no cambia.

Parte 2 — Tránsito v2: se elimina el pilar **Gerencia de los Proyectos** (cascada:
  indicadores, subindicadores, criterios y resultados de ese pilar). Su peso efectivo
  (suma de sus subindicadores; el campo peso del pilar está en 0) se reparte **por partes
  iguales** entre los demás pilares, y dentro de cada pilar se escala de forma proporcional
  a los pesos que ya tenían. Se recalcula la ponderación de los resultados existentes.

Seguridad:
  - Todo corre en UNA transacción. En simulación (por defecto) se ejecuta completo y se
    hace rollback, así el reporte muestra el estado final real sin escribir nada.
  - Aborta si algún resultado de Bellas Artes / Oficina TIC usa Estratégicos, si los pesos
    no cuadran o si falla cualquier verificación final.
  - Idempotente: si una parte ya se aplicó, la omite.

Uso:  python manage.py ajustar_modelos_v2            (simula)
      python manage.py ajustar_modelos_v2 --commit   (escribe)
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from contenido.models import (
    Criterio, DependenciaModelo, Evaluacion, EvaluacionResultado,
    EvaluacionResultadoDetalle, Indicador, ModeloEvaluacion, PerfilUsuario, Pilar,
    Subindicador,
)

# --- Parte 1 ---
MODELO_COMPARTIDO = ("MAG v2 - (Salud, Inclusión, Bellas Artes, Oficina TIC, Unidad del "
                     "Riesgo, Oficina de Turismo y Oficina de Innovación)")
DEPENDENCIAS_SALEN = ["Bellas Artes", "Oficina TIC"]
MODELO_NUEVO = "MAG v2 - (Bellas Artes y Oficina TIC)"
IND_EXCLUIR = "Estratégicos"
IND_RECIBE = "POAI"
# --- Parte 2 ---
MODELO_TRANSITO = "MAG v2 - Transito"
PILAR_QUITAR = "Gerencia de los Proyectos"

CIEN = Decimal("100")


def _q5(v):
    return Decimal(v).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)


def _escalar(pesos, objetivo):
    """Escala {pk: peso} para que sume exactamente `objetivo`, conservando la proporción.
    Redondea a 5 decimales y ajusta el residuo en el último elemento."""
    total = sum(pesos.values())
    if not total:
        raise CommandError("No se puede escalar un grupo de pesos que suma 0.")
    claves = list(pesos)
    nuevos = {k: _q5(pesos[k] * objetivo / total) for k in claves}
    nuevos[claves[-1]] += objetivo - sum(nuevos.values())
    return nuevos


def _recalcular(resultado, peso):
    """Recalcula la ponderación de un resultado con `peso`, igual que la vista de
    diligenciamiento: directo = puntaje*peso/100; mensual = promedio de las ponderaciones
    de cada mes (cada detalle se recalcula también)."""
    ahora = timezone.now()
    detalles = list(EvaluacionResultadoDetalle.objects.filter(resultado=resultado))
    if detalles:
        ponds = []
        for d in detalles:
            p = d.puntaje * peso / CIEN
            ponds.append(p)
            EvaluacionResultadoDetalle.objects.filter(pk=d.pk).update(ponderacion=_q5(p))
        nueva = _q5(sum(ponds) / Decimal(len(ponds)))
    else:
        nueva = _q5(resultado.puntaje * peso / CIEN)
    EvaluacionResultado.objects.filter(pk=resultado.pk).update(
        ponderacion=nueva, actualizado_en=ahora)


def _total(ev_pk):
    return EvaluacionResultado.objects.filter(evaluacion_id=ev_pk).aggregate(
        s=Sum("ponderacion"))["s"] or Decimal("0")


def _suma_pesos_modelo(modelo):
    return Subindicador.objects.filter(
        indicador__pilar__modelo_evaluacion=modelo).aggregate(s=Sum("peso"))["s"] or Decimal("0")


class Command(BaseCommand):
    help = ("Ajustes v2 (nov-2026): estructura propia para Bellas Artes y Oficina TIC sin "
            "Estratégicos, y Tránsito sin el pilar Gerencia de los Proyectos. Simula salvo --commit.")

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true",
                            help="Aplica los cambios. Sin este flag solo simula (rollback).")

    def handle(self, *args, **opts):
        commit = opts["commit"]
        modo = "ESCRITURA (--commit)" if commit else "SIMULACIÓN (se ejecuta y se revierte)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nAjustes estructuras v2 — modo {modo}"))

        with transaction.atomic():
            evals_revisar = []
            evals_revisar += self._parte1()
            evals_revisar += self._parte2()
            self._verificar(evals_revisar)
            if not commit:
                transaction.set_rollback(True)

        if commit:
            self.stdout.write(self.style.SUCCESS("\n>>> Cambios APLICADOS."))
        else:
            self.stdout.write(self.style.WARNING(
                "\n>>> SIMULACIÓN: se revirtió todo, no se escribió nada. Use --commit para aplicar."))

    # ------------------------------------------------------------------ Parte 1
    def _parte1(self):
        self.stdout.write(self.style.MIGRATE_LABEL(
            "\n[Parte 1] Bellas Artes y Oficina TIC -> estructura propia sin Estratégicos"))
        if ModeloEvaluacion.objects.filter(nombre=MODELO_NUEVO).exists():
            self.stdout.write("   Ya aplicada (existe la estructura nueva). Se omite.")
            return []
        try:
            origen = ModeloEvaluacion.objects.get(nombre=MODELO_COMPARTIDO, version=2)
        except ModeloEvaluacion.DoesNotExist:
            raise CommandError(f"No existe la estructura '{MODELO_COMPARTIDO}'.")

        ind_excl = Indicador.objects.get(pilar__modelo_evaluacion=origen, nombre__nombre=IND_EXCLUIR)
        ind_recibe = Indicador.objects.get(pilar__modelo_evaluacion=origen, nombre__nombre=IND_RECIBE)

        asignaciones = list(DependenciaModelo.objects.filter(
            modelo=origen, dependencia__nombre__in=DEPENDENCIAS_SALEN, activo=True)
            .select_related("dependencia"))
        if len(asignaciones) != len(DEPENDENCIAS_SALEN):
            raise CommandError("Las dependencias a mover no tienen asignación activa a la estructura origen.")
        deps = [a.dependencia for a in asignaciones]
        evals = list(Evaluacion.objects.filter(modelo_evaluacion=origen, dependencia__in=deps)
                     .select_related("dependencia", "periodo").order_by("dependencia__nombre", "periodo_id"))

        usan_excl = EvaluacionResultado.objects.filter(
            evaluacion__in=evals, subindicador__indicador=ind_excl).count()
        if usan_excl:
            raise CommandError(f"{usan_excl} resultado(s) de estas dependencias usan '{IND_EXCLUIR}'; se aborta.")

        # Pesos nuevos: POAI recibe el peso de Estratégicos, repartido en proporción.
        peso_ind_recibe = ind_recibe.peso + ind_excl.peso
        subs_recibe = {s.pk: s.peso for s in Subindicador.objects.filter(indicador=ind_recibe).order_by("orden", "pk")}
        nuevos_sub = _escalar(subs_recibe, peso_ind_recibe)

        self.stdout.write(f"   Origen: [{origen.pk}] {origen.nombre}")
        self.stdout.write(f"   Se excluye '{IND_EXCLUIR}' (peso {ind_excl.peso}) -> "
                          f"'{IND_RECIBE}' pasa de {ind_recibe.peso} a {peso_ind_recibe}")
        for s in Subindicador.objects.filter(pk__in=subs_recibe).select_related("nombre"):
            self.stdout.write(f"      {s.nombre.nombre[:60]:60} {s.peso} -> {nuevos_sub[s.pk]}")

        # Clonar el árbol.
        nuevo = ModeloEvaluacion.objects.create(nombre=MODELO_NUEVO, version=origen.version, activo=origen.activo)
        mapa_sub, mapa_ind = {}, {}
        for p in Pilar.objects.filter(modelo_evaluacion=origen).order_by("orden", "pk"):
            np_ = Pilar.objects.create(orden=p.orden, modelo_evaluacion=nuevo, nombre_id=p.nombre_id, peso=p.peso)
            for ind in Indicador.objects.filter(pilar=p).order_by("orden", "pk"):
                if ind.pk == ind_excl.pk:
                    continue
                peso_ind = peso_ind_recibe if ind.pk == ind_recibe.pk else ind.peso
                nind = Indicador.objects.create(orden=ind.orden, pilar=np_, nombre_id=ind.nombre_id, peso=peso_ind)
                mapa_ind[ind.pk] = nind
                for s in Subindicador.objects.filter(indicador=ind).order_by("orden", "pk"):
                    ns = Subindicador.objects.create(
                        orden=s.orden, indicador=nind, nombre_id=s.nombre_id,
                        peso=nuevos_sub.get(s.pk, s.peso), tipo_calculo=s.tipo_calculo)
                    mapa_sub[s.pk] = ns
                    for c in Criterio.objects.filter(subindicador=s).order_by("orden", "pk"):
                        Criterio.objects.create(orden=c.orden, subindicador=ns, nombre=c.nombre, rango=c.rango)
        self.stdout.write(self.style.SUCCESS(
            f"   Creada: [{nuevo.pk}] {nuevo.nombre} | suma pesos subindicadores = {_suma_pesos_modelo(nuevo)}"))

        # Renombrar el origen (sin las dependencias que salen).
        nombre_origen = origen.nombre
        for d in DEPENDENCIAS_SALEN:
            nombre_origen = nombre_origen.replace(f"{d}, ", "")
        ModeloEvaluacion.objects.filter(pk=origen.pk).update(nombre=nombre_origen, actualizado_en=timezone.now())
        self.stdout.write(f"   Origen renombrado: {nombre_origen}")

        # Reasignar dependencias.
        DependenciaModelo.objects.filter(pk__in=[a.pk for a in asignaciones]).update(
            modelo=nuevo, actualizado_en=timezone.now())
        self.stdout.write(f"   Asignación activa -> estructura nueva: {', '.join(d.nombre for d in deps)}")

        # Migrar evaluaciones.
        antes = {e.pk: _total(e.pk) for e in evals}
        n_res = 0
        for ev in evals:
            for r in EvaluacionResultado.objects.filter(evaluacion=ev):
                dest = mapa_sub[r.subindicador_id]
                EvaluacionResultado.objects.filter(pk=r.pk).update(subindicador=dest)
                n_res += 1
                if dest.peso != r.subindicador.peso:
                    r.refresh_from_db()
                    _recalcular(r, dest.peso)
            Evaluacion.objects.filter(pk=ev.pk).update(modelo_evaluacion=nuevo, actualizado_en=timezone.now())
        self.stdout.write(f"   Evaluaciones migradas: {len(evals)} | resultados remapeados: {n_res}")
        for ev in evals:
            self.stdout.write(f"      [{ev.pk}] {ev.dependencia.nombre:14} {ev.periodo.nombre:28} "
                              f"total {antes[ev.pk]:.5f} -> {_total(ev.pk):.5f}")

        # Asignaciones de usuarios por indicador.
        for perfil in PerfilUsuario.objects.filter(indicadores__in=list(mapa_ind)).distinct().select_related("usuario"):
            nuevos = [mapa_ind[i.pk] for i in perfil.indicadores.filter(pk__in=list(mapa_ind))]
            perfil.indicadores.add(*nuevos)
            self.stdout.write(f"   Usuario {perfil.usuario.username}: + {', '.join(str(i.nombre) for i in nuevos)}")

        return [e.pk for e in evals]

    # ------------------------------------------------------------------ Parte 2
    def _parte2(self):
        self.stdout.write(self.style.MIGRATE_LABEL(f"\n[Parte 2] Tránsito: quitar '{PILAR_QUITAR}'"))
        try:
            modelo = ModeloEvaluacion.objects.get(nombre=MODELO_TRANSITO, version=2)
        except ModeloEvaluacion.DoesNotExist:
            raise CommandError(f"No existe la estructura '{MODELO_TRANSITO}'.")
        pilar = Pilar.objects.filter(modelo_evaluacion=modelo, nombre__nombre=PILAR_QUITAR).first()
        if pilar is None:
            self.stdout.write("   Ya aplicada (el pilar no existe). Se omite.")
            return []

        total_antes = _suma_pesos_modelo(modelo)
        peso_efectivo = Subindicador.objects.filter(indicador__pilar=pilar).aggregate(s=Sum("peso"))["s"] or Decimal("0")
        restantes = list(Pilar.objects.filter(modelo_evaluacion=modelo).exclude(pk=pilar.pk).order_by("orden", "pk"))
        cuota = peso_efectivo / len(restantes)
        evals = list(Evaluacion.objects.filter(modelo_evaluacion=modelo).select_related("periodo").order_by("periodo_id"))
        antes = {e.pk: _total(e.pk) for e in evals}

        self.stdout.write(f"   Estructura: [{modelo.pk}] {modelo.nombre} | suma pesos actual = {total_antes}")
        self.stdout.write(f"   Pilar a quitar: [{pilar.pk}] peso campo={pilar.peso} | peso efectivo (subindicadores)={peso_efectivo}")
        self.stdout.write(f"   Cuota por pilar restante: {peso_efectivo} / {len(restantes)} = {cuota}")

        # Lo que se elimina en cascada.
        res_del = EvaluacionResultado.objects.filter(subindicador__indicador__pilar=pilar).select_related(
            "evaluacion__periodo", "subindicador__nombre")
        for r in res_del:
            self.stdout.write(self.style.WARNING(
                f"      elimina resultado: {r.evaluacion.periodo.nombre:28} {r.subindicador.nombre.nombre[:45]:45} "
                f"puntaje={r.puntaje} pond={r.ponderacion}"))
        usuarios = list(PerfilUsuario.objects.filter(indicadores__pilar=pilar).distinct()
                        .values_list("usuario__username", flat=True))
        if usuarios:
            self.stdout.write(f"      pierden la asignación del indicador: {', '.join(usuarios)}")
        pilar.delete()

        # Redistribuir pesos.
        cambios = {}
        for p in restantes:
            objetivo = p.peso + cuota
            subs = list(Subindicador.objects.filter(indicador__pilar=p).order_by("indicador__orden", "indicador_id", "orden", "pk"))
            nuevos = _escalar({s.pk: s.peso for s in subs}, objetivo)
            self.stdout.write(f"   Pilar '{p.nombre}': {p.peso} -> {objetivo}")
            Pilar.objects.filter(pk=p.pk).update(peso=objetivo, actualizado_en=timezone.now())
            for s in subs:
                if nuevos[s.pk] != s.peso:
                    cambios[s.pk] = nuevos[s.pk]
                Subindicador.objects.filter(pk=s.pk).update(peso=nuevos[s.pk], actualizado_en=timezone.now())
            for ind in Indicador.objects.filter(pilar=p).order_by("orden", "pk"):
                peso_ind = sum(nuevos[s.pk] for s in subs if s.indicador_id == ind.pk)
                self.stdout.write(f"      indicador '{str(ind.nombre)[:55]}': {ind.peso} -> {peso_ind}")
                Indicador.objects.filter(pk=ind.pk).update(peso=peso_ind, actualizado_en=timezone.now())
            for s in subs:
                self.stdout.write(f"         sub '{s.nombre.nombre[:52]}': {s.peso} -> {nuevos[s.pk]}")

        total_despues = _suma_pesos_modelo(modelo)
        if total_despues != CIEN:
            raise CommandError(f"Los pesos de Tránsito suman {total_despues}, no 100; se aborta.")

        for r in EvaluacionResultado.objects.filter(evaluacion__in=evals, subindicador_id__in=list(cambios)):
            _recalcular(r, cambios[r.subindicador_id])
        self.stdout.write(f"   Suma pesos final = {total_despues}")
        for ev in evals:
            self.stdout.write(f"      [{ev.pk}] Tránsito {ev.periodo.nombre:28} total {antes[ev.pk]:.5f} -> {_total(ev.pk):.5f}")
        return [e.pk for e in evals]

    # ------------------------------------------------------------------ Verificación
    def _verificar(self, evals_pk):
        self.stdout.write(self.style.MIGRATE_LABEL("\n[Verificación]"))
        errores = []
        for r in EvaluacionResultado.objects.filter(evaluacion_id__in=evals_pk).select_related(
                "subindicador__indicador__pilar", "evaluacion"):
            if r.subindicador.indicador.pilar.modelo_evaluacion_id != r.evaluacion.modelo_evaluacion_id:
                errores.append(f"resultado {r.pk}: subindicador fuera del modelo de su evaluación")
            peso = r.subindicador.peso
            det = list(EvaluacionResultadoDetalle.objects.filter(resultado=r))
            if det:
                esperado = _q5(sum(d.puntaje * peso / CIEN for d in det) / Decimal(len(det)))
                for d in det:
                    if d.ponderacion != _q5(d.puntaje * peso / CIEN):
                        errores.append(f"detalle {d.pk}: ponderación no cuadra con el peso")
            else:
                esperado = _q5(r.puntaje * peso / CIEN)
            if r.ponderacion != esperado:
                errores.append(f"resultado {r.pk}: ponderación {r.ponderacion} != esperado {esperado}")
        for m in ModeloEvaluacion.objects.filter(version=2, activo=True):
            s = _suma_pesos_modelo(m)
            marca = "" if s == CIEN else "   <-- no suma 100"
            self.stdout.write(f"   pesos [{m.pk}] {m.nombre[:70]:70} = {s}{marca}")
        if errores:
            for e in errores:
                self.stdout.write(self.style.ERROR(f"   {e}"))
            raise CommandError(f"{len(errores)} error(es) de verificación; se revierte todo.")
        self.stdout.write(self.style.SUCCESS(
            f"   OK: {EvaluacionResultado.objects.filter(evaluacion_id__in=evals_pk).count()} resultados "
            "verificados (modelo correcto y ponderación = puntaje x peso / 100)."))
