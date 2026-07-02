"""
Vistas de la aplicacion.

Permisos por indicador (PerfilUsuario):
  - Todos los usuarios autenticados pueden VER toda la jerarquia y los
    resultados de cualquier evaluacion.
  - Solo pueden EDITAR los subindicadores cuyo `indicador` este asignado en
    su PerfilUsuario.indicadores.
  - Los superusers pueden editar todo.

Logica de ponderacion:
  - DIRECTO:
      EvaluacionResultado.puntaje      = puntaje
      EvaluacionResultado.ponderacion  = puntaje * peso_sub / 100
  - MENSUAL (con N meses diligenciados):
      detalle.ponderacion              = puntaje_mes * peso_sub / 100
      parent.puntaje                   = promedio(puntaje_mes)
      parent.ponderacion               = promedio(detalle.ponderacion)
  Todos los valores se cuantizan a 2 decimales antes de persistir.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from unicodedata import normalize

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Min, Prefetch, Sum
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views.generic import CreateView, ListView, UpdateView

from .models import (
    Categoria, Criterio, Dependencia, DependenciaModelo,
    Evaluacion, EvaluacionResultado, EvaluacionResultadoDetalle,
    Indicador, IndicadorCategoria, Meses, ModeloEvaluacion, PerfilUsuario,
    Periodo, Pilar, PilarCategoria, Subindicador, SubindicadorCategoria,
)


# ============================================================== Utilidades
TWO = Decimal("0.01")
FIVE = Decimal("0.00001")


def _q2(value):
    """Cuantiza a 2 decimales con ROUND_HALF_UP (redondeo de presentación)."""
    if value is None:
        return Decimal("0.00")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(TWO, rounding=ROUND_HALF_UP)


def _q5(value):
    """Cuantiza a 5 decimales con ROUND_HALF_UP (tope real de los DecimalField).

    Se usa al *guardar* puntaje/ponderación para conservar la precisión que el
    usuario captura; el redondeo a 2 decimales queda solo para la presentación.
    """
    if value is None:
        return Decimal("0.00000")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(FIVE, rounding=ROUND_HALF_UP)


def _orden_nombre(qs):
    return qs.order_by(F("orden").asc(nulls_last=True), "nombre")


def _normaliza(s):
    return normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def _parse_orden(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_decimal(raw, etiqueta="valor", minimo=None, maximo=None):
    """Convierte texto a Decimal aceptando UN solo separador decimal (coma o punto).

    Reglas (validacion de captura en todo el registro de la pagina):
      - Se acepta coma O punto como separador decimal, pero solo UNO.
      - Separadores mezclados ("1.234,5") o repetidos ("3,6,0") -> ValidationError.
      - Caracteres no numericos -> ValidationError.
      - Si se pasan `minimo`/`maximo`, el valor debe estar dentro del rango.
    Lanza ValidationError con un mensaje claro (se muestra al intentar guardar).
    """
    s = "" if raw is None else str(raw).strip()
    if s == "":
        raise ValidationError("El {} está vacío.".format(etiqueta))
    n_coma = s.count(",")
    n_punto = s.count(".")
    if n_coma and n_punto:
        raise ValidationError(
            "El {} «{}» tiene separadores mezclados (coma y punto); "
            "usa solo uno como separador decimal.".format(etiqueta, s)
        )
    if n_coma > 1 or n_punto > 1:
        raise ValidationError(
            "El {} «{}» tiene más de un separador decimal; usa solo uno.".format(etiqueta, s)
        )
    try:
        valor = Decimal(s.replace(",", "."))
    except InvalidOperation:
        raise ValidationError("El {} «{}» no es un número válido.".format(etiqueta, s))
    if minimo is not None and valor < minimo:
        raise ValidationError(
            "El {} «{}» no puede ser menor que {}.".format(etiqueta, s, minimo)
        )
    if maximo is not None and valor > maximo:
        raise ValidationError(
            "El {} «{}» no puede ser mayor que {}.".format(etiqueta, s, maximo)
        )
    return valor


def meses_del_periodo(periodo):
    nombre = _normaliza(periodo.nombre or "") if periodo else ""
    encontrados = []
    for value, label in Meses.choices:
        if _normaliza(label) in nombre:
            encontrados.append((value, label))
    if not encontrados:
        encontrados = list(Meses.choices)
    return encontrados


def _indicadores_editables_ids(user):
    """
    Devuelve set de IDs de indicadores que `user` puede editar.
    Si es superuser -> conjunto vacio se considera 'todos' (None).
    Si no tiene perfil -> conjunto vacio (no edita nada).
    """
    if user.is_superuser:
        return None  # marca especial -> 'todos'
    perfil = PerfilUsuario.objects.filter(usuario=user).prefetch_related("indicadores").first()
    if perfil is None:
        return set()
    return set(perfil.indicadores.values_list("id", flat=True))


def _puede_editar(indicadores_editables, indicador_id):
    if indicadores_editables is None:  # superuser
        return True
    return indicador_id in indicadores_editables


# --------------------------------------------------------------------- Inicio
#
# Dashboard analitico (replica del tablero de Power BI). Toda la analitica se
# deriva del "puntaje ponderado" del subindicador, que la captura ya persiste como
# EvaluacionResultado.ponderacion = puntaje * peso_sub / 100 (ver docstring del
# modulo). La agregacion sube: subindicador -> (suma) dependencia -> (promedio
# entre dependencias) pilar -> (suma) IMAG.
#
# Nota: solo el peso del SUBINDICADOR participa hoy en `ponderacion`; los pesos de
# Indicador/Pilar no se aplican (queda pendiente de definicion del negocio).
class _TodasCategorias:
    """Sentinela del filtro 'Todas las categorías': NO filtra por categoria (consolida
    todas), pero se distingue de `None` (que significa 'no hay categorías')."""
    pk = "todas"
    nombre = "Todas las categorías"

    def __str__(self):
        return self.nombre


TODAS_CATEGORIAS = _TodasCategorias()


def _eval_kwargs(categoria, modelo):
    """Filtro a nivel de la `Evaluacion` (categoria + versión del modelo).

    Devuelve los kwargs `evaluacion__categoria` / `evaluacion__modelo_evaluacion__version`
    que se aplican sobre EvaluacionResultado y (vía la relación inversa) sobre
    Periodo/Dependencia. `categoria` es el pivote; `modelo` es el NÚMERO de versión.

    El filtro opera sobre el número de versión (no sobre un ModeloEvaluacion concreto):
    una misma versión puede tener varias estructuras (varios ModeloEvaluacion para
    distintos grupos de dependencias), así que al elegir una versión entran TODAS sus
    estructuras.
    """
    kw = {}
    if categoria is not None and categoria is not TODAS_CATEGORIAS:
        kw["evaluacion__categoria"] = categoria
    if modelo is not None:
        kw["evaluacion__modelo_evaluacion__version"] = modelo
    return kw


def _puntajes_por_dependencia(categoria, modelo, periodo, pilar=None):
    """{dep_id: (nombre, total_ponderacion)} para una categoria/modelo y periodo.

    Si `pilar` se indica, solo suma los subindicadores de ese pilar (ranking por pilar).
    El filtro de pilar es por NOMBRE (PilarCategoria): una versión puede abarcar varias
    estructuras que comparten el mismo pilar por nombre.
    """
    if periodo is None or categoria is None:
        return {}
    qs = EvaluacionResultado.objects.filter(
        evaluacion__periodo=periodo, **_eval_kwargs(categoria, modelo)
    )
    if pilar is not None:
        qs = qs.filter(subindicador__indicador__pilar__nombre=pilar.nombre_id)
    filas = (
        qs.values("evaluacion__dependencia", "evaluacion__dependencia__nombre")
        .annotate(total=Sum("ponderacion"))
    )
    return {
        f["evaluacion__dependencia"]: (
            f["evaluacion__dependencia__nombre"], f["total"] or Decimal("0"),
        )
        for f in filas
    }


def _promedios_por_pilar(categoria, modelo, periodo, pilar=None):
    """{pilar_nombre_id: {'nombre','orden','peso','promedio'}} — promedio entre dependencias.

    Se agrupa por NOMBRE de pilar (PilarCategoria), no por el Pilar concreto: una versión
    puede abarcar varias estructuras (varios ModeloEvaluacion) que comparten el mismo pilar
    por nombre; agrupar por PK los duplicaría en el IMAG. Los pilares con el mismo nombre
    comparten orden/peso (validado en la migración), así que se toman del primer registro.
    """
    if periodo is None or categoria is None:
        return {}
    qs = EvaluacionResultado.objects.filter(
        evaluacion__periodo=periodo, **_eval_kwargs(categoria, modelo)
    )
    if pilar is not None:
        qs = qs.filter(subindicador__indicador__pilar__nombre=pilar.nombre_id)
    filas = (
        qs.values(
            "subindicador__indicador__pilar__nombre",
            "subindicador__indicador__pilar__nombre__nombre",
            "subindicador__indicador__pilar__orden",
            "subindicador__indicador__pilar__peso",
            "evaluacion__dependencia",
        )
        .annotate(total=Sum("ponderacion"))
    )
    acum = {}
    for f in filas:
        pid = f["subindicador__indicador__pilar__nombre"]
        d = acum.setdefault(pid, {
            "nombre": f["subindicador__indicador__pilar__nombre__nombre"],
            "orden": f["subindicador__indicador__pilar__orden"],
            "peso": f["subindicador__indicador__pilar__peso"] or Decimal("0"),
            "suma": Decimal("0"), "n": 0,
        })
        d["suma"] += f["total"] or Decimal("0")
        d["n"] += 1
    return {
        pid: {
            "nombre": d["nombre"], "orden": d["orden"], "peso": d["peso"],
            "promedio": (d["suma"] / d["n"]) if d["n"] else Decimal("0"),
        }
        for pid, d in acum.items()
    }


def _ranking(puntajes):
    """{dep_id: posicion} ordenando por total descendente (1 = mejor)."""
    orden = sorted(puntajes.items(), key=lambda kv: kv[1][1], reverse=True)
    return {dep_id: i + 1 for i, (dep_id, _) in enumerate(orden)}


def _signo(valor):
    if valor is None:
        return ""
    if valor > 0:
        return "pos"
    if valor < 0:
        return "neg"
    return "cero"


def _resolver(items, raw):
    """Devuelve el item de `items` cuyo pk coincide con `raw` (o None)."""
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None
    return next((x for x in items if x.pk == pk), None)


def _periodos_con_datos(categoria, modelo, vigencia, solo_publicos=False):
    """Periodos con evaluaciones para la categoria/modelo, del más reciente al más antiguo.

    `vigencia` (año) opcional acota a ese año. `solo_publicos=True` restringe a periodos
    con `publico=True` (reporte público): el equipo puede tener datos previos que no deben
    salir al público hasta que el admin marque el periodo como público. El dashboard
    interno usa el valor por defecto (False) y ve todos los periodos.
    """
    if categoria is None:
        return []
    qs = Periodo.objects.filter(**_eval_kwargs(categoria, modelo))
    if vigencia is not None:
        qs = qs.filter(vigencia=vigencia)
    if solo_publicos:
        qs = qs.filter(publico=True)
    return list(
        qs.distinct().order_by(F("orden").desc(nulls_last=True), "-creado_en")
    )


def _datos_dashboard(categoria, modelo, actual, anterior, pilar=None):
    """Calcula el tablero para una categoria/modelo/periodos/pilar dados.

    - `categoria` None -> None (no hay categoria).
    - `actual` None -> {sin_datos} (la categoria no tiene periodos con datos).
    - `pilar` None -> consolida todos los pilares; si se indica, filtra a ese pilar.
    """
    if categoria is None:
        return None
    if actual is None:
        return {"categoria": categoria, "sin_datos": True}

    pun_act = _puntajes_por_dependencia(categoria, modelo, actual, pilar)
    pun_ant = _puntajes_por_dependencia(categoria, modelo, anterior, pilar)
    rank_act = _ranking(pun_act)
    rank_ant = _ranking(pun_ant)
    pil_act = _promedios_por_pilar(categoria, modelo, actual, pilar)
    pil_ant = _promedios_por_pilar(categoria, modelo, anterior, pilar)

    imag_act = sum((p["promedio"] for p in pil_act.values()), Decimal("0"))
    imag_ant = sum((p["promedio"] for p in pil_ant.values()), Decimal("0")) if anterior else None
    imag_var = (imag_act - imag_ant) if imag_ant is not None else None

    # --- Pilares (barras): cada barra se mide contra el PESO del pilar (su máximo).
    pilares = []
    for pid, p in pil_act.items():
        prom_ant = pil_ant.get(pid, {}).get("promedio")
        peso = p.get("peso") or Decimal("0")
        pct = float(p["promedio"] / peso * 100) if peso else 0.0
        pilares.append({
            "nombre": p["nombre"],
            "orden": p["orden"],
            "peso": _q2(peso),
            "promedio": _q2(p["promedio"]),
            "promedio_anterior": _q2(prom_ant) if prom_ant is not None else None,
            "pct": max(0.0, min(100.0, pct)),
        })
    pilares.sort(key=lambda x: (x["orden"] is None, x["orden"] or 0, x["nombre"] or ""))

    # --- Ranking de dependencias: cada barra se mide contra 100 (puntaje máximo).
    ranking = []
    for dep_id, (nombre, total) in pun_act.items():
        total_ant = pun_ant.get(dep_id, (None, None))[1] if anterior else None
        pos = rank_act.get(dep_id)
        pos_ant = rank_ant.get(dep_id) if anterior else None
        delta_punt = (total - total_ant) if (total_ant is not None) else None
        delta_puesto = (pos_ant - pos) if (pos_ant and pos) else None
        ranking.append({
            "dependencia": nombre,
            "total": _q2(total),
            "posicion": pos,
            "total_anterior": _q2(total_ant) if total_ant is not None else None,
            "posicion_anterior": pos_ant,
            "delta_puntaje": _q2(delta_punt) if delta_punt is not None else None,
            "delta_puntaje_signo": _signo(delta_punt),
            "delta_puesto": delta_puesto,
            "delta_puesto_signo": _signo(delta_puesto),
            "pct": max(0.0, min(100.0, float(total))),
        })
    ranking.sort(key=lambda x: x["posicion"])

    return {
        "categoria": categoria,
        "periodo_actual": actual,
        "periodo_anterior": anterior,
        "imag_actual": _q2(imag_act),
        "imag_anterior": _q2(imag_ant) if imag_ant is not None else None,
        "imag_var": _q2(imag_var) if imag_var is not None else None,
        "imag_var_signo": _signo(imag_var),
        "pilares": pilares,
        "ranking": ranking,
        "mejor": ranking[0] if ranking else None,
        "peor": ranking[-1] if len(ranking) > 1 else None,
    }


@login_required
def dashboard(request):
    contexto = {
        "total_modelos": ModeloEvaluacion.objects.count(),
        "total_modelos_activos": ModeloEvaluacion.objects.filter(activo=True).count(),
        "total_evaluaciones": Evaluacion.objects.filter(periodo__activo=True).count(),
        "total_dependencias": Dependencia.objects.count(),
        "ultimas_evaluaciones": (
            Evaluacion.objects
            .filter(periodo__activo=True)
            .select_related("periodo", "dependencia", "modelo_evaluacion")
            .order_by("-creado_en")[:5]
        ),
    }
    return render(request, "base/dashboard.html", contexto)


def _serie_temporal(categoria, modelo, vigencia, pilar=None, solo_publicos=False):
    """Series para el gráfico de evolución: IMAG y cada pilar a través de los periodos.

    Eje X = periodos del más antiguo al más reciente. Honra el filtro `pilar`.
    `solo_publicos=True` limita el eje a periodos públicos (reporte público).
    """
    periodos = list(reversed(_periodos_con_datos(categoria, modelo, vigencia, solo_publicos)))
    labels = [str(p) for p in periodos]
    por_periodo = [_promedios_por_pilar(categoria, modelo, p, pilar) for p in periodos]
    imag = [
        float(sum((x["promedio"] for x in d.values()), Decimal("0")))
        for d in por_periodo
    ]
    meta = {}  # pid -> (nombre, orden, peso)  (unión de pilares presentes)
    for d in por_periodo:
        for pid, info in d.items():
            meta.setdefault(pid, (info["nombre"], info["orden"], float(info["peso"] or 0)))
    pilares = []
    for pid, (nombre, orden, peso) in meta.items():
        pilares.append({
            "nombre": nombre,
            "orden": orden,
            "peso": peso,
            "data": [float(d[pid]["promedio"]) if pid in d else None for d in por_periodo],
        })
    pilares.sort(key=lambda x: (x["orden"] is None, x["orden"] or 0, x["nombre"] or ""))
    return {"labels": labels, "imag": imag, "pilares": pilares}


# ----------------------------------------------------- Dashboard: dependencia
def _filtra_resultados(periodo, dependencia, pilar=None, indicador=None):
    """Queryset base de EvaluacionResultado para una dependencia (con filtros).

    La dependencia + periodo ya acotan a una única evaluación (constraint
    unique(periodo, dependencia)), así que no hace falta filtrar por categoria/modelo.
    """
    qs = EvaluacionResultado.objects.filter(
        evaluacion__periodo=periodo,
        evaluacion__dependencia=dependencia,
    )
    if pilar is not None:
        qs = qs.filter(subindicador__indicador__pilar=pilar)
    if indicador is not None:
        qs = qs.filter(subindicador__indicador=indicador)
    return qs


def _total_dependencia(periodo, dependencia, pilar=None, indicador=None):
    """Suma de ponderacion (puntaje total) de una dependencia en un periodo."""
    if periodo is None or dependencia is None:
        return Decimal("0")
    total = _filtra_resultados(
        periodo, dependencia, pilar, indicador
    ).aggregate(t=Sum("ponderacion"))["t"]
    return total or Decimal("0")


def _puntajes_por_pilar_dependencia(periodo, dependencia, pilar=None, indicador=None):
    """{pilar_categoria_id: {'nombre','orden','total'}} para una dependencia/periodo.

    Se agrupa por NOMBRE de pilar (PilarCategoria), no por el pk del Pilar: una versión
    puede abarcar varias estructuras (p. ej. v1-2025 y v1-2026) donde el mismo pilar es un
    objeto distinto. Agrupar por pk lo duplicaría en la serie de Desempeño; por nombre se
    consolida. `orden` se toma con Min (mismo nombre = mismo orden entre estructuras).
    """
    if periodo is None or dependencia is None:
        return {}
    filas = (
        _filtra_resultados(periodo, dependencia, pilar, indicador)
        .values(
            "subindicador__indicador__pilar__nombre",
            "subindicador__indicador__pilar__nombre__nombre",
        )
        .annotate(total=Sum("ponderacion"),
                  orden=Min("subindicador__indicador__pilar__orden"))
    )
    return {
        f["subindicador__indicador__pilar__nombre"]: {
            "nombre": f["subindicador__indicador__pilar__nombre__nombre"],
            "orden": f["orden"],
            "total": f["total"] or Decimal("0"),
        }
        for f in filas
    }


def _datos_dependencia(categoria, modelo, actual, anterior, dependencia, pilar=None, indicador=None):
    """Tablero de una dependencia: puntaje total, posición y nº de pilares evaluados."""
    if categoria is None:
        return None
    if actual is None or dependencia is None:
        return {"categoria": categoria, "dependencia": dependencia, "sin_datos": True}

    total_act = _total_dependencia(actual, dependencia, pilar, indicador)
    total_ant = (
        _total_dependencia(anterior, dependencia, pilar, indicador)
        if anterior else None
    )
    var = (total_act - total_ant) if total_ant is not None else None

    pilares_breakdown = _puntajes_por_pilar_dependencia(
        actual, dependencia, pilar, indicador
    )

    # Posicion en el ranking de la categoria/modelo (puntaje total, sin filtros de pilar).
    puntajes = _puntajes_por_dependencia(categoria, modelo, actual)
    posicion = _ranking(puntajes).get(dependencia.pk)

    return {
        "categoria": categoria,
        "dependencia": dependencia,
        "periodo_actual": actual,
        "periodo_anterior": anterior,
        "pilar": pilar,
        "indicador": indicador,
        "total_actual": _q2(total_act),
        "total_anterior": _q2(total_ant) if total_ant is not None else None,
        "total_var": _q2(var) if var is not None else None,
        "total_var_signo": _signo(var),
        "posicion": posicion,
        "total_deps": len(puntajes),
        "pilares_evaluados": len(pilares_breakdown),
    }


def _serie_dependencia(categoria, modelo, vigencia, dependencia, pilar=None, indicador=None, solo_publicos=False):
    """Series de evolución de una dependencia: total y cada pilar por periodo.

    `solo_publicos=True` limita el eje a periodos públicos (reporte público).
    """
    periodos = list(reversed(_periodos_con_datos(categoria, modelo, vigencia, solo_publicos)))
    labels = [str(p) for p in periodos]
    total = [
        float(_total_dependencia(p, dependencia, pilar, indicador))
        for p in periodos
    ]
    por_periodo = [
        _puntajes_por_pilar_dependencia(p, dependencia, pilar, indicador)
        for p in periodos
    ]
    meta = {}
    for d in por_periodo:
        for pid, info in d.items():
            meta.setdefault(pid, (info["nombre"], info["orden"]))
    pilares = []
    for pid, (nombre, orden) in meta.items():
        pilares.append({
            "nombre": nombre,
            "orden": orden,
            "data": [float(d[pid]["total"]) if pid in d else None for d in por_periodo],
        })
    pilares.sort(key=lambda x: (x["orden"] is None, x["orden"] or 0, x["nombre"] or ""))
    return {"labels": labels, "total": total, "pilares": pilares}


def _categorias_disponibles():
    """Categorias (clasificacion de dependencias) ordenadas para los selectores.

    Son el pivote del tablero: las pestañas/selector superior cambian de categoria
    y toda la analitica se filtra por `evaluacion__categoria`.
    """
    return list(_orden_nombre(Categoria.objects.all()))


def _resolver_categoria(request, categorias):
    """Categoria seleccionada en el GET, o la primera disponible.

    `categoria=todas` selecciona el sentinela TODAS_CATEGORIAS (consolida todas las
    categorías: IMAG general y sus indicadores sin pivotar por categoría).
    """
    if request.GET.get("categoria") == "todas":
        return TODAS_CATEGORIAS
    return (
        _resolver(categorias, request.GET.get("categoria"))
        or (categorias[0] if categorias else None)
    )


def _versiones_disponibles():
    """Números de versión existentes, de la más reciente a la más antigua (filtro de versión).

    El filtro de "versión del modelo" opera sobre el número de versión, no sobre cada
    ModeloEvaluacion: una versión puede tener varias estructuras (varios ModeloEvaluacion
    para distintos grupos de dependencias). Al elegir una versión entran todas ellas.
    """
    return list(
        ModeloEvaluacion.objects
        .values_list("version", flat=True)
        .distinct()
        .order_by("-version")
    )


def _resolver_version(request, versiones):
    """Versión seleccionada en el GET (param 'modelo'); por defecto la versión activa más
    reciente, o la más reciente disponible.

    Siempre hay una versión seleccionada (no existe opción "todas"): cada versión tiene
    su propia estructura de pilares, así que mezclarlas no tendría sentido.
    """
    raw = request.GET.get("modelo")
    try:
        v = int(raw)
        if v in versiones:
            return v
    except (TypeError, ValueError):
        pass
    activa = (
        ModeloEvaluacion.objects.filter(activo=True)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    if activa in versiones:
        return activa
    return versiones[0] if versiones else None


def _vigencias_disponibles(categoria, modelo):
    """Años (vigencias) con datos para la categoria/modelo, de mayor a menor."""
    if categoria is None:
        return []
    return list(
        Periodo.objects
        .filter(vigencia__isnull=False, **_eval_kwargs(categoria, modelo))
        .values_list("vigencia", flat=True)
        .distinct()
        .order_by("-vigencia")
    )


def _resolver_vigencia(request, vigencias):
    """Vigencia (año) seleccionada en el GET; None = todas las vigencias."""
    raw = request.GET.get("vigencia")
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    return v if v in vigencias else None


def _pilares_de_categoria(categoria, modelo):
    """Pilares presentes en las evaluaciones de la categoria/modelo (filtro 'Indicador').

    Se derivan de los pilares efectivamente evaluados (no del catálogo del modelo) para
    no ofrecer pilares sin datos en el alcance seleccionado. Se deduplican por NOMBRE
    (una versión puede abarcar varias estructuras con el mismo pilar repetido): se deja un
    Pilar representativo por nombre, ordenado por orden/nombre.
    """
    if categoria is None:
        return []
    pilar_ids = (
        EvaluacionResultado.objects
        .filter(**_eval_kwargs(categoria, modelo))
        .values_list("subindicador__indicador__pilar", flat=True)
        .distinct()
    )
    pilares = _orden_nombre(Pilar.objects.filter(pk__in=pilar_ids).select_related("nombre"))
    vistos, unicos = set(), []
    for p in pilares:
        if p.nombre_id in vistos:
            continue
        vistos.add(p.nombre_id)
        unicos.append(p)
    return unicos


def _resolver_actual_anterior(periodos, request):
    """Resuelve el periodo "actual" (último) y el "anterior" para comparar.

    - `periodo` (GET): periodo principal; por defecto, el más reciente con datos.
    - `comparar` (GET): periodo de comparación. `"0"` desactiva la comparación;
      si viene vacío, se usa el inmediatamente anterior con datos.

    Garantiza el **orden cronológico**: de los dos periodos elegidos, "actual"
    siempre es el más reciente y "anterior" el más antiguo, sin importar cuál se
    seleccionó como principal o como comparación. Ej.: principal = "Julio - Agosto"
    y comparar = "Noviembre - Diciembre" ⇒ actual = "Noviembre - Diciembre",
    anterior = "Julio - Agosto" (la variación siempre lee reciente − antiguo).
    `periodos` viene del más reciente al más antiguo, así que un índice menor en la
    lista = periodo más reciente.
    """
    actual = _resolver(periodos, request.GET.get("periodo")) or (periodos[0] if periodos else None)

    comparar_raw = request.GET.get("comparar")
    if comparar_raw == "0":
        anterior = None
    else:
        anterior = _resolver(periodos, comparar_raw)
        if anterior is None and actual in periodos:
            idx = periodos.index(actual)
            anterior = periodos[idx + 1] if idx + 1 < len(periodos) else None

    # Reordena cronológicamente: el más reciente de los dos es el "actual".
    if (anterior is not None and actual is not None
            and actual in periodos and anterior in periodos
            and periodos.index(anterior) < periodos.index(actual)):
        actual, anterior = anterior, actual

    return actual, anterior, comparar_raw


def _resolver_dependencia_contexto(request, solo_publicos=False):
    """Resuelve categoria/modelo/vigencia/periodos/dependencia/pilar desde el GET.

    `solo_publicos=True` (reporte público) limita periodos y dependencias a los que
    tienen datos en periodos públicos; el dashboard interno usa False (ve todo).
    """
    categorias = _categorias_disponibles()
    categoria = _resolver_categoria(request, categorias)
    versiones = _versiones_disponibles()
    modelo = _resolver_version(request, versiones)
    vigencias = _vigencias_disponibles(categoria, modelo)
    vigencia = _resolver_vigencia(request, vigencias)
    periodos = _periodos_con_datos(categoria, modelo, vigencia, solo_publicos)
    actual, anterior, comparar_raw = _resolver_actual_anterior(periodos, request)

    if categoria:
        dep_qs = Dependencia.objects.filter(**_eval_kwargs(categoria, modelo))
        if vigencia is not None:
            dep_qs = dep_qs.filter(evaluacion__periodo__vigencia=vigencia)
        if solo_publicos:
            dep_qs = dep_qs.filter(evaluacion__periodo__publico=True)
        dependencias = list(dep_qs.distinct().order_by("nombre"))
    else:
        dependencias = []
    dependencia = _resolver(dependencias, request.GET.get("dependencia")) or (dependencias[0] if dependencias else None)

    pilares_disp = _pilares_de_categoria(categoria, modelo)
    pilar = _resolver(pilares_disp, request.GET.get("pilar"))

    return {
        "categorias": categorias, "categoria": categoria,
        "modelos": versiones, "modelo": modelo,
        "vigencias": vigencias, "vigencia": vigencia,
        "periodos": periodos,
        "actual": actual, "anterior": anterior, "comparar_raw": comparar_raw,
        "dependencias": dependencias, "dependencia": dependencia,
        "pilares_disp": pilares_disp, "pilar": pilar,
    }


# ------------------------------------------------- Reporte publico (sin login)
#
# Pagina de RESULTADOS de cara al publico (ciudadania / organos de control):
# replica de las 4 vistas del Power BI (IMAG, Desempeno, Ranking, Variaciones).
# NO lleva @login_required: su unico fin es mostrar resultados, sin editar nada.
# Las mismas vistas alimentan el dashboard interno (con login) via `interno=True`
# (ver wrappers dashboard_imag/_desempeno/_ranking/_variaciones mas abajo).
def _estado_semaforo(pct):
    """Clase de semaforo segun el % de cumplimiento (0-100)."""
    if pct is None:
        return "cero"
    if pct >= 80:
        return "verde"
    if pct >= 60:
        return "ambar"
    return "rojo"


def _imag_max(dash):
    """Puntaje maximo posible del IMAG = suma de los pesos de los pilares en alcance.

    Se deriva de los pilares presentes en el tablero (no del modelo), porque el pivote
    ahora es la categoria. Con filtro de pilar, `dash['pilares']` ya trae solo ese
    pilar, asi que la suma equivale a su peso.
    """
    total = sum(float(p["peso"]) for p in dash.get("pilares", []))
    return total or 100.0


def _reporte_filtros(request, solo_publicos=True):
    """Resuelve categoria/periodos/actual/anterior/pilar desde el GET (compartido por
    las vistas IMAG, Ranking y Variaciones).

    `solo_publicos=True` (reporte publico) solo considera periodos PUBLICOS
    (`publico=True`): nunca muestra datos previos de un periodo que el admin aun no
    ha publicado. El dashboard interno usa `solo_publicos=False` y ve todos los
    periodos (los resultados son del equipo).
    """
    categorias = _categorias_disponibles()
    categoria = _resolver_categoria(request, categorias)
    versiones = _versiones_disponibles()
    modelo = _resolver_version(request, versiones)
    vigencias = _vigencias_disponibles(categoria, modelo)
    vigencia = _resolver_vigencia(request, vigencias)
    periodos = _periodos_con_datos(categoria, modelo, vigencia, solo_publicos=solo_publicos)
    actual, anterior, comparar_raw = _resolver_actual_anterior(periodos, request)

    pilares_disp = _pilares_de_categoria(categoria, modelo)
    pilar = _resolver(pilares_disp, request.GET.get("pilar"))

    return {
        "categorias": categorias, "categoria": categoria,
        "modelos": versiones, "modelo": modelo,
        "vigencias": vigencias, "vigencia": vigencia,
        "periodos": periodos,
        "actual": actual, "anterior": anterior, "comparar_raw": comparar_raw,
        "pilares_disp": pilares_disp, "pilar": pilar,
    }


# Mapa vista -> (url publica, url interna). El reporte publico y el dashboard
# interno comparten plantillas; solo cambian la base, la URL de "Restablecer" y
# el flag `interno` (que ademas decide `solo_publicos`).
_VISTA_URL = {
    "imag": ("contenido:reporte_publico", "contenido:dashboard_imag"),
    "desempeno": ("contenido:reporte_desempeno", "contenido:dashboard_desempeno"),
    "ranking": ("contenido:reporte_ranking", "contenido:dashboard_ranking"),
    "variaciones": ("contenido:reporte_variaciones", "contenido:dashboard_variaciones"),
}


def _reporte_chrome(vista, interno):
    """Contexto del 'cascaron' compartido por reporte publico y dashboard interno:
    plantilla base, flag `interno` y URL de restablecer filtros."""
    pub, intr = _VISTA_URL[vista]
    return {
        "interno": interno,
        "base_template": "base/dashboard_reporte.html" if interno else "reporte/base_reporte.html",
        "url_reset": intr if interno else pub,
        "url_publico": pub,  # vista publica equivalente (para el boton "Ver reporte publico")
    }


def _ctx_filtros(f, vista, interno=False):
    """Diccionario de contexto comun (filtros + cabecera) para las plantillas."""
    ctx = {
        "vista": vista,
        "categorias": f["categorias"], "periodos": f["periodos"], "pilares_disp": f["pilares_disp"],
        "modelos": f["modelos"], "vigencias": f["vigencias"],
        "sel_categoria": f["categoria"], "sel_periodo": f["actual"], "sel_comparar": f["anterior"],
        "sel_modelo": f["modelo"], "sel_vigencia": f["vigencia"],
        "sel_comparar_none": f["comparar_raw"] == "0", "sel_pilar": f["pilar"],
        "categoria": f["categoria"], "modelo": f["modelo"], "vigencia": f["vigencia"],
        "periodo_actual": f["actual"], "periodo_anterior": f["anterior"],
    }
    ctx.update(_reporte_chrome(vista, interno))
    return ctx


def _shade(valor, tope, alpha_max=0.55):
    """Alpha 0..alpha_max proporcional a |valor|/tope (para sombreado de tablas)."""
    if not tope:
        return 0.0
    return max(0.0, min(alpha_max, abs(valor) / tope * alpha_max))


def reporte_publico(request, interno=False):
    """Vista IMAG (replica del Power BI). Acceso libre, filtros via GET.

    Muestra: KPIs del IMAG (ultimo %, anterior %, variacion en puntos), evolucion
    del % de cumplimiento por pilar a lo largo de los periodos, y tabla
    Pilar | Periodo Anterior | Ultimo Periodo. El "Indicador" del Power BI es el
    Pilar del modelo; los puntajes se muestran como % de cumplimiento (promedio/peso).

    `interno=True` (dashboard del equipo) levanta la restriccion de periodo publico.
    """
    f = _reporte_filtros(request, solo_publicos=not interno)
    categoria, modelo, vigencia = f["categoria"], f["modelo"], f["vigencia"]
    actual, anterior, pilar = f["actual"], f["anterior"], f["pilar"]
    dash = _datos_dashboard(categoria, modelo, actual, anterior, pilar)
    ctx = _ctx_filtros(f, "imag", interno)

    if dash is None or dash.get("sin_datos"):
        return render(request, "reporte/reporte_imag.html", dict(ctx, vacio=True))

    imag_max = _imag_max(dash)
    imag_pct = max(0.0, min(100.0, float(dash["imag_actual"]) / imag_max * 100)) if imag_max else 0.0
    imag_ant_pct = (
        float(dash["imag_anterior"]) / imag_max * 100
        if (dash.get("imag_anterior") is not None and imag_max) else None
    )
    imag_var = float(dash["imag_var"]) if dash.get("imag_var") is not None else None

    # Tabla "Desempeno por Indicador" (= pilar), en % de cumplimiento.
    pilares_tabla = []
    for p in dash["pilares"]:
        peso = float(p["peso"]) or 0.0
        ult = p["pct"]
        ant = (float(p["promedio_anterior"]) / peso * 100) if (p["promedio_anterior"] is not None and peso) else None
        pilares_tabla.append({
            "nombre": p["nombre"], "ult": ult, "ant": ant,
            "ult_a": _shade(ult, 100), "ant_a": _shade(ant, 100) if ant is not None else 0.0,
        })

    serie = _serie_temporal(categoria, modelo, vigencia, pilar, solo_publicos=not interno)
    payload = {
        "labels": serie["labels"],
        "pilares": [{"nombre": p["nombre"], "peso": p["peso"], "data": p["data"]} for p in serie["pilares"]],
    }

    return render(request, "reporte/reporte_imag.html", dict(
        ctx, vacio=False, dash=dash, payload=payload,
        imag_pct=imag_pct, imag_ant_pct=imag_ant_pct, imag_var=imag_var,
        imag_var_signo=dash["imag_var_signo"], imag_max=imag_max,
        pilares_tabla=pilares_tabla,
    ))


def reporte_variaciones(request, interno=False):
    """Vista Variaciones (replica del Power BI). Acceso libre, filtros via GET.

    Tabla Dependencia | Periodo Anterior | Ultimo Periodo | Variacion + barras
    horizontales de variacion + KPIs (mejor/peor variacion, mejor/peor desempeno).
    Filtro por pilar (el "Indicador" del Power BI). Las variaciones requieren un
    periodo de comparacion (por defecto, el inmediatamente anterior).

    `interno=True` (dashboard del equipo) levanta la restriccion de periodo publico.
    """
    f = _reporte_filtros(request, solo_publicos=not interno)
    categoria, modelo = f["categoria"], f["modelo"]
    actual, anterior, pilar = f["actual"], f["anterior"], f["pilar"]
    dash = _datos_dashboard(categoria, modelo, actual, anterior, pilar)
    ctx = _ctx_filtros(f, "variaciones", interno)

    if dash is None or dash.get("sin_datos"):
        return render(request, "reporte/reporte_variaciones.html", dict(ctx, vacio=True))

    filas = []
    for r in dash["ranking"]:
        filas.append({
            "dependencia": r["dependencia"],
            "ult": float(r["total"]),
            "ant": float(r["total_anterior"]) if r["total_anterior"] is not None else None,
            "var": float(r["delta_puntaje"]) if r["delta_puntaje"] is not None else None,
            "signo": r["delta_puntaje_signo"],
        })
    # Orden por variacion descendente (mejor variacion arriba); sin variacion al final.
    filas.sort(key=lambda x: (x["var"] is None, -(x["var"] if x["var"] is not None else 0)))

    con_var = [x for x in filas if x["var"] is not None]
    maxabs = max((abs(x["var"]) for x in con_var), default=0.0) or 1.0
    for x in filas:
        x["ult_a"] = _shade(x["ult"], 100)
        x["ant_a"] = _shade(x["ant"], 100) if x["ant"] is not None else 0.0
        x["var_a"] = _shade(x["var"], maxabs, 0.5) if x["var"] is not None else 0.0

    mejor_var = max(con_var, key=lambda x: x["var"]) if con_var else None
    peor_var = min(con_var, key=lambda x: x["var"]) if con_var else None

    payload = {
        "variacion": [
            {"dependencia": x["dependencia"], "var": x["var"]}
            for x in filas if x["var"] is not None
        ],
    }

    return render(request, "reporte/reporte_variaciones.html", dict(
        ctx, vacio=False, dash=dash, payload=payload,
        filas=filas, hay_comparacion=bool(anterior),
        mejor_var=mejor_var, peor_var=peor_var,
        mejor_desemp=dash["mejor"], peor_desemp=dash["peor"],
    ))


def reporte_desempeno(request, interno=False):
    """Vista Desempeno (replica del Power BI): por dependencia. Acceso libre.

    Muestra el puntaje del periodo (vs objetivo 60%), la variacion respecto al
    periodo anterior y la evolucion de cada pilar como small-multiples (una
    mini-grafica por pilar, en puntos = % del total).

    `interno=True` (dashboard del equipo) levanta la restriccion de periodo publico.
    """
    ctx = _resolver_dependencia_contexto(request, solo_publicos=not interno)
    categoria = ctx["categoria"]
    modelo = ctx["modelo"]
    vigencia = ctx["vigencia"]
    actual = ctx["actual"]
    anterior = ctx["anterior"]
    dependencia = ctx["dependencia"]
    pilar = ctx["pilar"]

    dash = _datos_dependencia(categoria, modelo, actual, anterior, dependencia, pilar)

    filtros = {
        "vista": "desempeno",
        "categorias": ctx["categorias"],
        "modelos": ctx["modelos"],
        "vigencias": ctx["vigencias"],
        "periodos": ctx["periodos"],
        "dependencias": ctx["dependencias"],
        "pilares_disp": ctx["pilares_disp"],
        "sel_categoria": categoria,
        "sel_modelo": modelo,
        "sel_vigencia": vigencia,
        "sel_periodo": actual,
        "sel_comparar": anterior,
        "sel_comparar_none": ctx["comparar_raw"] == "0",
        "sel_dependencia": dependencia,
        "sel_pilar": pilar,
        "categoria": categoria,
        "modelo": modelo,
        "vigencia": vigencia,
        "periodo_actual": actual,
        "periodo_anterior": anterior,
    }
    filtros.update(_reporte_chrome("desempeno", interno))

    if dash is None or dash.get("sin_datos"):
        return render(request, "reporte/reporte_desempeno.html", dict(filtros, vacio=True))

    objetivo = 60.0
    total_act = float(dash["total_actual"])
    total_ant = float(dash["total_anterior"]) if dash["total_anterior"] is not None else None
    total_var = float(dash["total_var"]) if dash["total_var"] is not None else None
    serie = _serie_dependencia(categoria, modelo, vigencia, dependencia, pilar, solo_publicos=not interno)

    payload = {
        "labels": serie["labels"],
        "pilares": [{"nombre": p["nombre"], "data": p["data"]} for p in serie["pilares"]],
    }

    return render(request, "reporte/reporte_desempeno.html", dict(
        filtros, vacio=False, dash=dash, payload=payload,
        total_act=total_act, total_ant=total_ant, total_var=total_var,
        total_var_signo=dash["total_var_signo"],
        objetivo=objetivo, gap=total_act - objetivo,
        gap_ant=(total_ant - objetivo) if total_ant is not None else None,
        estado=_estado_semaforo(total_act),
        pilares_mini=serie["pilares"],
    ))


def reporte_ranking(request, interno=False):
    """Vista Ranking (replica del Power BI). Acceso libre.

    La fila de pestañas superior cambia de Categoria (clasificacion de la
    dependencia). Para la categoria/periodo elegidos, muestra el ranking de
    dependencias (barras + tabla, contra el objetivo = umbral del periodo).

    `interno=True` (dashboard del equipo) levanta la restriccion de periodo publico.
    """
    f = _reporte_filtros(request, solo_publicos=not interno)
    categoria, modelo = f["categoria"], f["modelo"]
    actual, anterior, pilar = f["actual"], f["anterior"], f["pilar"]
    dash = _datos_dashboard(categoria, modelo, actual, anterior, pilar)
    ctx = _ctx_filtros(f, "ranking", interno)
    # Objetivo del ranking = umbral del periodo actual (puede variar de un periodo a
    # otro). Si el periodo no tiene umbral definido, no se dibuja la linea de objetivo.
    objetivo = float(actual.umbral) if (actual and actual.umbral is not None) else None

    if dash is None or dash.get("sin_datos"):
        return render(request, "reporte/reporte_ranking.html", dict(ctx, vacio=True, objetivo=objetivo))

    filas = []
    for r in dash["ranking"]:
        total = float(r["total"])
        filas.append({
            "dependencia": r["dependencia"], "total": total,
            "pos": r["posicion"], "a": _shade(total, 100, 0.5),
        })

    payload = {
        "ranking": [{"dependencia": x["dependencia"], "total": x["total"]} for x in filas],
        "mejor": dash["mejor"]["dependencia"] if dash["mejor"] else None,
        "objetivo": objetivo,
    }

    return render(request, "reporte/reporte_ranking.html", dict(
        ctx, vacio=False, dash=dash, filas=filas, payload=payload,
        objetivo=objetivo, mejor=dash["mejor"],
    ))


# ------------------------------------------------ Dashboard interno (con login)
#
# Mismas 4 vistas del reporte, pero dentro del shell de la app y SIN la
# restriccion de periodo publico: el equipo ve todos los periodos (incluidos los
# datos previos aun no publicados). Reutilizan las vistas del reporte con
# `interno=True`; el login lo aporta el wrapper.
@login_required
def dashboard_imag(request):
    return reporte_publico(request, interno=True)


@login_required
def dashboard_desempeno(request):
    return reporte_desempeno(request, interno=True)


@login_required
def dashboard_ranking(request):
    return reporte_ranking(request, interno=True)


@login_required
def dashboard_variaciones(request):
    return reporte_variaciones(request, interno=True)


# =========================================================================
#                                REPORTES
# =========================================================================
# Genera informes descargables (Excel/PDF) con la evaluación diligenciada de
# cada dependencia, con la misma jerarquía de la pantalla de evaluación. Los
# constructores viven en `contenido/reportes.py` (import perezoso para evitar
# el ciclo views <-> reportes).
def _deps_en_alcance(categoria, modelo, periodo):
    """Dependencias con evaluación en el periodo, para la versión (+ categoría)."""
    if periodo is None or categoria is None:
        return []
    return list(
        Dependencia.objects
        .filter(evaluacion__periodo=periodo, **_eval_kwargs(categoria, modelo))
        .distinct().order_by("nombre")
    )


def construir_matriz(evaluacion):
    """Matriz jerárquica read-only de una evaluación, como dicts planos (sin ORM),
    lista para los constructores de Excel/PDF. Replica el árbol de la pantalla de
    evaluación (Pilar → Indicador → Subindicador → Criterios) con puntaje,
    ponderación y desglose por mes."""
    meses = meses_del_periodo(evaluacion.periodo)
    pilares_qs = _orden_nombre(
        Pilar.objects.filter(modelo_evaluacion=evaluacion.modelo_evaluacion)
    ).prefetch_related(
        Prefetch(
            "indicador_set",
            queryset=_orden_nombre(Indicador.objects.all()).prefetch_related(
                Prefetch(
                    "subindicador_set",
                    queryset=_orden_nombre(Subindicador.objects.all()).prefetch_related(
                        Prefetch("criterio_set", queryset=_orden_nombre(Criterio.objects.all())),
                    ),
                ),
            ),
        )
    )
    resultados = {
        r.subindicador_id: r
        for r in EvaluacionResultado.objects.filter(evaluacion=evaluacion)
        .prefetch_related("evaluacionresultadodetalle_set")
    }
    detalles = {
        sid: {d.mes: d for d in r.evaluacionresultadodetalle_set.all()}
        for sid, r in resultados.items()
    }

    pilares = []
    for pilar in pilares_qs:
        indicadores = []
        for ind in pilar.indicador_set.all():
            subs = []
            for sub in ind.subindicador_set.all():
                r = resultados.get(sub.pk)
                dts = detalles.get(sub.pk, {})
                es_mensual = sub.tipo_calculo == "mensual"
                subs.append({
                    "nombre": str(sub.nombre),
                    "peso": sub.peso,
                    "tipo": sub.tipo_calculo or "",
                    "criterios": [(str(c.nombre), c.rango) for c in sub.criterio_set.all()],
                    "puntaje": r.puntaje if r else None,
                    "ponderacion": r.ponderacion if r else None,
                    "observaciones": (r.observaciones or "") if r else "",
                    "meses": {m: (dts[m].puntaje if m in dts else None) for m, _ in meses}
                             if es_mensual else {},
                })
            indicadores.append({"nombre": str(ind.nombre), "peso": ind.peso, "subindicadores": subs})
        pilares.append({"nombre": str(pilar.nombre), "peso": pilar.peso, "indicadores": indicadores})

    return {
        "dependencia": str(evaluacion.dependencia),
        "categoria": str(evaluacion.categoria) if evaluacion.categoria else "—",
        "periodo": str(evaluacion.periodo),
        "vigencia": evaluacion.periodo.vigencia,
        "version": evaluacion.modelo_evaluacion.version,
        "meses": [(m, lbl) for m, lbl in meses],
        "pilares": pilares,
    }


@login_required
def reportes(request):
    """Pantalla del compositor de informes: filtros + panel-membrete (cascada GET)."""
    categorias = _categorias_disponibles()
    categoria = _resolver_categoria(request, categorias)
    versiones = _versiones_disponibles()
    modelo = _resolver_version(request, versiones)
    periodos = _periodos_con_datos(categoria, modelo, None, solo_publicos=False)
    periodo = _resolver(periodos, request.GET.get("periodo")) or (periodos[0] if periodos else None)
    dependencias = _deps_en_alcance(categoria, modelo, periodo)
    sel_deps = set(request.GET.getlist("dependencia"))
    return render(request, "reportes/reportes.html", {
        "categorias": categorias, "categoria": categoria,
        "versiones": versiones, "version": modelo,
        "periodos": periodos, "periodo": periodo,
        "dependencias": dependencias, "sel_deps": sel_deps,
        "todas_categorias": TODAS_CATEGORIAS,
    })


@login_required
def reporte_generar(request):
    """Genera y descarga el informe (Excel o PDF) según los filtros del POST."""
    if request.method != "POST":
        return redirect("contenido:reportes")

    categorias = _categorias_disponibles()
    versiones = _versiones_disponibles()

    try:
        modelo = int(request.POST.get("modelo"))
    except (TypeError, ValueError):
        modelo = None
    if modelo not in versiones:
        modelo = _resolver_version(request, versiones)

    cat_raw = request.POST.get("categoria")
    if cat_raw == "todas":
        categoria = TODAS_CATEGORIAS
    else:
        categoria = _resolver(categorias, cat_raw) or (categorias[0] if categorias else None)

    periodos = _periodos_con_datos(categoria, modelo, None, solo_publicos=False)
    periodo = _resolver(periodos, request.POST.get("periodo")) or (periodos[0] if periodos else None)
    if periodo is None or categoria is None:
        messages.warning(request, "No hay datos para los filtros seleccionados.")
        return redirect("contenido:reportes")

    alcance = {str(d.pk): d for d in _deps_en_alcance(categoria, modelo, periodo)}
    elegidas = [pk for pk in request.POST.getlist("dependencia") if pk in alcance]
    deps = [alcance[pk] for pk in elegidas] if elegidas else list(alcance.values())
    if not deps:
        messages.warning(request, "No hay dependencias con evaluación para esos filtros.")
        return redirect("contenido:reportes")

    items = []
    for dep in deps:
        ev = (
            Evaluacion.objects
            .filter(dependencia=dep, periodo=periodo, modelo_evaluacion__version=modelo)
            .select_related("periodo", "dependencia", "modelo_evaluacion", "categoria")
            .first()
        )
        if ev is not None:
            items.append(construir_matriz(ev))
    if not items:
        messages.warning(request, "No se encontraron evaluaciones para generar el informe.")
        return redirect("contenido:reportes")

    from . import reportes as reportes_mod  # import perezoso (evita ciclo)
    nombre = "Informe_MAG_{}".format(slugify("{}-{}".format(periodo, periodo.vigencia or "")))
    if request.POST.get("formato") == "pdf":
        resp = HttpResponse(reportes_mod.generar_pdf(items), content_type="application/pdf")
        resp["Content-Disposition"] = 'attachment; filename="{}.pdf"'.format(nombre)
    else:
        resp = HttpResponse(
            reportes_mod.generar_excel(items).getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="{}.xlsx"'.format(nombre)
    return resp


# =========================================================================
#                              PARAMETRIZACION
# =========================================================================
class ModeloEvaluacionListView(LoginRequiredMixin, ListView):
    model = ModeloEvaluacion
    template_name = "modelos/modelo_list.html"
    context_object_name = "modelos"
    ordering = ["-activo", "-version", "nombre"]


class ModeloEvaluacionCreateView(LoginRequiredMixin, CreateView):
    model = ModeloEvaluacion
    fields = ["nombre", "version", "activo"]
    template_name = "modelos/modelo_form.html"
    success_url = reverse_lazy("contenido:modelo_list")

    def form_valid(self, form):
        messages.success(self.request, "Modelo de evaluacion creado correctamente.")
        return super().form_valid(form)


class ModeloEvaluacionUpdateView(LoginRequiredMixin, UpdateView):
    model = ModeloEvaluacion
    fields = ["nombre", "version", "activo"]
    template_name = "modelos/modelo_form.html"

    def get_success_url(self):
        return reverse("contenido:modelo_detalle", args=[self.object.pk])

    def form_valid(self, form):
        messages.success(self.request, "Modelo actualizado correctamente.")
        return super().form_valid(form)


@login_required
def modelo_detalle(request, pk):
    modelo = get_object_or_404(
        ModeloEvaluacion.objects.prefetch_related(
            Prefetch(
                "pilar_set",
                queryset=_orden_nombre(Pilar.objects.all()).prefetch_related(
                    Prefetch(
                        "indicador_set",
                        queryset=_orden_nombre(Indicador.objects.all()).prefetch_related(
                            Prefetch(
                                "subindicador_set",
                                queryset=_orden_nombre(Subindicador.objects.all()).prefetch_related(
                                    Prefetch(
                                        "criterio_set",
                                        queryset=_orden_nombre(Criterio.objects.all()),
                                    )
                                ),
                            )
                        ),
                    )
                ),
            ),
        ),
        pk=pk,
    )
    dependencias_asignadas = (
        DependenciaModelo.objects.filter(modelo=modelo)
        .select_related("dependencia")
        .order_by("dependencia__nombre")
    )
    dependencias_disponibles = Dependencia.objects.exclude(
        dependenciamodelo__modelo=modelo
    ).order_by("nombre")
    return render(request, "modelos/modelo_detalle.html", {
        "modelo": modelo,
        "pilares": modelo.pilar_set.all(),
        "dependencias_asignadas": dependencias_asignadas,
        "dependencias_disponibles": dependencias_disponibles,
    })


@login_required
def modelo_activar(request, pk):
    modelo = get_object_or_404(ModeloEvaluacion, pk=pk)
    if request.method == "POST":
        modelo.activo = True
        modelo.save()
        messages.success(request, "El modelo «{}» ha sido marcado como activo.".format(modelo))
    return redirect("contenido:modelo_detalle", pk=pk)


@login_required
def dependencia_modelo_asignar(request, pk):
    modelo = get_object_or_404(ModeloEvaluacion, pk=pk)
    if request.method == "POST":
        dependencia_id = request.POST.get("dependencia")
        activo = request.POST.get("activo") == "on"
        dependencia = get_object_or_404(Dependencia, pk=dependencia_id)
        try:
            with transaction.atomic():
                if activo:
                    DependenciaModelo.objects.filter(
                        dependencia=dependencia, activo=True
                    ).update(activo=False)
                DependenciaModelo.objects.update_or_create(
                    modelo=modelo, dependencia=dependencia,
                    defaults={"activo": activo},
                )
            messages.success(request, "Dependencia «{}» asignada al modelo «{}».".format(dependencia, modelo))
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("contenido:modelo_detalle", pk=pk)


@login_required
def pilar_create(request, pk):
    modelo = get_object_or_404(ModeloEvaluacion, pk=pk)
    categorias = PilarCategoria.objects.order_by("nombre")
    if request.method == "POST":
        categoria = PilarCategoria.objects.filter(pk=request.POST.get("nombre")).first()
        peso = request.POST.get("peso") or "0"
        orden = _parse_orden(request.POST.get("orden"))
        if categoria is None:
            messages.error(request, "Debe seleccionar una categoría de pilar.")
        else:
            try:
                Pilar.objects.create(
                    modelo_evaluacion=modelo, nombre=categoria,
                    peso=_parse_decimal(peso, "peso (%)", 0, 100), orden=orden,
                )
                messages.success(request, "Pilar creado correctamente.")
                return redirect("contenido:modelo_detalle", pk=pk)
            except (InvalidOperation, ValidationError) as exc:
                messages.error(request, "Error al crear el pilar: {}".format("; ".join(exc.messages) if hasattr(exc, "messages") else exc))
    return render(request, "modelos/pilar_form.html", {"modelo": modelo, "categorias": categorias})


@login_required
def pilar_editar(request, pk):
    pilar = get_object_or_404(Pilar.objects.select_related("modelo_evaluacion"), pk=pk)
    modelo = pilar.modelo_evaluacion
    categorias = PilarCategoria.objects.order_by("nombre")
    if request.method == "POST":
        categoria = PilarCategoria.objects.filter(pk=request.POST.get("nombre")).first()
        peso = request.POST.get("peso") or "0"
        orden = _parse_orden(request.POST.get("orden"))
        if categoria is None:
            messages.error(request, "Debe seleccionar una categoría de pilar.")
        else:
            try:
                pilar.nombre = categoria
                pilar.peso = _parse_decimal(peso, "peso (%)", 0, 100)
                pilar.orden = orden
                pilar.save()
                messages.success(request, "Pilar actualizado correctamente.")
                return redirect("contenido:modelo_detalle", pk=modelo.pk)
            except (InvalidOperation, ValidationError) as exc:
                messages.error(request, "Error al actualizar el pilar: {}".format("; ".join(exc.messages) if hasattr(exc, "messages") else exc))
    return render(request, "modelos/pilar_form.html", {
        "modelo": modelo, "pilar": pilar, "categorias": categorias, "editando": True,
    })


@login_required
def indicador_create(request, pk):
    pilar = get_object_or_404(Pilar.objects.select_related("modelo_evaluacion"), pk=pk)
    categorias = IndicadorCategoria.objects.order_by("nombre")
    if request.method == "POST":
        categoria = IndicadorCategoria.objects.filter(pk=request.POST.get("nombre")).first()
        peso = request.POST.get("peso") or "0"
        orden = _parse_orden(request.POST.get("orden"))
        if categoria is None:
            messages.error(request, "Debe seleccionar una categoría de indicador.")
        else:
            try:
                Indicador.objects.create(
                    pilar=pilar, nombre=categoria,
                    peso=_parse_decimal(peso, "peso (%)", 0, 100), orden=orden,
                )
                messages.success(request, "Indicador creado correctamente.")
                return redirect("contenido:modelo_detalle", pk=pilar.modelo_evaluacion_id)
            except (InvalidOperation, ValidationError) as exc:
                messages.error(request, "Error al crear el indicador: {}".format("; ".join(exc.messages) if hasattr(exc, "messages") else exc))
    return render(request, "modelos/indicador_form.html", {"pilar": pilar, "categorias": categorias})


@login_required
def indicador_editar(request, pk):
    indicador = get_object_or_404(
        Indicador.objects.select_related("pilar__modelo_evaluacion"), pk=pk
    )
    pilar = indicador.pilar
    categorias = IndicadorCategoria.objects.order_by("nombre")
    if request.method == "POST":
        categoria = IndicadorCategoria.objects.filter(pk=request.POST.get("nombre")).first()
        peso = request.POST.get("peso") or "0"
        orden = _parse_orden(request.POST.get("orden"))
        if categoria is None:
            messages.error(request, "Debe seleccionar una categoría de indicador.")
        else:
            try:
                indicador.nombre = categoria
                indicador.peso = _parse_decimal(peso, "peso (%)", 0, 100)
                indicador.orden = orden
                indicador.save()
                messages.success(request, "Indicador actualizado correctamente.")
                return redirect("contenido:modelo_detalle", pk=pilar.modelo_evaluacion_id)
            except (InvalidOperation, ValidationError) as exc:
                messages.error(request, "Error al actualizar el indicador: {}".format("; ".join(exc.messages) if hasattr(exc, "messages") else exc))
    return render(request, "modelos/indicador_form.html", {
        "pilar": pilar, "indicador": indicador, "categorias": categorias, "editando": True,
    })


@login_required
def subindicador_create(request, pk):
    indicador = get_object_or_404(
        Indicador.objects.select_related("pilar__modelo_evaluacion"), pk=pk
    )
    categorias = SubindicadorCategoria.objects.order_by("nombre")
    if request.method == "POST":
        categoria = SubindicadorCategoria.objects.filter(pk=request.POST.get("nombre")).first()
        peso = request.POST.get("peso") or "0"
        tipo_calculo = (request.POST.get("tipo_calculo") or "directo").strip()
        orden = _parse_orden(request.POST.get("orden"))
        if tipo_calculo not in ("mensual", "directo"):
            tipo_calculo = "directo"
        if categoria is None:
            messages.error(request, "Debe seleccionar una categoría de subindicador.")
        else:
            try:
                Subindicador.objects.create(
                    indicador=indicador, nombre=categoria,
                    peso=_parse_decimal(peso, "peso (%)", 0, 100), tipo_calculo=tipo_calculo, orden=orden,
                )
                messages.success(request, "Subindicador creado correctamente.")
                return redirect(
                    "contenido:modelo_detalle",
                    pk=indicador.pilar.modelo_evaluacion_id,
                )
            except (InvalidOperation, ValidationError) as exc:
                messages.error(request, "Error al crear el subindicador: {}".format("; ".join(exc.messages) if hasattr(exc, "messages") else exc))
    return render(request, "modelos/subindicador_form.html", {"indicador": indicador, "categorias": categorias})


@login_required
def subindicador_editar(request, pk):
    subindicador = get_object_or_404(
        Subindicador.objects.select_related("indicador__pilar__modelo_evaluacion"),
        pk=pk,
    )
    indicador = subindicador.indicador
    categorias = SubindicadorCategoria.objects.order_by("nombre")
    if request.method == "POST":
        categoria = SubindicadorCategoria.objects.filter(pk=request.POST.get("nombre")).first()
        peso = request.POST.get("peso") or "0"
        tipo_calculo = (request.POST.get("tipo_calculo") or "directo").strip()
        orden = _parse_orden(request.POST.get("orden"))
        if tipo_calculo not in ("mensual", "directo"):
            tipo_calculo = "directo"
        if categoria is None:
            messages.error(request, "Debe seleccionar una categoría de subindicador.")
        else:
            try:
                subindicador.nombre = categoria
                subindicador.peso = _parse_decimal(peso, "peso (%)", 0, 100)
                subindicador.tipo_calculo = tipo_calculo
                subindicador.orden = orden
                subindicador.save()
                messages.success(request, "Subindicador actualizado correctamente.")
                return redirect(
                    "contenido:modelo_detalle",
                    pk=indicador.pilar.modelo_evaluacion_id,
                )
            except (InvalidOperation, ValidationError) as exc:
                messages.error(request, "Error al actualizar el subindicador: {}".format("; ".join(exc.messages) if hasattr(exc, "messages") else exc))
    return render(request, "modelos/subindicador_form.html", {
        "indicador": indicador, "subindicador": subindicador,
        "categorias": categorias, "editando": True,
    })


@login_required
def criterio_create(request, pk):
    subindicador = get_object_or_404(
        Subindicador.objects.select_related("indicador__pilar__modelo_evaluacion"),
        pk=pk,
    )
    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()
        rango = (request.POST.get("rango") or "").strip()
        orden = _parse_orden(request.POST.get("orden"))
        if not nombre or not rango:
            messages.error(request, "Nombre y rango son obligatorios.")
        else:
            Criterio.objects.create(
                subindicador=subindicador, nombre=nombre, rango=rango, orden=orden,
            )
            messages.success(request, "Criterio creado correctamente.")
            return redirect(
                "contenido:modelo_detalle",
                pk=subindicador.indicador.pilar.modelo_evaluacion_id,
            )
    return render(request, "modelos/criterio_form.html", {"subindicador": subindicador})


@login_required
def criterio_editar(request, pk):
    criterio = get_object_or_404(
        Criterio.objects.select_related("subindicador__indicador__pilar__modelo_evaluacion"),
        pk=pk,
    )
    subindicador = criterio.subindicador
    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()
        rango = (request.POST.get("rango") or "").strip()
        orden = _parse_orden(request.POST.get("orden"))
        if not nombre or not rango:
            messages.error(request, "Nombre y rango son obligatorios.")
        else:
            criterio.nombre = nombre
            criterio.rango = rango
            criterio.orden = orden
            criterio.save()
            messages.success(request, "Criterio actualizado correctamente.")
            return redirect(
                "contenido:modelo_detalle",
                pk=subindicador.indicador.pilar.modelo_evaluacion_id,
            )
    return render(request, "modelos/criterio_form.html", {
        "subindicador": subindicador, "criterio": criterio, "editando": True,
    })


# ------------------------------------------------- Catalogos de categorias
# Los nombres de pilar/indicador/subindicador son FK a estos catalogos.
# Vistas genericas para gestionarlos (listar / crear / editar) desde el front.
CATEGORIA_TIPOS = {
    "pilar": {
        "model": PilarCategoria, "rel": "pilar", "max_length": 150,
        "singular": "categoría de pilar", "plural": "Categorías de pilar",
    },
    "indicador": {
        "model": IndicadorCategoria, "rel": "indicador", "max_length": 255,
        "singular": "categoría de indicador", "plural": "Categorías de indicador",
    },
    "subindicador": {
        "model": SubindicadorCategoria, "rel": "subindicador", "max_length": 255,
        "singular": "categoría de subindicador", "plural": "Categorías de subindicador",
    },
}


def _cfg_categoria(tipo):
    cfg = CATEGORIA_TIPOS.get(tipo)
    if cfg is None:
        raise Http404("Tipo de categoría no válido.")
    return cfg


@login_required
def categoria_list(request, tipo):
    cfg = _cfg_categoria(tipo)
    categorias = (
        cfg["model"].objects
        .annotate(n_uso=Count(cfg["rel"]))
        .order_by("nombre")
    )
    return render(request, "categorias/categoria_list.html", {
        "tipo": tipo, "cfg": cfg, "categorias": categorias,
    })


@login_required
def categoria_create(request, tipo):
    cfg = _cfg_categoria(tipo)
    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()
        if not nombre:
            messages.error(request, "El nombre es obligatorio.")
        else:
            cfg["model"].objects.create(nombre=nombre[: cfg["max_length"]])
            messages.success(request, "Categoría creada correctamente.")
            return redirect("contenido:categoria_list", tipo=tipo)
    return render(request, "categorias/categoria_form.html", {"tipo": tipo, "cfg": cfg})


@login_required
def categoria_editar(request, tipo, pk):
    cfg = _cfg_categoria(tipo)
    obj = get_object_or_404(cfg["model"], pk=pk)
    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()
        if not nombre:
            messages.error(request, "El nombre es obligatorio.")
        else:
            obj.nombre = nombre[: cfg["max_length"]]
            obj.save()
            messages.success(request, "Categoría actualizada correctamente.")
            return redirect("contenido:categoria_list", tipo=tipo)
    return render(request, "categorias/categoria_form.html", {
        "tipo": tipo, "cfg": cfg, "obj": obj, "editando": True,
    })


# =========================================================================
#                                EVALUACIONES
# =========================================================================
class EvaluacionListView(LoginRequiredMixin, ListView):
    model = Evaluacion
    template_name = "evaluaciones/evaluacion_list.html"
    context_object_name = "evaluaciones"

    def get_queryset(self):
        # Solo evaluaciones de periodos activos: si el periodo esta inactivo,
        # sus evaluaciones no aparecen en el listado operativo (los datos siguen
        # en BD; se vuelven a ver al reactivar el periodo).
        return (
            Evaluacion.objects
            .filter(periodo__activo=True)
            .select_related("periodo", "dependencia", "modelo_evaluacion")
            .annotate(suma_ponderacion=Sum("evaluacionresultado__ponderacion"))
            .order_by("-creado_en")
        )


class EvaluacionCreateView(LoginRequiredMixin, CreateView):
    model = Evaluacion
    fields = ["periodo", "dependencia", "categoria"]
    template_name = "evaluaciones/evaluacion_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["dependencia"].queryset = (
            Dependencia.objects
            .filter(dependenciamodelo__activo=True)
            .distinct()
            .order_by("nombre")
        )
        form.fields["periodo"].queryset = Periodo.objects.filter(activo=True).order_by(
            F("orden").asc(nulls_last=True), "-creado_en"
        )
        form.fields["categoria"].queryset = _orden_nombre(Categoria.objects.all())
        return form

    def form_valid(self, form):
        periodo = form.cleaned_data["periodo"]
        dependencia = form.cleaned_data["dependencia"]
        categoria = form.cleaned_data["categoria"]
        if Evaluacion.objects.filter(periodo=periodo, dependencia=dependencia).exists():
            form.add_error(None,
                "Ya existe una evaluacion registrada para esa combinacion de "
                "periodo y dependencia.",
            )
            return self.form_invalid(form)
        asignacion = (
            DependenciaModelo.objects.select_related("modelo")
            .filter(dependencia=dependencia, activo=True).first()
        )
        if asignacion is None:
            form.add_error("dependencia",
                "La dependencia no tiene un modelo de evaluacion activo asignado.",
            )
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                self.object = Evaluacion.objects.create(
                    periodo=periodo, dependencia=dependencia,
                    modelo_evaluacion=asignacion.modelo, categoria=categoria,
                )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
            return self.form_invalid(form)
        messages.success(self.request,
            "Evaluacion creada con el modelo activo «{}». "
            "Puede diligenciarla a continuacion.".format(asignacion.modelo))
        return HttpResponseRedirect(
            reverse("contenido:evaluacion_diligenciar", args=[self.object.pk])
        )


@login_required
def evaluacion_diligenciar(request, pk):
    """
    Diligencia una evaluacion. Los usuarios pueden ver toda la jerarquia,
    pero solo editan subindicadores cuyo indicador este en su
    PerfilUsuario.indicadores (superusers editan todo).
    """
    evaluacion = get_object_or_404(
        Evaluacion.objects.select_related(
            "periodo", "dependencia", "modelo_evaluacion"),
        pk=pk,
    )
    # Si el periodo esta inactivo, la evaluacion no esta disponible para
    # diligenciamiento (apertura/cierre de periodos controla la edicion).
    if not evaluacion.periodo.activo:
        messages.warning(
            request,
            "El periodo «{}» esta inactivo; la evaluacion no esta disponible "
            "para diligenciamiento.".format(evaluacion.periodo),
        )
        return redirect("contenido:evaluacion_list")
    meses_aplicables = meses_del_periodo(evaluacion.periodo)
    indicadores_editables = _indicadores_editables_ids(request.user)
    usuario_es_superuser = request.user.is_superuser
    n_editables = (
        "(todos)" if indicadores_editables is None
        else len(indicadores_editables)
    )

    pilares_qs = (
        _orden_nombre(
            Pilar.objects.filter(modelo_evaluacion=evaluacion.modelo_evaluacion)
        ).prefetch_related(
            Prefetch(
                "indicador_set",
                queryset=_orden_nombre(Indicador.objects.all()).prefetch_related(
                    Prefetch(
                        "subindicador_set",
                        queryset=_orden_nombre(Subindicador.objects.all()).prefetch_related(
                            Prefetch(
                                "criterio_set",
                                queryset=_orden_nombre(Criterio.objects.all()),
                            )
                        ),
                    )
                ),
            )
        )
    )
    pilares = list(pilares_qs)

    resultados_actuales = {
        r.subindicador_id: r
        for r in EvaluacionResultado.objects.filter(evaluacion=evaluacion)
        .prefetch_related("evaluacionresultadodetalle_set")
    }
    detalles_por_sub = {
        r.subindicador_id: {
            d.mes: d for d in r.evaluacionresultadodetalle_set.all()
        }
        for r in resultados_actuales.values()
    }

    if request.method == "POST":
        # Si el usuario no puede editar nada (no superuser, sin perfil ni
        # indicadores asignados), rechazamos el POST con mensaje claro.
        if indicadores_editables is not None and not indicadores_editables:
            messages.error(
                request,
                "No tiene indicadores asignados. Contacte a un administrador.",
            )
            return redirect("contenido:evaluacion_diligenciar", pk=evaluacion.pk)

        try:
            with transaction.atomic():
                for pilar in pilares:
                    for indicador in pilar.indicador_set.all():
                        # Saltamos completos los indicadores que el usuario
                        # no puede editar (sus inputs llegan readonly pero
                        # ignoramos cualquier cosa que llegue via POST manual).
                        if not _puede_editar(indicadores_editables, indicador.pk):
                            continue

                        for sub in indicador.subindicador_set.all():
                            observaciones = request.POST.get(
                                "observaciones_{}".format(sub.pk), ""
                            ).strip()
                            peso_sub = Decimal(sub.peso)

                            if sub.tipo_calculo == "mensual":
                                puntajes_mes = {}
                                for mes_num, _ in meses_aplicables:
                                    raw = request.POST.get(
                                        "puntaje_{}_{}".format(sub.pk, mes_num), ""
                                    ).strip()
                                    if raw:
                                        puntajes_mes[mes_num] = _parse_decimal(
                                            raw, "puntaje de «{}» (mes {})".format(sub, mes_num), 0, 100
                                        )
                                if not puntajes_mes:
                                    EvaluacionResultado.objects.filter(
                                        evaluacion=evaluacion, subindicador=sub,
                                    ).delete()
                                    continue
                                ponderaciones_mes = {
                                    m: (p * peso_sub / Decimal("100"))
                                    for m, p in puntajes_mes.items()
                                }
                                n = Decimal(len(puntajes_mes))
                                puntaje_avg = sum(puntajes_mes.values()) / n
                                ponderacion_avg = sum(ponderaciones_mes.values()) / n
                                resultado, _ = EvaluacionResultado.objects.update_or_create(
                                    evaluacion=evaluacion, subindicador=sub,
                                    defaults={
                                        "puntaje": _q5(puntaje_avg),
                                        "ponderacion": _q5(ponderacion_avg),
                                        "observaciones": observaciones,
                                    },
                                )
                                for mes_num, puntaje_mes in puntajes_mes.items():
                                    EvaluacionResultadoDetalle.objects.update_or_create(
                                        resultado=resultado, mes=mes_num,
                                        defaults={
                                            "puntaje": _q5(puntaje_mes),
                                            "ponderacion": _q5(ponderaciones_mes[mes_num]),
                                        },
                                    )
                                EvaluacionResultadoDetalle.objects.filter(
                                    resultado=resultado
                                ).exclude(mes__in=puntajes_mes.keys()).delete()
                            else:  # directo o NULL
                                puntaje_raw = request.POST.get(
                                    "puntaje_{}".format(sub.pk), ""
                                ).strip()
                                if not puntaje_raw:
                                    continue
                                puntaje = _parse_decimal(
                                    puntaje_raw, "puntaje de «{}»".format(sub), 0, 100
                                )
                                ponderacion = puntaje * peso_sub / Decimal("100")
                                EvaluacionResultado.objects.update_or_create(
                                    evaluacion=evaluacion, subindicador=sub,
                                    defaults={
                                        "puntaje": _q5(puntaje),
                                        "ponderacion": _q5(ponderacion),
                                        "observaciones": observaciones,
                                    },
                                )
            messages.success(request, "Evaluacion guardada correctamente.")
            return redirect("contenido:evaluacion_diligenciar", pk=evaluacion.pk)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    matriz = []
    total_subindicadores = 0
    total_editables = 0
    for pilar in pilares:
        pilar_rowspan = 0
        indicadores_data = []
        for indicador in pilar.indicador_set.all():
            editable_ind = _puede_editar(indicadores_editables, indicador.pk)
            sub_list = list(indicador.subindicador_set.all())
            for sub in sub_list:
                resultado = resultados_actuales.get(sub.pk)
                sub.editable = editable_ind  # heredado del indicador
                sub.es_mensual = sub.tipo_calculo == "mensual"
                if sub.es_mensual:
                    detalles = detalles_por_sub.get(sub.pk, {})
                    sub.meses_render = [
                        (
                            mes_num, mes_label,
                            str(detalles[mes_num].puntaje) if mes_num in detalles else "",
                        )
                        for mes_num, mes_label in meses_aplicables
                    ]
                    sub.puntaje_actual = ""
                else:
                    sub.puntaje_actual = str(resultado.puntaje) if resultado else ""
                sub.ponderacion_actual = str(resultado.ponderacion) if resultado else ""
                sub.observaciones_actual = resultado.observaciones if resultado else ""
                if editable_ind:
                    total_editables += 1
            indicadores_data.append({
                "indicador": indicador,
                "editable": editable_ind,
                "subindicadores": sub_list,
                "rowspan": max(len(sub_list), 1),
            })
            pilar_rowspan += max(len(sub_list), 1)
        matriz.append({
            "pilar": pilar,
            "indicadores": indicadores_data,
            "rowspan": max(pilar_rowspan, 1),
        })
        total_subindicadores += pilar_rowspan

    return render(request, "evaluaciones/evaluacion_diligenciar.html", {
        "evaluacion": evaluacion,
        "matriz": matriz,
        "meses_aplicables": meses_aplicables,
        "total_subindicadores": total_subindicadores,
        "total_resultados_guardados": len(resultados_actuales),
        "total_editables": total_editables,
        "usuario_es_superuser": usuario_es_superuser,
        "n_indicadores_asignados": n_editables,
        "puede_editar_algo": (indicadores_editables is None) or bool(indicadores_editables),
    })


# =========================================================================
#                                 PERIODOS
# =========================================================================
class PeriodoListView(LoginRequiredMixin, ListView):
    """Gestion de periodos: ver estado y activar/desactivar.

    Activar/desactivar un periodo abre o cierra la visibilidad y el
    diligenciamiento de TODAS sus evaluaciones, sin borrar informacion.
    """
    model = Periodo
    template_name = "periodos/periodo_list.html"
    context_object_name = "periodos"

    def get_queryset(self):
        return (
            Periodo.objects
            .annotate(n_evaluaciones=Count("evaluacion"))
            .order_by("-activo", F("orden").asc(nulls_last=True), "-creado_en")
        )


def _periodo_set_estado(request, pk, activo):
    periodo = get_object_or_404(Periodo, pk=pk)
    if request.method == "POST":
        if periodo.activo != activo:
            periodo.activo = activo
            periodo.save(update_fields=["activo", "actualizado_en"])
        estado = "activado" if activo else "desactivado"
        messages.success(request, "Periodo «{}» {}.".format(periodo, estado))
    return redirect("contenido:periodo_list")


@login_required
def periodo_activar(request, pk):
    return _periodo_set_estado(request, pk, True)


@login_required
def periodo_desactivar(request, pk):
    return _periodo_set_estado(request, pk, False)


def _periodo_set_publico(request, pk, publico):
    """Marca un periodo como público/privado para el reporte público (/reporte/).

    No afecta al dashboard interno (que ve todos los periodos)."""
    periodo = get_object_or_404(Periodo, pk=pk)
    if request.method == "POST":
        if periodo.publico != publico:
            periodo.publico = publico
            periodo.save(update_fields=["publico", "actualizado_en"])
        estado = "publicado" if publico else "retirado del reporte público"
        messages.success(request, "Periodo «{}» {}.".format(periodo, estado))
    return redirect("contenido:periodo_list")


@login_required
def periodo_publicar(request, pk):
    return _periodo_set_publico(request, pk, True)


@login_required
def periodo_despublicar(request, pk):
    return _periodo_set_publico(request, pk, False)


@login_required
def periodo_umbral_editar(request, pk):
    """Formulario para crear/editar la vigencia (año) y el umbral (objetivo % del
    ranking) de un periodo. Umbral vacío = sin meta (no se dibuja la línea en el
    Ranking)."""
    periodo = get_object_or_404(Periodo, pk=pk)
    if request.method == "POST":
        try:
            umbral_raw = request.POST.get("umbral", "").strip()
            vigencia_raw = request.POST.get("vigencia", "").strip()
            if umbral_raw == "":
                periodo.umbral = None
            else:
                umbral = _parse_decimal(umbral_raw, "umbral", 0, 100)
                if umbral > Decimal("99.99"):
                    raise ValidationError("El umbral máximo es 99.99 (límite del campo).")
                periodo.umbral = umbral
            if vigencia_raw == "":
                periodo.vigencia = None
            elif vigencia_raw.isdigit() and 1900 <= int(vigencia_raw) <= 2200:
                periodo.vigencia = int(vigencia_raw)
            else:
                raise ValidationError("La vigencia debe ser un año válido (p. ej. 2025).")
            periodo.save(update_fields=["umbral", "vigencia", "actualizado_en"])
            messages.success(request, "Periodo «{}» actualizado.".format(periodo))
            return redirect("contenido:periodo_list")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return render(request, "periodos/periodo_umbral_form.html", {"periodo": periodo})
