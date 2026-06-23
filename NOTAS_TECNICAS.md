# Notas técnicas — Modelo de Alta Gerencia (MAG)

> Documento de referencia técnica. Está organizado en tres partes:
>
> 1. **Parte I — Los modelos:** qué es cada tabla de la base de datos, para qué sirve
>    y qué reglas trae incrustadas.
> 2. **Parte II — Ejemplo guiado:** un caso completo (de crear el modelo hasta ver el
>    reporte) explicando, paso a paso, qué función se ejecuta y qué hace por dentro.
> 3. **Parte III — Glosario del ORM:** qué hace *detrás de cámara* cada operador de
>    acceso a datos (qué SQL genera y cuándo golpea la base de datos).
>
> Complementa a `README.md` (puesta en marcha) y `DOCUMENTACION.md` (funcional).
> Código: `mag/contenido/{models,views,urls,roles,middleware}.py`.

---

# Parte I — Los modelos de la base de datos

La estructura de una evaluación es un **árbol versionado**, y la operación gira en
torno a ese árbol:

```
ModeloEvaluacion (versión)          ← el "molde" de la evaluación
   └── Pilar             (peso %)
         └── Indicador   (peso %)
               └── Subindicador  (peso % · tipo de cálculo)   ← lo que se diligencia
                     └── Criterio (rangos de referencia, texto)

Dependencia ──< DependenciaModelo >── ModeloEvaluacion   ← qué molde aplica a cada quién
Periodo                                                  ← cuándo se evalúa
Evaluacion = (Periodo + Dependencia + Modelo congelado)
   └── EvaluacionResultado            (puntaje/ponderación por Subindicador)
         └── EvaluacionResultadoDetalle  (un valor por mes; solo cálculo "mensual")
```

Todos los modelos —salvo `PerfilUsuario` y `EvaluacionResultadoDetalle`— heredan de la
clase abstracta **`Fechas`**, que aporta dos columnas automáticas:

```python
class Fechas(models.Model):
    creado_en      = models.DateTimeField(auto_now_add=True)   # se fija al INSERT
    actualizado_en = models.DateTimeField(auto_now=True)       # se reescribe en cada save()
    class Meta:
        abstract = True            # no crea tabla propia; aporta columnas a quien herede
```

`auto_now_add=True` → Django pone la fecha **solo al crear**. `auto_now=True` → Django
la sobrescribe **en cada `.save()`**. Por eso `actualizado_en` solo cambia por rutas que
pasen por `.save()` (no por `QuerySet.update()`; ver Parte III).

## 1. Modelos de estructura (parametrización)

### `ModeloEvaluacion`
La **raíz versionada** del árbol. Cada fila es un molde de evaluación independiente.

```python
class ModeloEvaluacion(Fechas):
    nombre  = models.CharField(max_length=150)
    version = models.IntegerField()
    activo  = models.BooleanField()
```

- Función: agrupar toda la jerarquía (pilares→…→criterios) de una versión.
- `version` permite tener "MAG v1", "MAG v2"… coexistiendo. `activo` marca cuáles están
  vigentes para asignarse a dependencias.

### `Dependencia`
La **entidad evaluada** (secretaría, oficina, etc.). Solo guarda `nombre`. Es una
entidad **permanente**: las evaluaciones apuntan a ella directamente.

### `DependenciaModelo` — el puente
Tabla intermedia (*junction*) entre `Dependencia` y `ModeloEvaluacion`. Responde a la
pregunta: **¿qué molde aplica a esta dependencia, y cuál está vigente?**

```python
class DependenciaModelo(Fechas):
    modelo      = models.ForeignKey(ModeloEvaluacion, on_delete=models.CASCADE)
    dependencia = models.ForeignKey(Dependencia, on_delete=models.CASCADE)
    activo      = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dependencia"], condition=models.Q(activo=True),
                name="unique_modelo_activo_por_dependencia"),   # 1 activo por dependencia
            models.UniqueConstraint(
                fields=["dependencia", "modelo"],
                name="unique_dependencia_modelo"),              # no duplicar el par
        ]
```

El primer constraint es un **índice único parcial** (`WHERE activo`): la BD garantiza que
una dependencia no tenga dos modelos activos a la vez. Es solo un *puente de decisión* al
crear la evaluación; no se referencia después (ver Parte II, paso 6).

### `Pilar`, `Indicador`, `Subindicador`
Los tres niveles internos del árbol. Cada uno apunta con FK a su padre, tiene `orden`,
`peso` (Decimal 5,2) y su `nombre` es una **FK a un catálogo**:

```python
class Pilar(Fechas):
    orden  = models.IntegerField(null=True)
    modelo_evaluacion = models.ForeignKey(ModeloEvaluacion, on_delete=models.CASCADE)
    nombre = models.ForeignKey(PilarCategoria, on_delete=models.CASCADE)   # nombre = catálogo
    peso   = models.DecimalField(max_digits=5, decimal_places=2)

class Indicador(Fechas):
    orden  = models.IntegerField(null=True)
    pilar  = models.ForeignKey(Pilar, on_delete=models.CASCADE)
    nombre = models.ForeignKey(IndicadorCategoria, on_delete=models.CASCADE)
    peso   = models.DecimalField(max_digits=5, decimal_places=2)

class Subindicador(Fechas):
    orden  = models.IntegerField(null=True)
    indicador = models.ForeignKey(Indicador, on_delete=models.CASCADE)
    nombre = models.ForeignKey(SubindicadorCategoria, on_delete=models.CASCADE)
    peso   = models.DecimalField(max_digits=5, decimal_places=2)
    tipo_calculo = models.CharField(
        max_length=20, choices=(("mensual","Mensual"),("directo","Directo")), null=True)
```

- El **`Subindicador`** es la **unidad que efectivamente se diligencia**: ahí se captura
  el puntaje. `tipo_calculo` decide si se captura un valor único (`directo`) o uno por
  mes (`mensual`).
- `on_delete=CASCADE` en toda la cadena: borrar un `ModeloEvaluacion` arrastra sus
  pilares→indicadores→subindicadores→criterios.

### `Criterio`
Tabla de **rangos de referencia** del subindicador (texto). No se diligencia; orienta al
evaluador sobre qué puntaje asignar. Campos: `orden`, `nombre` (texto), `rango` (texto).

### Catálogos de nombres
`PilarCategoria`, `IndicadorCategoria`, `SubindicadorCategoria` (y `Categoria` auxiliar):
listas reutilizables de nombres. Por eso `Pilar.nombre` no es texto sino una FK — permite
reutilizar y renombrar nombres sin tocar cada fila.

## 2. Modelos de operación

### `Periodo`
La ventana temporal. Dos flags con semántica distinta:

```python
class Periodo(Fechas):
    orden   = models.IntegerField(null=True)
    nombre  = models.CharField(max_length=100)
    activo  = models.BooleanField(default=True)    # abre/cierra el diligenciamiento
    publico = models.BooleanField(default=False)   # visible en el reporte público
```

### `Evaluacion`
El **hecho histórico**: una dependencia evaluada en un periodo, con un modelo **congelado**.

```python
class Evaluacion(Fechas):
    periodo           = models.ForeignKey(Periodo, on_delete=models.CASCADE)
    dependencia       = models.ForeignKey(Dependencia, on_delete=models.CASCADE)
    modelo_evaluacion = models.ForeignKey(ModeloEvaluacion, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["periodo","dependencia"],
                                    name="unique_periodo_dependencia")]

    def clean(self):
        if self.pk:                                    # solo al EDITAR (ya tiene pk)
            original = Evaluacion.objects.filter(pk=self.pk).first()
            if original and original.modelo_evaluacion_id != self.modelo_evaluacion_id:
                raise ValidationError("No se puede cambiar el modelo de una evaluación existente")

    def save(self, *args, **kwargs):
        self.full_clean()                              # corre clean() SIEMPRE, también en admin
        super().save(*args, **kwargs)
```

- Guarda `dependencia` **y** `modelo_evaluacion` por separado (no un FK al puente). Es
  **desnormalización deliberada** (patrón *snapshot*): la evaluación queda autónoma y el
  histórico no se rompe si luego se reasigna o borra la fila de `DependenciaModelo`.
- `UniqueConstraint(periodo, dependencia)` → no dos evaluaciones de la misma dependencia
  en el mismo periodo.
- `clean()` + `save()` → el `modelo_evaluacion` es **inmutable** una vez creado.

### `EvaluacionResultado`
El resultado por subindicador: puntaje capturado + ponderación calculada + observaciones.

```python
class EvaluacionResultado(Fechas):
    evaluacion   = models.ForeignKey(Evaluacion, on_delete=models.CASCADE)
    subindicador = models.ForeignKey(Subindicador, on_delete=models.CASCADE)
    puntaje      = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    ponderacion  = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    observaciones= models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["evaluacion","subindicador"],
                                               name="unique_evaluacion_subindicador")]
        indexes = [models.Index(fields=["evaluacion"]), models.Index(fields=["subindicador"])]

    def clean(self):
        if self.subindicador.indicador.pilar.modelo_evaluacion_id != self.evaluacion.modelo_evaluacion_id:
            raise ValidationError("El subindicador no pertenece al modelo de la evaluación")
        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
```

- `UniqueConstraint(evaluacion, subindicador)` → un único resultado por subindicador en
  cada evaluación (clave para que `update_or_create` actúe como "upsert"; ver Parte III).
- `clean()` → **coherencia**: el subindicador debe pertenecer al modelo de la evaluación.
- Los `indexes` aceleran los filtros del reporte (`filter(evaluacion=…)`, etc.).

### `EvaluacionResultadoDetalle`
Desglose **mensual** de un resultado (solo subindicadores `tipo_calculo='mensual'`).

```python
class EvaluacionResultadoDetalle(models.Model):       # NO hereda de Fechas
    resultado   = models.ForeignKey(EvaluacionResultado, on_delete=models.CASCADE)
    mes         = models.IntegerField(choices=Meses.choices,
                    validators=[MinValueValidator(1), MaxValueValidator(12)])
    puntaje     = models.DecimalField(max_digits=5, decimal_places=2)
    ponderacion = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["resultado","mes"],
                                               name="unique_resultado_mes")]
```

`Meses` es un `IntegerChoices` (1=Enero … 12=Diciembre): no es tabla, es una enumeración.
`UniqueConstraint(resultado, mes)` → un solo valor por mes y resultado.

## 3. Modelo de seguridad

### `PerfilUsuario`
Relaciona un `User` con los `Indicador`es que puede **editar** al diligenciar.

```python
class PerfilUsuario(models.Model):                    # NO hereda de Fechas
    usuario     = models.OneToOneField(User, on_delete=models.CASCADE)
    indicadores = models.ManyToManyField(Indicador, blank=True)
```

`OneToOneField` → un perfil por usuario. `ManyToManyField` → Django crea una **tabla
intermedia oculta** (`perfilusuario_indicadores`) con pares `(perfil_id, indicador_id)`.
El rol **Evaluador** no es un modelo: es un **Group** de Django (ver Parte II, paso 8).

---

# Parte II — Ejemplo guiado de punta a punta

Seguiremos un caso concreto y, en cada paso, abriremos el "detrás de cámara": qué vista
se ejecuta, qué funciones llama y qué hace cada operación del ORM. Los operadores
marcados con → se explican a fondo en la **Parte III**.

**El caso:**
- Modelo: **"MAG 2026"**, versión 1.
- Dependencia: **"Secretaría de Educación"**.
- Árbol (resumido): Pilar *Gestión* → Indicador *Eficiencia* con dos subindicadores:
  - *Ejecución presupuestal*, peso **5.40**, tipo **directo**.
  - *Avance mensual*, peso **3.60**, tipo **mensual**.
- Periodo: **"Primer Trimestre (Enero Febrero Marzo) 2026"**.

## Paso 1 — Crear el modelo

Vista: `ModeloEvaluacionCreateView` (CBV `CreateView`). Al enviar el formulario, Django
ejecuta internamente:

```python
ModeloEvaluacion.objects.create(nombre="MAG 2026", version=1, activo=True)
```

→ `.create()` arma un `INSERT INTO contenido_modeloevaluacion (...)`, lo ejecuta y
devuelve el objeto ya con su `pk`. Como `ModeloEvaluacion` hereda de `Fechas`,
`creado_en`/`actualizado_en` se rellenan solos.

## Paso 2 — Crear la dependencia

Igual de simple: `Dependencia.objects.create(nombre="Secretaría de Educación")`.

## Paso 3 — Asignar modelo ↔ dependencia (regla del "único activo")

Vista: **`dependencia_modelo_asignar(request, pk)`**. El corazón:

```python
with transaction.atomic():                                   # → abre transacción
    if activo:
        DependenciaModelo.objects.filter(                    # → SELECT … WHERE
            dependencia=dependencia, activo=True
        ).update(activo=False)                               # → UPDATE directo (sin save())
    DependenciaModelo.objects.update_or_create(              # → SELECT y luego INSERT o UPDATE
        modelo=modelo, dependencia=dependencia,
        defaults={"activo": activo},
    )
```

Detrás de cámara, en orden:

1. **`transaction.atomic()`** envuelve todo en una transacción: si algo falla a mitad,
   se revierte completo (no queda la dependencia sin modelo activo ni con dos).
2. **`.filter(dependencia=…, activo=True)`** construye un `QuerySet` perezoso (todavía no
   consulta nada). El `activo=True` se traduce a `WHERE activo = true`.
3. **`.update(activo=False)`** es **terminal**: ejecuta de inmediato un
   `UPDATE … SET activo=false WHERE dependencia_id=… AND activo=true`. Apaga el modelo
   activo previo. **Salta `save()`/`clean()`** y no toca `actualizado_en`.
4. **`.update_or_create(modelo=…, dependencia=…, defaults={...})`**: hace un `SELECT` por
   `(modelo, dependencia)`; si existe, lo actualiza con `defaults`; si no, lo crea. Así
   reactivar un modelo ya conocido no rompe el `UniqueConstraint(dependencia, modelo)`.

Resultado: la Secretaría queda con **MAG 2026** como su único modelo activo.

## Paso 4 — Construir el árbol (pilares, indicadores, subindicadores)

Vista (ejemplo, `pilar_create(request, pk)`):

```python
categoria = PilarCategoria.objects.filter(pk=request.POST.get("nombre")).first()   # → SELECT … LIMIT 1
peso  = request.POST.get("peso") or "0"
orden = _parse_orden(request.POST.get("orden"))                                    # texto → int|None
if categoria is None:
    messages.error(request, "Debe seleccionar una categoría de pilar.")
else:
    Pilar.objects.create(                                                          # → INSERT
        modelo_evaluacion=modelo, nombre=categoria,
        peso=_parse_decimal(peso, "peso (%)", 0, 100), orden=orden,
    )
```

Funciones auxiliares que entran aquí:

- **`_parse_orden(raw)`** — normaliza el texto del input a `int` o `None`:
  ```python
  def _parse_orden(raw):
      raw = (raw or "").strip()
      if not raw:
          return None
      try:    return int(raw)
      except (TypeError, ValueError):  return None
  ```
  Si llega vacío o no numérico, devuelve `None` (el campo `orden` admite NULL).

- **`_parse_decimal(raw, etiqueta, minimo, maximo)`** — el validador decimal central de
  todo el registro. Detrás de cámara:
  ```python
  def _parse_decimal(raw, etiqueta="valor", minimo=None, maximo=None):
      s = "" if raw is None else str(raw).strip()
      if s == "": raise ValidationError("El {} está vacío.".format(etiqueta))
      n_coma, n_punto = s.count(","), s.count(".")
      if n_coma and n_punto:                 # "1.234,5" → mezcla → error
          raise ValidationError("...separadores mezclados...")
      if n_coma > 1 or n_punto > 1:          # "3,6,0" → repetido → error
          raise ValidationError("...más de un separador...")
      try:    valor = Decimal(s.replace(",", "."))   # normaliza coma → punto
      except InvalidOperation:               # texto no numérico
          raise ValidationError("...no es un número válido.")
      if minimo is not None and valor < minimo: raise ValidationError("...menor que...")
      if maximo is not None and valor > maximo: raise ValidationError("...mayor que...")
      return valor
  ```
  Acepta **un solo** separador (coma o punto), lo normaliza a punto para que `Decimal`
  lo entienda, y valida el rango 0–100. Lanza `ValidationError` con mensaje legible que
  la vista atrapa y muestra. (Detalle de por qué es necesario: ver Parte IV, decimales.)

Se repite la misma mecánica para `indicador_create` y `subindicador_create` (este último
guarda además `tipo_calculo`). Al terminar, el árbol del modelo está completo.

## Paso 5 — Crear el periodo

`Periodo.objects.create(nombre="Primer Trimestre (Enero Febrero Marzo) 2026", activo=True)`.
El nombre **importa para el cálculo mensual**: de él se infieren los meses (paso 7).

## Paso 6 — Crear la evaluación (deriva y congela el modelo)

Vista: **`EvaluacionCreateView.form_valid`**.

```python
periodo     = form.cleaned_data["periodo"]
dependencia = form.cleaned_data["dependencia"]

if Evaluacion.objects.filter(periodo=periodo, dependencia=dependencia).exists():   # → SELECT EXISTS
    form.add_error(None, "Ya existe una evaluacion para esa combinación…")
    return self.form_invalid(form)

asignacion = (
    DependenciaModelo.objects.select_related("modelo")        # → JOIN para traer el modelo
    .filter(dependencia=dependencia, activo=True).first()     # → SELECT … LIMIT 1
)
if asignacion is None:
    form.add_error("dependencia", "La dependencia no tiene un modelo … activo asignado.")
    return self.form_invalid(form)

with transaction.atomic():
    self.object = Evaluacion.objects.create(                  # → INSERT (pasa por save()→full_clean())
        periodo=periodo, dependencia=dependencia,
        modelo_evaluacion=asignacion.modelo,                  # COPIA el modelo (snapshot)
    )
```

Detrás de cámara:

1. **`.filter(...).exists()`** → `SELECT 1 … WHERE periodo_id=… AND dependencia_id=… LIMIT 1`,
   devuelve `True`/`False`. Evita violar el `UniqueConstraint(periodo, dependencia)` con un
   mensaje amigable en vez de un `IntegrityError`.
2. **`select_related("modelo")`** → hace que el `SELECT` traiga, con un `JOIN`, la fila de
   `ModeloEvaluacion` en la misma consulta. Así, al leer `asignacion.modelo` **no** se
   dispara una segunda query.
3. **`.first()`** → añade `LIMIT 1` y devuelve el objeto o `None`. Aquí el constraint
   parcial garantiza que solo hay una fila activa.
4. **`.create(...)`** pasa por `Evaluacion.save()` → `full_clean()` → `clean()`. Como es
   un alta (`self.pk` aún no existe), el `clean()` de inmutabilidad no se dispara. El
   `modelo_evaluacion` queda **copiado y congelado** en la evaluación. De aquí en adelante
   la evaluación **ya no consulta** `DependenciaModelo`.

## Paso 7 — Diligenciar la evaluación (el paso más denso)

Vista: **`evaluacion_diligenciar(request, pk)`**. Tiene tres bloques: cargar el árbol y los
resultados existentes (GET), procesar el guardado (POST) y armar la matriz para la
plantilla.

### 7.a — Cargar el árbol con una sola "ráfaga" de queries

```python
evaluacion = get_object_or_404(
    Evaluacion.objects.select_related("periodo","dependencia","modelo_evaluacion"), pk=pk)

if not evaluacion.periodo.activo:           # periodo cerrado → no se diligencia
    messages.warning(request, "El periodo … esta inactivo …")
    return redirect("contenido:evaluacion_list")

meses_aplicables = meses_del_periodo(evaluacion.periodo)   # infiere [(1,Enero),(2,Febrero),(3,Marzo)]

pilares = list(
    _orden_nombre(Pilar.objects.filter(modelo_evaluacion=evaluacion.modelo_evaluacion))
    .prefetch_related(
        Prefetch("indicador_set",
            queryset=_orden_nombre(Indicador.objects.all()).prefetch_related(
                Prefetch("subindicador_set",
                    queryset=_orden_nombre(Subindicador.objects.all()).prefetch_related(
                        Prefetch("criterio_set", queryset=_orden_nombre(Criterio.objects.all())))))))
)
```

Detrás de cámara:

- **`get_object_or_404(...select_related(3 FKs)...)`** → un `SELECT` con tres `JOIN`
  (periodo, dependencia, modelo). Si no existe la pk, lanza 404. Con un solo viaje a la
  BD ya tenemos la evaluación y sus tres relaciones.
- **`meses_del_periodo(periodo)`** → función de negocio que **infiere los meses del
  nombre del periodo**:
  ```python
  def meses_del_periodo(periodo):
      nombre = _normaliza(periodo.nombre)                       # sin tildes, minúsculas
      encontrados = [(v, l) for v, l in Meses.choices if _normaliza(l) in nombre]
      return encontrados or list(Meses.choices)                 # si no reconoce ninguno → los 12
  ```
  Con nuestro periodo, encuentra **Enero, Febrero y Marzo**.
- El bloque de **`prefetch_related` + `Prefetch`** baja **todo el árbol** del modelo
  (pilares→indicadores→subindicadores→criterios) en pocas queries (una por nivel), cada
  nivel ya ordenado por `_orden_nombre`. Sin esto, recorrer el árbol en la plantilla
  dispararía cientos de consultas (problema "N+1"). Ver Parte III para el detalle de
  `prefetch_related` vs `select_related`.
- **`_orden_nombre(qs)`** → `qs.order_by(F("orden").asc(nulls_last=True), "nombre")`:
  ordena por `orden` dejando los `NULL` al final, y desempata por `nombre`.

Luego se cargan los resultados ya guardados, indexados por subindicador para acceso O(1):

```python
resultados_actuales = {
    r.subindicador_id: r
    for r in EvaluacionResultado.objects.filter(evaluacion=evaluacion)
             .prefetch_related("evaluacionresultadodetalle_set")
}
detalles_por_sub = {
    r.subindicador_id: {d.mes: d for d in r.evaluacionresultadodetalle_set.all()}
    for r in resultados_actuales.values()
}
```

Como ya hicimos `prefetch_related("evaluacionresultadodetalle_set")`, leer
`r.evaluacionresultadodetalle_set.all()` **no** vuelve a la BD: usa lo precargado.

### 7.b — Guardar (POST): cálculo de ponderaciones

Primero, control de permisos por indicador:

```python
indicadores_editables = _indicadores_editables_ids(request.user)
if indicadores_editables is not None and not indicadores_editables:
    messages.error(request, "No tiene indicadores asignados. …")
    return redirect("contenido:evaluacion_diligenciar", pk=evaluacion.pk)
```

- **`_indicadores_editables_ids(user)`**:
  ```python
  def _indicadores_editables_ids(user):
      if user.is_superuser:
          return None                                   # marca especial: "todos"
      perfil = PerfilUsuario.objects.filter(usuario=user)\
                  .prefetch_related("indicadores").first()
      if perfil is None:
          return set()                                  # sin perfil → no edita nada
      return set(perfil.indicadores.values_list("id", flat=True))   # {ids editables}
  ```
  `.values_list("id", flat=True)` → `SELECT indicador_id …`, devuelve una lista plana de
  ids (no objetos), envuelta en `set()` para test de pertenencia O(1).

El guardado, dentro de una transacción, recorre el árbol y **salta** lo no editable:

```python
with transaction.atomic():
    for pilar in pilares:
        for indicador in pilar.indicador_set.all():            # ya precargado (no toca BD)
            if not _puede_editar(indicadores_editables, indicador.pk):
                continue                                       # ignora POST de lo no editable
            for sub in indicador.subindicador_set.all():
                observaciones = request.POST.get("observaciones_%s" % sub.pk, "").strip()
                peso_sub = Decimal(sub.peso)
                ...
```

- **`_puede_editar(editables, indicador_id)`** → `editables is None or indicador_id in editables`
  (superuser pasa siempre; los demás, solo sus indicadores).

**Caso `directo`** — un valor, una ponderación:

```python
puntaje_raw = request.POST.get("puntaje_%s" % sub.pk, "").strip()
if not puntaje_raw:
    continue                                       # sin dato → no se guarda
puntaje = _parse_decimal(puntaje_raw, "puntaje de «%s»" % sub, 0, 100)
ponderacion = puntaje * peso_sub / Decimal("100")  # fórmula base
EvaluacionResultado.objects.update_or_create(      # upsert por (evaluacion, subindicador)
    evaluacion=evaluacion, subindicador=sub,
    defaults={"puntaje": _q2(puntaje), "ponderacion": _q2(ponderacion),
              "observaciones": observaciones})
```

Con *Ejecución presupuestal* (peso 5.40) y puntaje **80**:
`ponderacion = 80 × 5.40 / 100 = 4.32`. → `_q2(...)` cuantiza a 2 decimales con
`ROUND_HALF_UP`.

**Caso `mensual`** — un valor por mes, y el resultado guarda el **promedio**:

```python
puntajes_mes = {}
for mes_num, _ in meses_aplicables:                # Enero, Febrero, Marzo
    raw = request.POST.get("puntaje_%s_%s" % (sub.pk, mes_num), "").strip()
    if raw:
        puntajes_mes[mes_num] = _parse_decimal(raw, "puntaje de «%s» (mes %s)" % (sub, mes_num), 0, 100)

if not puntajes_mes:                               # mensual sin ningún mes → borra el resultado
    EvaluacionResultado.objects.filter(evaluacion=evaluacion, subindicador=sub).delete()
    continue

ponderaciones_mes = {m: (p * peso_sub / Decimal("100")) for m, p in puntajes_mes.items()}
n = Decimal(len(puntajes_mes))
puntaje_avg     = sum(puntajes_mes.values()) / n          # promedio de puntajes
ponderacion_avg = sum(ponderaciones_mes.values()) / n     # promedio de ponderaciones

resultado, _ = EvaluacionResultado.objects.update_or_create(
    evaluacion=evaluacion, subindicador=sub,
    defaults={"puntaje": _q2(puntaje_avg), "ponderacion": _q2(ponderacion_avg),
              "observaciones": observaciones})

for mes_num, p in puntajes_mes.items():            # un detalle por mes
    EvaluacionResultadoDetalle.objects.update_or_create(
        resultado=resultado, mes=mes_num,
        defaults={"puntaje": _q2(p), "ponderacion": _q2(ponderaciones_mes[mes_num])})

EvaluacionResultadoDetalle.objects.filter(resultado=resultado)\
    .exclude(mes__in=puntajes_mes.keys()).delete()  # limpia meses que ya no llegan
```

Con *Avance mensual* (peso 3.60) y puntajes Ene=90, Feb=70, Mar=80:
- ponderaciones por mes: 90×3.6/100=**3.24**, 70×3.6/100=**2.52**, 80×3.6/100=**2.88**.
- `puntaje_avg = (90+70+80)/3 = 80.00`; `ponderacion_avg = (3.24+2.52+2.88)/3 = 2.88`.
- Se guarda el `EvaluacionResultado` (puntaje 80.00, ponderación 2.88) y **tres**
  `EvaluacionResultadoDetalle` (uno por mes). El `.exclude(mes__in=…).delete()` borra
  cualquier mes previo que ya no venga en el POST (p. ej. si se corrige y se deja un mes
  en blanco).

Todo corre dentro de `transaction.atomic()`: si cualquier `_parse_decimal` lanza
`ValidationError`, **se revierte el guardado completo** y se muestra el error — no quedan
resultados a medias.

> **`update_or_create` y el constraint:** funciona como "upsert" gracias a
> `UniqueConstraint(evaluacion, subindicador)` y `UniqueConstraint(resultado, mes)`:
> Django busca por esas claves y decide entre `UPDATE` e `INSERT`. Además, cada
> `EvaluacionResultado.save()` corre `full_clean()→clean()`, revalidando que el
> subindicador pertenezca al modelo de la evaluación.

### 7.c — Armar la matriz para la plantilla

El último bloque recorre `pilares` (ya precargado) y construye una lista de filas con
`rowspan` por pilar/indicador, marcando cada subindicador como `editable`, `es_mensual`,
y rellenando sus valores actuales (`puntaje_actual`, `meses_render`, etc.). No hace nuevas
queries: todo sale de lo precargado en 7.a. Los valores se pasan como `str(...)` para que
**no se localicen** (lleguen con punto a los `data-*`/inputs; ver Parte IV).

## Paso 8 — Reporte y dashboard (agregación)

Para nuestra Secretaría, el total del periodo es la **suma de ponderaciones**:
`4.32 (directo) + 2.88 (mensual) = 7.20`.

La función que lo calcula para todas las dependencias:

```python
def _puntajes_por_dependencia(modelo, periodo, pilar=None):
    qs = EvaluacionResultado.objects.filter(
        evaluacion__modelo_evaluacion=modelo,          # JOIN a Evaluacion + filtro
        evaluacion__periodo=periodo)
    if pilar is not None:
        qs = qs.filter(subindicador__indicador__pilar=pilar)   # JOIN de 3 saltos
    filas = (qs.values("evaluacion__dependencia", "evaluacion__dependencia__nombre")
               .annotate(total=Sum("ponderacion")))    # GROUP BY + SUM
    return {f["evaluacion__dependencia"]: (f["evaluacion__dependencia__nombre"],
                                           f["total"] or Decimal("0")) for f in filas}
```

Detrás de cámara:

- **`evaluacion__modelo_evaluacion=modelo`** — el doble guion bajo `__` **atraviesa la
  FK**: Django añade un `JOIN` a `contenido_evaluacion` y filtra por
  `evaluacion.modelo_evaluacion_id`. `subindicador__indicador__pilar=pilar` encadena
  **tres** JOINs (subindicador→indicador→pilar).
- **`.values("evaluacion__dependencia", "...__nombre")`** — proyecta solo esas columnas y
  cambia la consulta a "modo diccionario"; combinado con `annotate`, define el `GROUP BY`.
- **`.annotate(total=Sum("ponderacion"))`** — agrega `SUM(ponderacion)` **agrupando** por
  las columnas de `values()`. Resultado: una fila por dependencia con su total.

Otras funciones del reporte siguen el mismo patrón:
- **`_promedios_por_pilar`** suma por (pilar, dependencia) y luego **promedia entre
  dependencias** (`suma / n` en Python).
- **`_ranking`** ordena por total descendente (1 = mejor).
- **`_imag_max`** → `Pilar.objects.filter(modelo_evaluacion=modelo).aggregate(Sum("peso"))`.

> **Nota de negocio (pendiente):** hoy solo participa el **peso del Subindicador** en
> `ponderacion`. Los pesos de Indicador y Pilar existen pero **no** se aplican (ver
> comentario en `views.py`). Cambiarlo afectaría todos los agregados.

El **reporte público** (`/reporte/`) llama estas funciones con `solo_publicos=True` (solo
periodos `publico=True`); el **dashboard interno** (`/dashboard/`, con login) las llama con
`interno=True` y ve **todos** los periodos.

---

# Parte III — Glosario del ORM (qué hace cada operador detrás de cámara)

Idea base: **un `QuerySet` es perezoso**. Encadenar `.filter().values().annotate()…` **no
toca la base de datos**: solo construye un objeto que *describe* una consulta SQL. La BD se
golpea únicamente cuando el QuerySet se **evalúa**: al iterar, hacer `list()`, indexar,
`len()`, `bool()`, o llamar un método **terminal** (`.first()`, `.get()`, `.count()`,
`.exists()`, `.update()`, `.delete()`, `.aggregate()`, `.create()`).

### El doble guion bajo `__` — atravesar relaciones y aplicar lookups

Es el operador de acceso más importante. Tiene dos usos:

- **Atravesar relaciones (JOIN):** `evaluacion__periodo=p` → Django añade un `JOIN` a la
  tabla de `Evaluacion` y filtra por `periodo_id`. Se encadena:
  `subindicador__indicador__pilar__modelo_evaluacion=m` son cuatro saltos = varios JOINs.
- **Lookups (comparadores):** el segmento final puede ser un comparador en vez de un campo:
  `__in` (`WHERE … IN (…)`), `__gte`/`__lte` (`>=`/`<=`), `__icontains` (`ILIKE`),
  `__isnull`, etc. Ej.: `.exclude(mes__in=puntajes_mes.keys())` → `… WHERE NOT (mes IN (…))`.

### Métodos que devuelven otro QuerySet (perezosos, encadenables)

| Operador | Qué hace detrás de cámara |
|---|---|
| **`.filter(**kw)`** | Añade condiciones `WHERE … AND …`. No ejecuta nada todavía. |
| **`.exclude(**kw)`** | Igual pero negado: `WHERE NOT (…)`. |
| **`.order_by(...)`** | Define el `ORDER BY`. Acepta `F("orden").asc(nulls_last=True)` para controlar dónde van los `NULL`. |
| **`.values(...)`** | Proyecta columnas concretas y devuelve **diccionarios** en vez de objetos. Con `annotate`, fija el `GROUP BY`. |
| **`.values_list(..., flat=True)`** | Como `values` pero devuelve **tuplas**; con `flat=True` y un solo campo, una lista plana de valores. |
| **`.annotate(alias=Func(...))`** | Agrega una columna calculada. Con `Sum/Count/Avg` + `values()` previo → `GROUP BY` + función agregada. |
| **`.distinct()`** | Añade `SELECT DISTINCT` (elimina filas repetidas, p. ej. tras un JOIN N↔N). |
| **`.select_related(*fks)`** | Trae relaciones **ForeignKey/OneToOne** en el **mismo SELECT** vía `JOIN`. Evita una query extra por cada acceso a `obj.fk`. Para relaciones "hacia uno". |
| **`.prefetch_related(*rels)`** | Trae relaciones "hacia muchos" (reverse FK, M2M) en **consultas separadas** y las une en memoria. Evita el problema **N+1** al recorrer hijos. |

### `Prefetch(...)` — prefetch con queryset a medida

`Prefetch("indicador_set", queryset=Indicador.objects.order_by(...))` permite **personalizar**
la consulta de precarga (ordenarla, filtrarla, anidar más `prefetch_related`). En
diligenciar se anidan cuatro niveles para bajar todo el árbol ya ordenado en pocas queries.

### Métodos terminales (ejecutan SQL al instante)

| Operador | Qué hace detrás de cámara |
|---|---|
| **`list(qs)` / iterar / `[i]` / `len` / `bool`** | Fuerzan la evaluación: ejecutan el `SELECT` y materializan objetos. |
| **`.first()`** | Añade `LIMIT 1` (respeta el `order_by`) y devuelve el objeto o `None`. |
| **`.get(**kw)`** | `SELECT … LIMIT 2`; devuelve **uno** o lanza `DoesNotExist` / `MultipleObjectsReturned`. Úsalo cuando esperas exactamente uno. |
| **`.exists()`** | `SELECT 1 … LIMIT 1` → `True`/`False`. Más barato que traer filas solo para preguntar "¿hay?". |
| **`.count()`** | `SELECT COUNT(*)`. Más barato que `len(list(qs))`. |
| **`.aggregate(x=Sum(...))`** | `SELECT SUM(...)` **sin** `GROUP BY` → un diccionario con el total global. |
| **`.create(**kw)`** | `INSERT`; instancia, **llama `save()`** (por tanto `full_clean()` si el modelo lo overridea) y devuelve el objeto con `pk`. |
| **`.get_or_create(**kw, defaults=…)`** | `SELECT`; si existe lo devuelve, si no lo crea. Devuelve `(obj, creado_bool)`. |
| **`.update_or_create(**kw, defaults=…)`** | "Upsert": `SELECT` por las claves; si existe → `UPDATE` con `defaults`; si no → `INSERT`. Devuelve `(obj, creado_bool)`. |
| **`.update(**kw)`** | `UPDATE … WHERE …` directo sobre el conjunto. **No** instancia objetos, **no** llama `save()`/`clean()`, **no** toca `auto_now`. Rápido y masivo, pero salta validaciones. |
| **`.delete()`** | `DELETE … WHERE …` sobre el conjunto (respeta `on_delete=CASCADE` en cascada). |

> **Por qué importa `update()` vs `save()`:** `update()` va directo al SQL, por eso
> **salta** la inmutabilidad de `Evaluacion` (que vive en `clean()`/`save()`). Es la razón
> por la que el modelo congelado solo se puede forzar por vías que **no** pasen por
> `.save()` (`update`, `bulk_update`, SQL crudo, `loaddata`).

### Expresiones y utilidades

| Operador | Qué hace detrás de cámara |
|---|---|
| **`F("campo")`** | Referencia a una **columna** dentro del SQL (no su valor en Python). Permite `order_by(F("orden").asc(nulls_last=True))` o comparar/operar columnas en la BD. |
| **`Q(...)`** | Encapsula condiciones combinables con `&`, `|`, `~`. Aquí se usa en el `UniqueConstraint(condition=Q(activo=True))` → índice **parcial** (`WHERE activo`). |
| **`Sum / Count / Avg`** | Funciones de agregación SQL; con `values()+annotate` → por grupo; con `aggregate` → global. |

### Transacciones y validación

- **`transaction.atomic()`** — abre una transacción (`BEGIN`); si el bloque termina bien,
  `COMMIT`; si lanza una excepción, `ROLLBACK` total. Se usa en asignar modelo, crear
  evaluación y guardar el diligenciamiento, para que un fallo a mitad **no** deje datos
  inconsistentes.
- **`full_clean()`** — ejecuta validación de campos + `clean()` del modelo. Los modelos
  `Evaluacion` y `EvaluacionResultado` llaman `full_clean()` dentro de su `save()`, de modo
  que **toda** alta/edición vía `.save()`/`.create()`/`update_or_create()` revalida las
  reglas de negocio (inmutabilidad del modelo, coherencia subindicador↔modelo). `clean()`
  es donde viven esas reglas y lanza `ValidationError` (que las vistas atrapan y muestran).

---

# Parte IV — Localización de decimales (gotcha recurrente)

`LANGUAGE_CODE='es-col'` hace que Django **localice** los decimales con **coma** ("3,60")
en plantillas. La coma es correcta para texto visible, pero **rompe** cualquier número que
el navegador deba interpretar:

- **CSS inline** (`width:{{x}}%`) → "57,66%" es inválido.
- **`parseFloat` de JS** → `parseFloat("3,60") === 3` (trunca decimales).
- **`<input type="number" value="3,60">`** → HTML5 lo deja **vacío**.

**Reglas adoptadas:**
- En BD **siempre** se guarda con **punto** (columnas `numeric`); la coma es solo
  presentación. Se **mantiene** la coma en pantalla (se descartó forzar punto con
  `FORMAT_MODULE_PATH`).
- Todo número que vaya a CSS, a un `data-*` leído por JS o al `value` de un input usa
  `{% load l10n %}` + **`|unlocalize`**. Los valores que la vista pasa como `str(...)` ya
  llegan con punto (no se localizan).
- Captura: inputs `type="text" inputmode="decimal" class="js-decimal"` (no `type=number`).
- Servidor: `_parse_decimal` (Parte II, paso 4). Cliente:
  `partials/decimal_validacion.html` valida en vivo y expone `window.parseNum()`.

---

# Parte V — Permisos, roles y restricciones del proyecto

**Edición por indicador** (`PerfilUsuario`): un usuario solo edita los indicadores de su
perfil; el resto, solo lectura (superusuario edita todo). Se resuelve con
`_indicadores_editables_ids` + `_puede_editar` (Parte II, paso 7.b).

**Rol Evaluador** (Group `Evaluador` + `RolEvaluadorMiddleware`): *deny-by-default*
server-side. El middleware resuelve la ruta y, si el `url_name` no está en
`EVALUADOR_URLS_PERMITIDAS`, redirige al listado de evaluaciones. El context processor
`es_evaluador` oculta del sidebar los módulos sin acceso. Superusuarios exentos. El grupo
se crea/elimina por migración de datos `0016_grupo_evaluador`.

**Restricciones del proyecto:**
- La **base de datos está fija**: no se modifican modelos ni migraciones de esquema; el
  trabajo se hace en vistas, plantillas, admin, URLs, settings y estáticos.
- Con `DEBUG=False`, WhiteNoise exige `collectstatic`.
- `manage.py` se ejecuta desde la carpeta `mag/`.

---

# Parte VI — Despliegue (Railway) y errores frecuentes

El proyecto se despliega en **Railway**, que instala las dependencias con `uv` a partir de
`pyproject.toml` + `uv.lock` y luego ejecuta el comando de inicio.

## Comando de inicio

```bash
cd mag && uv run manage.py collectstatic --noinput && gunicorn mag.wsgi:application --bind 0.0.0.0:$PORT
```

Tres detalles que **deben** ir así:

- **`mag.wsgi:application`** (dos puntos, no punto). Gunicorn espera `módulo:variable`. El
  módulo es `mag/wsgi.py` y la variable es `application = get_wsgi_application()`. Si se
  escribe `mag.wsgi.application` (con punto), gunicorn intenta importar un módulo llamado
  `mag.wsgi.application` que no existe → el arranque falla.
- **`collectstatic --noinput`**. `collectstatic` copia todos los estáticos (CSS/JS de la
  app, del admin de Django y de Unfold) a `STATIC_ROOT`, desde donde WhiteNoise los sirve.
  Cuando esa carpeta ya tiene archivos, Django **pregunta por teclado** (`Are you sure you
  want to do this? Type 'yes'...`) y se queda esperando. En un deploy no hay terminal
  interactiva, así que se cuelga o aborta. `--noinput` asume "sí" y no pregunta — es la
  forma estándar para deploys/CI. En local no se notaba porque ahí sí se puede escribir `yes`.
- **`$PORT`**. Railway inyecta el puerto por variable de entorno; hay que enlazar a
  `0.0.0.0:$PORT`, no a un puerto fijo.

## Error resuelto: `pg_config executable not found` (build de psycopg2)

**Síntoma** (en el log de build, fase de instalación de dependencias — *antes* de arrancar
la app):

```
× Failed to build `psycopg2==2.9.12`
  Error: pg_config executable not found.
  ... please install the PyPI 'psycopg2-binary' package instead.
```

**Causa.** `pyproject.toml` pedía `psycopg2` (a secas), que se distribuye **como código
fuente C** y se compila al instalar. La compilación necesita la herramienta `pg_config` y
las cabeceras de desarrollo de PostgreSQL, que la imagen de build de Railway no trae → el
wheel no compila y se cae todo el deploy.

**Solución aplicada.** Se **eliminó `psycopg2` de `pyproject.toml`** (y se regeneró
`uv.lock` con `uv lock` → *Removed psycopg2 v2.9.12*). No hacía falta: el proyecto ya usa
**`psycopg[binary]`** (psycopg **v3**, el sucesor de psycopg2, con binario precompilado),
que Django 5.2 reconoce de forma nativa. `psycopg2` estaba duplicado y la app nunca lo
importaba (`grep psycopg2` en el código → 0 resultados).

> Alternativa equivalente si en algún momento se necesitara psycopg2: usar
> `psycopg2-binary` (trae el `.so` precompilado y no requiere `pg_config`). Pero teniendo
> psycopg v3 no aporta nada.

## Variables de entorno en Railway

`mag/.env` está en `.gitignore`, así que **sus valores no viajan al deploy**. Hay que
cargarlos como variables de entorno del servicio en Railway:

- `DATABASE_URL` — cadena de conexión a la BD (la lee `dj-database-url` en settings).
- `SECRET_KEY` — clave de Django para producción.
- `DEBUG=False`.
- `ALLOWED_HOSTS` — debe incluir el dominio público de Railway
  (`*.up.railway.app` correspondiente).

## Recomendación de seguridad (rotación de credenciales)

Si en algún momento la `SECRET_KEY` o la contraseña de la base de datos quedan expuestas
(por compartir el `.env`, pegarlas en un chat, subirlas por error al repo, etc.), hay que
**rotarlas**:

- **Contraseña de Postgres/Supabase:** cambiarla en el proveedor y actualizar
  `DATABASE_URL` en Railway.
- **`SECRET_KEY`:** generar una nueva y cargarla en Railway. Una clave con el prefijo
  `django-insecure-` es la autogenerada por `startproject` y **no** debe usarse en
  producción.
- Nunca versionar secretos: viven solo en `mag/.env` (local, ignorado) y en las variables
  de entorno del servicio (producción).
