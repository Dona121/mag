# Modelo de Alta Gerencia — Gobernación de Sucre

Documentación funcional y técnica del proyecto: lógica de construcción de la
página, flujo de registro de datos y bitácora de ajustes de interfaz.

> **Regla del proyecto:** la capa de datos (modelos y estructura de la base de
> datos) está establecida y **no se modifica**. El trabajo se concentra en
> vistas, templates, admin, URLs, settings y estáticos.

---

## 1. Visión general

Aplicación **Django 5.2** para parametrizar y diligenciar **evaluaciones de
desempeño** de las dependencias de la Gobernación de Sucre, sobre un modelo
jerárquico de indicadores ponderados.

- **Producción:** desplegada en **Railway** (PostgreSQL + Gunicorn + WhiteNoise).
- **Local:** SQLite por defecto (si no hay `DATABASE_URL`).
- Dos interfaces:
  1. **App propia** (`contenido`): dashboard, parametrización y diligenciamiento.
  2. **Admin Django** con **django-unfold** (`/admin/`): CRUD completo de catálogos.

### Stack

| Componente | Uso |
|---|---|
| Django 5.2 | Framework principal |
| django-unfold | Tema del panel admin |
| WhiteNoise | Servido de estáticos en producción |
| Gunicorn | Servidor WSGI |
| dj-database-url + psycopg | Conexión a PostgreSQL |
| python-dotenv | Variables de entorno (`.env`) |

---

## 2. Configuración (`mag/mag/settings.py`)

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `CSRF_TRUSTED_ORIGINS`
  se leen de variables de entorno.
- `DEBUG = os.getenv("DEBUG", "0")` → **por defecto `False`**.
- Estáticos:
  - `STATIC_URL = 'static/'`
  - `STATICFILES_DIRS = [BASE_DIR / "static"]` (origen: `mag/static/`)
  - `STATIC_ROOT = BASE_DIR / 'staticfiles'` (destino de `collectstatic`)
  - `STORAGES["staticfiles"]` → `whitenoise.storage.CompressedStaticFilesStorage`.
- Idioma `es-col`, zona horaria `America/Bogota`.

### ⚠️ Servido de estáticos (punto crítico)

Con `DEBUG=False`, `runserver` **no** sirve desde `STATICFILES_DIRS`; los
estáticos los entrega WhiteNoise **solo desde `STATIC_ROOT`**. Por eso, tras
agregar/cambiar imágenes hay que ejecutar:

```bash
python mag/manage.py collectstatic --noinput
```

y **reiniciar** el servidor (WhiteNoise indexa `STATIC_ROOT` al arrancar).

En **desarrollo** es más cómodo crear un `.env` con `DEBUG=1`: así Django sirve
los estáticos directamente desde `mag/static/` sin recolectar.

---

## 3. Construcción de la página (frontend)

Todo el frontend de la app propia es **HTML + CSS embebido** (sin framework CSS),
con la tipografía **Montserrat** y una paleta corporativa que **replica los
colores del escudo oficial**.

### Paleta corporativa (definida en `:root`)

| Variable | Color | Uso |
|---|---|---|
| `--verde-primario` | `#109d39` | Acentos, botones primarios |
| `--verde-superficie` | `#0e4d2a` | Sidebar, hero del login, encabezados de tabla |
| `--verde-superficie-2` | `#08321b` | Degradados profundos |
| `--azul` | `#0b72ab` | Botón secundario, badges |
| `--rojo` | `#d92a34` | Errores, botón peligro |
| `--naranja` | `#ffa700` | Acentos, indicadores |
| Grises | `#5a595d`–`#f5f6f7` | Texto y fondos |

### Layout base (`mag/templates/base/base.html`)

Plantilla maestra de la que heredan las vistas internas. Estructura:

- **Sidebar fijo** (`.sidebar`, fondo verde oscuro) con marca, navegación por
  secciones (General / Parametrización / Operación / Sistema / Cuenta) y pie con
  el usuario activo.
  - **Colapsable**: el botón `#toggle-sidebar` alterna `body.sidebar-colapsado`
    (escritorio, persistido en `localStorage`) o `body.sidebar-abierto-mobile`
    (móvil, con backdrop). Al colapsar solo queda el ícono/emblema.
- **Topbar-mini** (`.topbar-mini`): botón de colapso + breadcrumb + área derecha.
- **App-shell** (`.app-shell`): contenedor del contenido con `margin-left` igual
  al ancho del sidebar; incluye el bloque de **mensajes** (`messages`) y el
  `{% block contenido %}`.
- **Footer** corporativo.

Bloques disponibles para las plantillas hijas: `titulo`, `breadcrumb`,
`estilos_extra`, `contenido`, `scripts_extra`.

### Logos oficiales

Ubicados en `mag/static/logos/`. Se eligió como marca el escudo oficial a color,
solo emblema (sin texto), vertical y con fondo transparente:

```
2025_Blanco_logo-gob-Sucre_3_3.png   (1200×2000 px)
```

**Por qué este:** la paleta del sitio replica los colores del escudo, así que el
escudo a color es el match colorimétrico perfecto y luce como sello oficial sobre
el verde oscuro. Al no traer texto incrustado, funciona como marca compacta y
sobrevive al colapso del sidebar.

Se usa en:
- **Sidebar** (`.brand-mark` de `base.html`), junto al texto "Gobernación de Sucre".
- **Login** (brand del hero + marca de agua de fondo).

**Regla de tamaño:** el `<img>` se acota con **alto fijo en px** (`height: 40px`
en sidebar, `64px` en login) + `width: auto` + `max-width: 100%` +
`object-fit: contain`. **No usar `height: 100%`** dentro de contenedores
`grid/place-items: center`: el porcentaje no resuelve y la imagen cae a su tamaño
intrínseco (2000 px), desbordándose.

### Login a pantalla completa (`mag/templates/registration/login.html`)

Página independiente (no hereda de `base.html`). Diseño **split-screen** que
ocupa `100vh/100dvh`:

- **Panel izquierdo (hero):** degradado verde diagonal + acento radial, escudo
  como **marca de agua** (opacidad 7%), logo + título grande fluido
  (`clamp(34px–52px)`) con acento, y footer anclado abajo.
- **Panel derecho (formulario):** centrado, con el formulario limitado a
  `max-width: 400px`. Campos `username` / `password`, `csrf_token`, `next` y
  render de errores del `AuthenticationForm`.
- **Responsive (≤860px):** colapsa a una sola columna; el hero pasa a franja
  compacta (sin marca de agua ni footer) y el formulario debajo.

### Admin (`mag/contenido/admin.py` + `mag/static/css/admin.css`)

- Cada modelo se registra extendiendo `unfold.admin.ModelAdmin` con
  `list_display`, `list_filter`, `search_fields`, `fieldsets` e `inlines` acordes
  a la jerarquía.
- `admin.css` tiene overrides de contraste de íconos y botones, pero **no está
  cargado** actualmente (no figura en `UNFOLD["STYLES"]`). Para activarlo habría
  que añadir esa clave; varias reglas apuntan a `aside`, que la versión actual de
  Unfold ya no usa para el sidebar, así que habría que revisarlas.
- La navegación lateral del admin se define en `UNFOLD["SIDEBAR"]` (settings).

---

## 4. Modelo de datos (jerarquía)

> Solo de referencia — **no se modifica**.

### Parametrización (estructura del modelo de evaluación)

```
ModeloEvaluacion  (versionado; uno activo)
└── Pilar                 (peso)
    └── Indicador         (peso)   ← unidad de permisos de edición
        └── Subindicador  (peso, tipo_calculo: "directo" | "mensual")
            └── Criterio   (rango; guía descriptiva)
```

> Nota: `Criterio.nombre` es ahora `TextField` (texto largo/multilínea; antes
> `CharField(255)` — migración `0013_alter_criterio_nombre`). En el formulario se
> captura con `<textarea>` y en el árbol (`modelo_detalle`) se muestra respetando
> saltos de línea.

### Operación

- **Dependencia** y **DependenciaModelo**: asignan qué modelo evalúa cada
  dependencia. Constraint: **un solo modelo activo por dependencia**. La dependencia ya
  **no** guarda su categoría (ver `Categoria`).
- **Categoria**: clasificación de dependencias (p. ej. "Secretarías", "Institutos"). Es
  el **pivote del dashboard/reporte**. Se elige al crear cada evaluación y queda
  **congelada** en `Evaluacion.categoria` (snapshot, así se versiona).
- **Periodo**: si su nombre incluye meses ("Enero - Febrero - Marzo"), el
  diligenciamiento mensual mostrará solo esos meses. Campos de apoyo: **`vigencia`** (año,
  filtro del dashboard) y **`umbral`** (objetivo % del ranking; vacío = sin línea de meta).
- **Evaluacion**: única por `(periodo, dependencia)`. Fija el **modelo** y la **categoría**
  al crearse; el modelo **no se puede cambiar** después (validado en `clean()`). La
  categoría es **obligatoria** al crear (`blank=False`, validado por `full_clean()`).
- **EvaluacionResultado**: puntaje/ponderación consolidados por subindicador
  (único por `evaluacion + subindicador`).
- **EvaluacionResultadoDetalle**: desglose por mes (subindicadores "mensual").
- **PerfilUsuario**: relación 1‑a‑1 con `User` + M2M con los **indicadores** que
  ese usuario puede editar.

---

## 5. Flujo de registro de datos

### Permisos y roles

El control de acceso tiene **dos capas independientes** (se combinan). Los
**superusuarios** quedan exentos de ambas.

**1. Edición de puntajes por indicador (`PerfilUsuario`)**
- Cualquier usuario autenticado **ve** toda la jerarquía y los resultados.
- Solo **edita** los subindicadores cuyo `indicador` esté en su
  `PerfilUsuario.indicadores` (se asigna en el admin de User, inline con
  `filter_horizontal`).
- El POST **valida en el servidor** (salta los indicadores no asignados); no confía
  en el `readonly` del HTML. La matriz muestra los no asignados como **solo lectura**
  (etiqueta "Solo lectura") + un banner indicando cuántos subindicadores puede editar.

**2. Rol `Evaluador` (grupo de Django)**
- Creado por la migración `0016_grupo_evaluador`. Un Evaluador solo gestiona
  evaluaciones: en el panel ve **General** (Inicio + Dashboard), **Operación →
  Evaluaciones** y **Cuenta**; no ve Parametrización, Periodos ni el admin.
- Lógica en `contenido/roles.py` (`es_evaluador`, `EVALUADOR_URLS_PERMITIDAS`).
- `RolEvaluadorMiddleware` aplica **deny-by-default**: cualquier URL fuera de la lista
  permitida lo redirige al listado de evaluaciones (defensa server-side, no se salta
  por URL). El sidebar oculta los módulos vía el context processor `es_evaluador`.
- Para un evaluador del equipo: agréguelo al grupo **y** asígnele sus indicadores en
  el `PerfilUsuario` (necesita ambos para diligenciar).

### Validación de captura de decimales

Toda entrada decimal (peso, puntaje) se valida con el helper
`views._parse_decimal(raw, etiqueta, minimo, maximo)`:
- Acepta **un solo** separador decimal (coma **o** punto) y lo normaliza a punto.
- Rechaza con mensaje claro: separadores mezclados (`1.234,5`), repetidos (`3,6,0`),
  texto no numérico o **fuera de rango** (peso y puntaje: 0–100).
- En cliente, los inputs son `type="text" inputmode="decimal" class="js-decimal"` y el
  partial `partials/decimal_validacion.html` valida en vivo y bloquea el envío.
- **Nota de localización:** la página **muestra** decimales con coma (locale `es-col`),
  pero en BD siempre se guardan con **punto** (columnas `numeric`). Ver la sección de
  bitácora / el patrón `|unlocalize`.

### Paso a paso (operación típica)

1. **Crear el modelo de evaluación** y su jerarquía: Pilares → Indicadores →
   Subindicadores → Criterios, cada uno con su peso.
   (Vistas `*_create` en `views.py` o el admin.) Cada elemento se puede **editar**
   con su vista `*_editar` (modelo/pilar/indicador/subindicador/criterio), vía el
   botón **Editar** en el árbol de `modelo_detalle`; reutilizan el mismo template
   de formulario en modo edición. El **nombre** de pilar/indicador/subindicador
   es un FK a un catálogo (`PilarCategoria`/`IndicadorCategoria`/
   `SubindicadorCategoria`): el formulario lo elige con un `<select>`; las
   categorías se gestionan en el admin (Parametrización).
2. **Registrar dependencias** y asignarles el modelo **activo**
   (`DependenciaModelo`, vía `dependencia_modelo_asignar`).
3. **Definir periodos** (incluyendo los meses en el nombre si aplica).
4. **Asignar indicadores** a cada usuario evaluador (`PerfilUsuario` en el admin) y,
   si solo debe diligenciar, agregarlo al **grupo `Evaluador`** (ver Permisos y roles).
5. **Crear una Evaluacion** (`EvaluacionCreateView`): se elige periodo +
   dependencia + **categoría** (obligatoria, queda congelada en la evaluación) y el
   sistema toma automáticamente el **modelo activo** de esa dependencia. Valida que no
   exista ya `(periodo, dependencia)`.
6. **Diligenciar** (`evaluacion_diligenciar`): se renderiza la matriz
   Pilar → Indicador → Subindicador. Cada usuario edita solo lo permitido.

### Lógica de ponderación (`views.evaluacion_diligenciar`)

Todos los valores se **cuantizan a 2 decimales** en la captura (`ROUND_HALF_UP`, helper
`_q2`). Las columnas de la BD admiten más precisión —`peso`/`puntaje`/`ponderacion` son
`DecimalField(max_digits=10, decimal_places=5)`— que aprovecha la migración del histórico v1
(que guarda 5 decimales).

- **DIRECTO:**
  ```
  EvaluacionResultado.puntaje     = puntaje
  EvaluacionResultado.ponderacion = puntaje * peso_sub / 100
  ```

- **MENSUAL** (con N meses diligenciados):
  ```
  detalle.ponderacion  = puntaje_mes * peso_sub / 100      (por cada mes)
  parent.puntaje       = promedio(puntaje_mes)
  parent.ponderacion   = promedio(detalle.ponderacion)
  ```
  - Si no llega ningún mes, se **elimina** el resultado del subindicador.
  - Los meses que dejan de venir en el POST se **borran** de los detalles.

- Todo el guardado ocurre dentro de `transaction.atomic()`.
- El listado de evaluaciones (`EvaluacionListView`) anota
  `suma_ponderacion = Sum(evaluacionresultado__ponderacion)`.

### Meses aplicables

`meses_del_periodo(periodo)` normaliza el nombre del periodo (sin acentos,
minúsculas) y detecta los meses mencionados; si no encuentra ninguno, devuelve
los 12.

---

## 6. URLs principales (`mag/contenido/urls.py`, namespace `contenido`)

| Ruta | Vista | Propósito |
|---|---|---|
| `/` | `dashboard` | Inicio con métricas y últimas evaluaciones |
| `/dashboard/` | `dashboard_imag` | **Dashboard interno** (con login) — vista IMAG |
| `/dashboard/desempeno/` | `dashboard_desempeno` | Dashboard interno — vista Desempeño |
| `/dashboard/ranking/` | `dashboard_ranking` | Dashboard interno — vista Ranking |
| `/dashboard/variaciones/` | `dashboard_variaciones` | Dashboard interno — vista Variaciones |
| `/reporte/` | `reporte_publico` | **Reporte público (sin login)** — vista IMAG |
| `/reporte/desempeno/` | `reporte_desempeno` | Reporte público — vista Desempeño (por dependencia) |
| `/reporte/ranking/` | `reporte_ranking` | Reporte público — vista Ranking (pestañas por Categoría) |
| `/reporte/variaciones/` | `reporte_variaciones` | Reporte público — vista Variaciones |
| `/reportes/` | `reportes` | **Módulo de Reportes** (con login) — compositor de informes Excel/PDF por dependencia |
| `/reportes/generar/` | `reporte_generar` | Genera y **descarga** el informe (POST; `formato=excel\|pdf`) |
| `/auth/login/` | `LoginView` | Inicio de sesión (template rediseñado) |
| `/auth/logout/` | `LogoutView` | Cierre de sesión |
| `/auth/password-change/` | `PasswordChangeView` | Cambio de contraseña |
| `/categorias/<tipo>/` … | `categoria_list/create/editar` | Catálogos de nombres (tipo: pilar/indicador/subindicador) |
| `/modelos/` … | parametrización | CRUD de modelo/pilar/indicador/sub/criterio |
| `/evaluaciones/` | `EvaluacionListView` | Listado de evaluaciones (solo periodos activos) |
| `/evaluaciones/nueva/` | `EvaluacionCreateView` | Crear evaluación (acceso por botón del listado, no por menú) |
| `/evaluaciones/<pk>/diligenciar/` | `evaluacion_diligenciar` | Diligenciar matriz (bloqueada si el periodo está inactivo) |
| `/periodos/` | `PeriodoListView` | Gestión de periodos (estado, vigencia, umbral, visibilidad) |
| `/periodos/<pk>/activar/` | `periodo_activar` | Activar periodo — abre diligenciamiento (POST) |
| `/periodos/<pk>/desactivar/` | `periodo_desactivar` | Desactivar periodo (POST) |
| `/periodos/<pk>/umbral/` | `periodo_umbral_editar` | Formulario para crear/editar **vigencia (año)** y **umbral** (objetivo % del ranking) |
| `/periodos/<pk>/publicar/` | `periodo_publicar` | Marcar `publico=True` — visible en reporte público (POST) |
| `/periodos/<pk>/despublicar/` | `periodo_despublicar` | Marcar `publico=False` (POST) |
| `/admin/` | django-unfold | Panel administrativo |

> El **rol Evaluador** solo puede acceder a `/`, `/dashboard/*`, `/reportes/*`,
> `/evaluaciones/`, `/evaluaciones/<pk>/diligenciar/`, auth y el reporte público; el resto
> lo redirige al listado de evaluaciones (`RolEvaluadorMiddleware`).

---

## 7. Dashboard interno (`/dashboard/`)

Réplica en la app del tablero que antes se hacía en Excel → Power BI. Desde el
rediseño, el dashboard interno **reutiliza las mismas 4 vistas del reporte público**
(IMAG · Desempeño · Ranking · Variaciones, ver sección 8), pero **dentro del shell**
de la app (sidebar/topbar) y **sin la restricción de periodo público**: el equipo ve
**todos** los periodos, incluidos los datos previos aún no publicados.

**Cómo está montado:** las 4 vistas del reporte (`reporte_publico`,
`reporte_desempeno`, `reporte_ranking`, `reporte_variaciones`) aceptan `interno=False`.
Hay 4 wrappers `@login_required` — `dashboard_imag` / `dashboard_desempeno` /
`dashboard_ranking` / `dashboard_variaciones` — que las llaman con `interno=True`. El
flag decide `solo_publicos = not interno` y el "cascarón" (`_reporte_chrome`): plantilla
base (`base/dashboard_reporte.html` interno vs `reporte/base_reporte.html` público),
`url_reset` y `url_publico`. Las plantillas `reporte/reporte_*.html` hacen
`{% extends base_template %}`, así sirven para ambos contextos. La cabecera interna trae
un botón **"Ver reporte público"** que abre la vista pública equivalente.

> **Eliminado en el rediseño:** el viejo dashboard de 2 pestañas
> (`dashboard_analitico` / `dashboard_dependencia`) y sus endpoints AJAX
> (`dashboard_datos` / `dashboard_dependencia_datos`). Las vistas nuevas inyectan los
> datos inline con `{{ payload|json_script }}` (sin `fetch`).

Mapeo Excel/Power BI → modelos en `consulta/Mapeo_Dashboard_Django.md`; descripción
detallada de cada modelo y del flujo en `NOTAS_TECNICAS.md`.

### Base de los cálculos

Todo se deriva del **puntaje ponderado del subindicador**
(`EvaluacionResultado.ponderacion = puntaje × peso_sub / 100`, ya persistido por la
captura). Agregación: subindicador → (suma) dependencia → (promedio entre
dependencias) pilar → (suma) **IMAG**.

> **Pendiente de negocio:** hoy solo el peso del **subindicador** entra en
> `ponderacion`; `Indicador.peso` y `Pilar.peso` **no** se cascadean al IMAG (sí se
> usan como base de las barras — ver abajo).

### Las cuatro vistas

Son **las mismas de la sección 8** (reporte público), con idénticos cálculos y filtros;
la única diferencia es que el dashboard interno **no aplica el filtro `publico`** (ve
todos los periodos). En resumen:
- **IMAG:** KPIs del IMAG (último %, anterior, variación) + evolución por pilar + tabla.
- **Desempeño:** por dependencia, puntaje vs. objetivo + *small-multiples* por pilar.
- **Ranking:** ranking de dependencias por **Categoría** contra el objetivo (`Periodo.umbral`).
- **Variaciones:** Δ por dependencia vs. periodo anterior + mejor/peor.

### Filtros (server-side, vía GET)

- **categoria** (pivote; incluye **"Todas las categorías"** → IMAG general, consolida todo),
  **modelo** (**número de versión**; por defecto la versión activa más reciente, sin opción
  "todas" — pero una versión **agrupa todas sus estructuras**), **vigencia** (año, opcional),
  periodo, comparar (`0` = ninguno), pilar; Desempeño añade dependencia.
- La agregación filtra por `evaluacion__categoria` + `evaluacion__modelo_evaluacion__version`
  (helper `_eval_kwargs`; "Todas las categorías" = sentinela `TODAS_CATEGORIAS`, omite el
  filtro de categoría). Los **pilares se agregan por nombre** (`_promedios_por_pilar`) para no
  duplicarlos cuando la versión abarca varias estructuras; el filtro de **pilar** también es por
  nombre. Helpers `_resolver`, `_versiones_disponibles`/`_resolver_version`,
  `_periodos_con_datos(categoria, modelo, vigencia, solo_publicos)`, `_reporte_filtros`,
  `_resolver_dependencia_contexto`. Parámetros inválidos caen al valor por defecto.

### Gráficos (Chart.js)

- **Chart.js v4 vendorizado** en `mag/static/vendor/chart.umd.min.js` (no es paquete
  pip; tras agregarlo correr `collectstatic`).
- Los datos van **inline** con `{{ payload|json_script }}` (JSON, separador **punto**) y
  los `<canvas>` se dibujan con `window.reporteCharts()` al entrar en viewport
  (IntersectionObserver). Ya **no hay endpoints AJAX**.
- El nav "Dashboard" del sidebar se marca activo con `'dashboard_' in url_name`.

---

## 8. Reporte público (`/reporte/`) — réplica del Power BI

Página **pública (sin login)** pensada para que la ciudadanía y los órganos de
control vean los resultados, tal como antes los consumían desde el Power BI.
**No** lleva `@login_required`; el control de acceso en el proyecto es por vista
(no hay middleware global), así que estas vistas simplemente omiten el decorador.

Es **independiente** de la app interna: las plantillas viven en
`mag/templates/reporte/` y **no** extienden `base/base.html` (no usan el sidebar
del admin). Hay una plantilla base propia, `reporte/base_reporte.html`, que aporta
masthead, pestañas, pie y el JS compartido (gauge + IntersectionObserver para las
animaciones de entrada); cada vista la extiende.

Los **filtros** (categoría, versión, vigencia, periodo, comparar, pilar) van en un
**sidebar izquierdo** (`.r-layout` → `.r-side` con el `.d-toolbar` como tarjeta vertical),
con el contenido a la derecha; en móvil (<900px) el sidebar se apila arriba. Este layout
vive **solo** en `base_reporte.html`: el **dashboard interno** usa otra base
(`base/dashboard_reporte.html`, dentro del shell de la app) con su propio CSS, así que
**no** se ve afectado aunque comparta las plantillas de vista.

### Identidad visual

Consistente con la página y con el **Manual de Identidad** (`manual_identidad/…pdf`):
tipografía **Montserrat** y paleta institucional (verde `#109d39`, verde profundo
`#0e4d2a`, azul `#0b72ab`, rojo `#d92a34`, naranja `#ffa700`, ámbar `#d88c16`,
grises). El semáforo del modelo (verde/ámbar/rojo) codifica los datos.

### Las cuatro vistas (pestañas)

Replican las láminas del Power BI. El **"Indicador" del Power BI = `Pilar`** del
modelo; las **"Categorías" = `Categoria`** (modelo real que clasifica dependencias,
**congelado en `Evaluacion.categoria`**), con la opción **"Todas las categorías"** (IMAG
general). El pivote del tablero es la categoría; la **versión del modelo** (por **número** de
versión: agrupa todas sus estructuras) y la **vigencia (año)** son filtros adicionales. Como
una versión puede tener varias estructuras, los **pilares se consolidan por nombre** (no se
repiten).

1. **IMAG** (`reporte_publico`, `/reporte/`) — KPIs de IMAG (último %, anterior %,
   variación en puntos), evolución del **% de cumplimiento por pilar**
   (`promedio/peso·100`) y tabla *Pilar | Anterior | Último* con sombreado verde.
2. **Desempeño** (`reporte_desempeno`, `/reporte/desempeno/`) — por dependencia:
   KPIs del puntaje del periodo contra **objetivo 60 %** (con la brecha) y
   **small-multiples**: una mini-gráfica de evolución por cada pilar.
3. **Ranking** (`reporte_ranking`, `/reporte/ranking/`) — fila de pestañas de
   **Categoría**; barras por dependencia (mejor en verde + **línea de objetivo =
   `Periodo.umbral`**, antes constante 40 %) y tabla *Dependencia | Puntaje* con
   sombreado azul, ordenada. Si el periodo no tiene `umbral`, no se dibuja la línea.
4. **Variaciones** (`reporte_variaciones`, `/reporte/variaciones/`) — KPIs
   (mejor/peor variación y mejor/peor desempeño), tabla *Dependencia | Anterior |
   Último | Variación* con sombreado verde/rojo y barras horizontales de variación.

### Cálculos y filtros

- Reutiliza los **mismos helpers** del dashboard interno (`_datos_dashboard`,
  `_serie_temporal`, `_datos_dependencia`, `_serie_dependencia`, `_imag_max(dash)`,
  `_estado_semaforo`, `_shade` para el sombreado de tablas). Todo en puntos/%.
- Filtros **server-side (GET)**, auto-submit: **categoria** (con "Todas las categorías"),
  **modelo** (= número de versión), **vigencia (año)**, periodo, comparar, pilar (y
  dependencia en Desempeño). Helper compartido `_reporte_filtros` / `_ctx_filtros`.
  Parámetros inválidos caen al valor por defecto.
- **Gráficos con Chart.js** vendorizado; los datos se inyectan inline con
  `{{ payload|json_script }}` (no hay endpoint AJAX aparte). Anchos/sombras usan
  `|unlocalize` (locale `es-col` mete coma decimal).
- El **objetivo del Ranking** ya viene de la BD (`Periodo.umbral`, variable por periodo);
  el de **Desempeño sigue constante en 60 %** (parametrizar si debe venir de la BD).

### Visibilidad pública (`Periodo.publico`)

El reporte público **solo muestra periodos con `Periodo.publico=True`**. El equipo
puede tardar días/semanas en terminar una evaluación (datos previos); esos datos no
deben verse afuera hasta que el admin cambie `publico` de `False` a `True`. El
**dashboard interno ve todos los periodos** (los resultados son del equipo) — no se
ve afectado.

Implementación: un flag `solo_publicos` recorre la cadena de helpers
(`_periodos_con_datos`, `_serie_temporal`, `_serie_dependencia`,
`_resolver_dependencia_contexto`). Las vistas públicas lo pasan en `True`
(`_reporte_filtros` lo fija); las internas usan el valor por defecto `False`. Como
los selectores de periodo/dependencia y las series solo enumeran periodos públicos,
no es posible "colar" un periodo no publicado por la URL. Si no hay ningún periodo
público, el reporte muestra el aviso correspondiente.

> **Estado de datos:** con un solo periodo cargado, la variación muestra "sin
> comparación"; al diligenciar un segundo periodo se llena automáticamente.

> **Pendientes / pistas:** las pestañas "Información" y "Ayúdanos a mejorar" del
> Power BI no se replicaron. La categorización por **orden de la dependencia** aún
> no está en el modelo; por ahora "Categoría" se trata como `ModeloEvaluacion`.

---

## 9. Bitácora de ajustes de interfaz

1. **Logos oficiales incorporados.** Reemplazo del placeholder "GS" por el escudo
   oficial (`2025_Blanco_logo-gob-Sucre_3_3.png`) en sidebar (`base.html`) y login.
   Selección por match colorimétrico con la paleta del sitio.
2. **Fix de carga de la imagen.** Causa: estáticos no recolectados con
   `DEBUG=False`. Solución: `collectstatic` (+ reiniciar y `Ctrl+F5`).
3. **Fix de desbordamiento del logo.** El `<img>` se acotó con alto fijo en px
   (sin `height: 100%`) para evitar el render a tamaño intrínseco.
4. **Login a pantalla completa.** Rediseño split-screen `100vh`, hero con
   degradado y marca de agua, formulario centrado con `max-width`, responsive a
   una columna en ≤860px. Sin cambios en la lógica del formulario.
5. **Sidebar del admin que se superponía al contenido — era bug de versión.**
   Síntoma: la barra lateral se montaba sobre títulos/formularios/changelist;
   empeoraba a zoom 100% y se "arreglaba" alejando el zoom. Tras descartar
   config y CSS (el `styles.css` compilado se veía correcto), la causa resultó
   ser un **bug del layout en versiones viejas de Unfold** (estaba en 0.90.0;
   `requirements.txt` fijaba 0.81.0). Solución: **actualizar django-unfold a
   0.98.0**, alinear `requirements.txt` con `pyproject.toml` (ambos 0.98.0) para
   que el deploy no reinstale la versión con bug, y `collectstatic --clear`.
6. **Filtro de modelo por número de versión.** El selector "Versión del modelo" pasó de
   listar cada `ModeloEvaluacion` a listar **números de versión** (1, 2, …): al elegir una
   versión entran **todas sus estructuras** (varios `ModeloEvaluacion`). `_eval_kwargs` filtra
   por `evaluacion__modelo_evaluacion__version`.
7. **IMAG: pilares repetidos — corregido.** Al abarcar una versión varias estructuras, el
   mismo pilar salía repetido. `_promedios_por_pilar` ahora agrega por **nombre** de pilar
   (`PilarCategoria`); el filtro de pilar y el dropdown "Indicador" también deduplican por nombre.
8. **Filtro "Todas las categorías".** Nueva opción (sentinela `TODAS_CATEGORIAS`) en el selector
   de IMAG/Desempeño/Variaciones y como pestaña en Ranking: consolida todas las categorías para
   ver el **IMAG general** y sus indicadores.
9. **Periodos: columnas Vigencia y Umbral + formulario.** La tabla de `/periodos/` muestra la
   vigencia (año) y el umbral, con un botón Definir/Editar que abre `periodo_umbral_editar` para
   crear/editar ambos (umbral vacío = sin meta del Ranking). Ver sección 10.
10. **Total en vivo de la evaluación: sin redondear por fila.** En `evaluacion_diligenciar.html` el
    JS guardaba la ponderación de cada fila redondeada a 2 decimales y sumaba eso, dando ~0.02 menos
    que el dashboard. Ahora guarda el valor exacto en `data-exact` por fila y solo redondea el
    **total** (coincide con el dashboard, que suma a 5 decimales y redondea al final).
11. **Decimales flexibles en pantalla (filtro `decimales`).** Nuevo templatetag
    `contenido/templatetags/formato.py` → `{{ valor|decimales }}`: muestra **mínimo 2 y hasta 5**
    decimales, recortando ceros sobrantes (12,5→"12,50"; 33,33333→"33,33333"). Localiza con coma.
    Se aplica en la pantalla de evaluación (pesos e inputs de puntaje), donde antes salían todos
    los decimales del `DecimalField`.
12. **Guardado de la evaluación a 5 decimales (`_q5`).** El POST de `evaluacion_diligenciar`
    guardaba puntaje/ponderación con `_q2` (2 decimales), recortando lo capturado (75,53785→75,54).
    Ahora usa **`_q5`** (5 decimales, el tope real del `DecimalField`), consistente con el
    importador de migración. El `_q2` se conserva solo para el redondeo de **presentación** en
    dashboard/reporte.
13. **Periodo actual/anterior en orden cronológico.** El dashboard/reporte tomaba como "anterior"
    literalmente el periodo elegido en *Comparar con*, sin verificar cuál es más reciente
    (Jul-Ago vs Nov-Dic ponía Nov-Dic como anterior). El helper **`_resolver_actual_anterior`**
    (compartido por ambos resolvedores) reordena: el más reciente de los dos siempre es el
    "actual/último" y el más antiguo el "anterior"; los selectores de la UI se autocorrigen.
14. **Módulo de Reportes (Excel/PDF).** Nuevo `/reportes/` — ver **sección 15**.
15. **Reporte público: filtros en sidebar izquierdo.** El panel sticky de filtros del top pasó a
    un **sidebar a la izquierda** (solo en `base_reporte.html`; el dashboard interno no cambia).

---

## 10. Apertura/cierre de periodos (`Periodo.activo`)

La disponibilidad de las evaluaciones se controla a **nivel de periodo** con el
booleano `Periodo.activo` (default `True`). Activar/desactivar un periodo abre o
cierra **todas sus evaluaciones** de una vez, sin borrar información.

- **Listados operativos** (`EvaluacionListView` y `ultimas_evaluaciones` +
  total del dashboard) muestran **solo evaluaciones de periodos activos**
  (`filter(periodo__activo=True)`).
- **Diligenciamiento**: `evaluacion_diligenciar` **bloquea** (redirige al
  listado con aviso) si el periodo está inactivo.
- **Creación**: `EvaluacionCreateView` solo ofrece periodos activos en el
  desplegable.
- **Gestión (frontend)**: `PeriodoListView` (`/periodos/`, menú Operación)
  lista los periodos con badge Activo/Inactivo, conteo de evaluaciones y botones
  **Activar/Desactivar** (POST). La tabla muestra además la **Vigencia** (año) y el
  **Umbral**, con un botón **Definir/Editar** que abre un formulario
  (`periodo_umbral_editar`, `/periodos/<pk>/umbral/`) para crear/editar ambos: la
  vigencia (año, valida 1900–2200) y el umbral (objetivo % del ranking, 0–99.99; **vacío =
  sin meta**, no se dibuja la línea en el Ranking). Usa `_parse_decimal` (coma o punto) y
  guarda con `update_fields`. También se gestiona desde `PeriodoAdmin` (filtro, edición en
  línea y acciones masivas).
- Desactivar **no elimina** evaluaciones ni resultados; se mantiene el histórico
  completo y se vuelve a ver al reactivar.
- **Convención**: toda consulta/funcionalidad nueva sobre evaluaciones asume
  **solo periodos activos** por defecto, salvo que se pida incluir inactivos.

> Nota: el antiguo campo `Evaluacion.activa` se retiró (migración
> `0010_remove_evaluacion_activa`); el control de disponibilidad es por periodo.

---

## 11. Comandos útiles

```bash
# Verificar configuración
python mag/manage.py check

# Recolectar estáticos (obligatorio tras cambiar imágenes con DEBUG=False)
python mag/manage.py collectstatic --noinput

# Migraciones
python mag/manage.py migrate

# Servidor de desarrollo
python mag/manage.py runserver

# Importar el histórico v1 (Excel) — sin --commit solo simula
#   (Windows: anteponer  $env:PYTHONUTF8="1"  para los acentos en consola)
python mag/manage.py importar_v1 migracion/archivo.xlsx
python mag/manage.py importar_v1 migracion/archivo.xlsx --commit

# Agregar un periodo nuevo a los modelos v1 ya existentes (p. ej. trimestre 2026)
python mag/manage.py importar_periodo_v1 migracion/archivo.xlsx           # simula
python mag/manage.py importar_periodo_v1 migracion/archivo.xlsx --commit  # escribe
```

> **Migración del histórico v1:** una hoja por dependencia (+ hoja `categorias` que mapea
> dependencia → categoría); las dependencias se agrupan por **estructura** y se crea un
> `ModeloEvaluacion` (version=1) por estructura. Escala ×100, 5 decimales, normaliza nombres
> y `tipo_calculo`. Detalle en `NOTAS_TECNICAS.md`.

---

## 12. Inconsistencias del Excel v1 (2025) y su corrección

Durante la preparación del cargue del histórico v1 se detectaron varias inconsistencias en el
Excel de origen (`estructura_modelo_version_1_2025.xlsx`). Se documentan aquí para trazabilidad.
Se dividen en: (A) las que **se corrigieron en el Excel** (eran datos contradictorios que el
importador no debe "adivinar") y (B) las que el **importador normaliza automáticamente** (ruido
de digitación que no cambia el dato).

> **Verificación final:** se comparó el Excel contra la base de datos — **740
> `EvaluacionResultado` y 1.133 detalles mensuales**; los **puntajes** coinciden exactamente y no
> hay filas sobrantes. Las **ponderaciones** cumplen `ponderación = puntaje × peso` (ver
> resolución abajo); el escaneo global deja solo 3 diferencias de **0.01** por redondeo del peso
> periódico `3.33333` (1/30), sin impacto real.

> **Resolución de los ponderados (decisión 2026-06):** el importador **recalcula** la
> ponderación = `puntaje × peso / 100` y **no usa la columna de ponderado del Excel** (que en
> varias celdas estaba mal calculada: un mes con un peso distinto al del subindicador). Así el
> dato queda coherente con el peso del catálogo y con lo que recalcula la pantalla de
> evaluación. Esto corrige automáticamente los casos del grupo **A‑5** (p. ej. Bellas Artes pasó
> de `20.00` a `3.00`). La reimportación usa `update_or_create`, así que sobrescribe los valores
> ya cargados.

### A. Corregidas en el Excel (por el equipo)

1. **Pesos en cascada incoherentes dentro de una misma estructura.** Dependencias que comparten
   estructura deben compartir pesos (el catálogo del modelo es único), y además debe cumplirse
   que Σ indicadores = peso del pilar y Σ subindicadores = peso del indicador. Se corrigieron:
   - **Interior** (estructura de Salud): indicadores `PIIP`, `Estratégicos`, `Aliados (Invisibles)`
     estaban en `0.0667` y debían ser `0.05` (como Salud).
   - **Oficina TIC** (estructura de Bellas Artes): indicador `PIIP` estaba en `0.20` y debía ser `0.05`.
   - **Tránsito** (estructura de Unidad del Riesgo): indicador `Portafolio` (`0.25`→`0.20`) y
     subindicadores `Tiempo` / `Información Completa` (`0.125`→`0.10`).
2. **`criterio_rango` con el valor del peso en vez del descriptor.** En **Tránsito**, los
   subindicadores `% de proyectos en ejecución suspendidos` y `% de Proyectos terminados sin liquidar`
   tenían en la columna de rango el número del peso (`0.2`, `0.05`) en lugar de `0 - 100%`.
3. **Typo en `tipo_calculo`.** En **Aguas de Sucre** (3 filas) decía `directo a paritr de septiembre`
   ("paritr" → "partir").
4. **Texto de `tipo_calculo` no estandarizado** entre dependencias de una misma estructura
   (p. ej. `directo` vs `directo a partir de julio/septiembre`), que se unificó.
5. **Ponderados que no correspondían a `puntaje × peso`.** En varias celdas el ponderado del
   Excel se calculó con un peso equivocado (o quedó en 0/inflado): **Bellas Artes** % suspendidos
   Nov-Dic (`20.00` → `3.00`), **Salud** % suspendidos Jul-Ago (`0.00` → `3.00`), **Fondo Mixto**
   Eficacia/Eficiencia Jul-Ago (`16.00`/`4.00` → `15.50`/`3.50`) e **Indersucre** % sin liquidar
   Sep-Oct (octubre usó 3 % en vez de 2 %). Se corrigieron en el Excel y, además, el importador
   **recalcula** la ponderación (ver recuadro arriba), así que estos casos quedan resueltos por
   definición; el escaneo final solo deja diferencias de redondeo de 0.01 por el peso 1/30.

> **El Excel fuente también quedó limpio.** Además de normalizarse en el importador, el `.xlsx`
> de origen se corrigió (typos y espacios al inicio/fin de los textos; nombres canónicos), dejando
> un **único archivo** `migracion/estructura_modelo_version_1_2025.xlsx`. Las fórmulas (pesos y
> ponderados calculados) se conservan; tras editar con openpyxl hay que **abrir y guardar en
> Excel** una vez para repoblar los valores cacheados de las fórmulas.

### B. Normalizadas automáticamente por el importador

6. **Espacios sobrantes** al inicio/fin de nombres de pilar, indicador, subindicador y criterio
   (p. ej. `"Ciclos de Gerencia "`, `" Cumplimiento de las metas"`, doble espacio final). → `strip()`
   y colapso de espacios.
7. **Espacios duros `\xa0`** (non-breaking space) dentro de criterios/observaciones. → reemplazados
   por espacio normal.
8. **Typos en nombres de subindicador:** `"...apalanca el cumplimeinto..."` → `cumplimiento`;
   `"Cumplimento Acumulado..."` → `Cumplimiento`.
9. **Variantes de nombre del mismo concepto** (nombres canónicos confirmados por el equipo):
   `Mecanismos de Financiación` → **`Otros Mecanismos de Financiación`**; `Ciclo de Proyectos` →
   **`Ciclos de Gerencia`**.
10. **Dependencia duplicada por nombre:** la hoja **`Oficina TI`** corresponde a **`Oficina TIC`**
   (misma dependencia); se importa con el nombre `Oficina TIC`.
11. **`tipo_calculo` con descriptor temporal** (`directo a partir de julio/septiembre`) → se
    normaliza a `directo` (el modelo solo admite `mensual`/`directo`; el matiz de "a partir de…"
    ya queda reflejado en que esos meses traen un solo valor por bimestre).
12. **Columna sobrante:** la hoja **Educación** traía una columna 31 vacía (sin efecto; se ignora).

---

## 13. Guía para revisar y migrar un nuevo Excel

Checklist a seguir **cada vez** que llegue un archivo Excel para migrar (p. ej. una nueva
vigencia o versión). Está ordenado en el orden recomendado de trabajo. Todo se valida con
scripts puntuales **antes** de escribir en la BD; el importador corre primero en
**simulación** (sin `--commit`).

### 13.1. Inspección estructural (antes que nada)

- [ ] **Hojas del libro.** Confirmar que hay una hoja **`categorias`** (mapa Dependencia →
  Categoría) **+ una hoja por dependencia**. El **título de cada hoja = nombre de la dependencia**.
- [ ] **Encabezados (fila 1).** Verificar que las columnas 1–30 siguen el layout esperado
  (`pilar_nombre, pilar_peso, … , tipo_calculo`). Revisar **columnas sobrantes** (p. ej. una
  col 31 vacía) y columnas faltantes.
- [ ] **Periodos (columnas pivote).** Confirmar qué periodos trae (Enero–Junio solo junio; luego
  bimestres; en 2026 trimestres) y que las columnas de puntaje/ponderado/observación de cada
  periodo están donde se esperan.
- [ ] **Hoja `categorias` completa.** Que toda dependencia con hoja esté mapeada, y revisar
  **filas de más** (dependencias en `categorias` que no tienen hoja, o duplicados por nombre).

### 13.2. Agrupación por estructura → modelos

- [ ] **Agrupar dependencias por estructura** (árbol pilar→indicador→subindicador). Se crea **un
  `ModeloEvaluacion` por estructura** distinta; el catálogo (pesos/criterios) se toma de la
  **primera dependencia** del grupo (representativa).
- [ ] **Variantes de nombre que inflan estructuras.** Detectar nombres que son el mismo concepto
  escritos distinto (en v1: `Mecanismos de Financiación` vs `Otros Mecanismos de Financiación`;
  `Ciclo de Proyectos` vs `Ciclos de Gerencia`). Normalizarlos reduce estructuras duplicadas.
- [ ] **Divergencias dentro del grupo.** Para cada estructura, comparar pesos, criterios y
  `tipo_calculo` entre las dependencias del grupo: deben ser idénticos (el catálogo del modelo es
  único). Reportar diferencias.

### 13.3. Validaciones de datos (correr y reportar)

- [ ] **Cascada de pesos** (por hoja): Σ pilares = 100 %, Σ indicadores = peso del pilar,
  Σ subindicadores = peso del indicador.
- [ ] **Ponderado = puntaje × peso** (por celda, mensual y de periodo): detectar celdas donde el
  ponderado del Excel no corresponde (un mes con peso distinto, valor inflado o en 0). *(El
  importador igual recalcula la ponderación; ver §12, pero conviene reportarlas.)*
- [ ] **`tipo_calculo`:** listar valores distintos; deben mapear a `mensual`/`directo`. Detectar
  typos (p. ej. `paritr`) y textos no estandarizados entre dependencias de una estructura.
- [ ] **`criterio_rango`:** revisar que no traiga el **peso** en lugar del descriptor
  (`0 - 100%`, etc.).

### 13.4. Limpieza de texto

- [ ] **Espacios** al inicio/fin, `\xa0` (non-breaking space) y dobles espacios → recortar/normalizar.
- [ ] **Typos** en nombres (en v1: `cumplimeinto`→`cumplimiento`, `Cumplimento`→`Cumplimiento`).
- El importador normaliza esto automáticamente; aun así conviene **dejar el Excel fuente limpio**
  (ver cuidados de openpyxl en 13.7).

### 13.5. Escala y precisión

- [ ] **Fracción → porcentaje:** el Excel viene en **0–1**; se guarda **×100** (peso `0.125`→`12.50`,
  puntaje `0.5`→`50`). Confirmar contra la convención de la BD.
- [ ] **Decimales:** los campos son `DecimalField(max_digits=10, decimal_places=5)`. Con pesos
  periódicos (p. ej. `1/30 = 6.66667`) es **normal** que queden diferencias de redondeo de `0.01`
  en alguna ponderación; no son errores.

### 13.6. Preguntas al usuario (decisiones que NO se deben adivinar)

1. **¿Cómo modelar las estructuras?** Uno por estructura distinta (recomendado), uno por categoría,
   o uno por dependencia.
2. **¿Unificar variantes de nombre?** ¿Cuál es el nombre canónico de cada par?
3. **Dependencias dudosas:** duplicadas por nombre o presentes en `categorias` sin hoja (p. ej.
   ¿`Oficina TI` = `Oficina TIC`?).
4. **Ponderados inconsistentes:** ¿recalcular en el importador (`puntaje × peso`), corregir en el
   Excel, o dejar el valor literal del Excel? *(En v1 se decidió **recalcular**.)*
5. **Subindicadores `directo`/trimestral con un solo valor por bimestre:** ¿guardar un detalle del
   mes presente, o solo el resultado del periodo?
6. **Visibilidad de los periodos:** ¿`publico=True/False`? ¿`activo`? (histórico suele ir
   `activo=False`, `publico=True`).
7. **Nombres de los `ModeloEvaluacion`** que se crearán.
8. **Limpieza de texto:** ¿solo recortar/normalizar, o también corregir typos?

### 13.7. Cuidados con el archivo Excel (openpyxl)

- [ ] **Respaldo** del `.xlsx` antes de editarlo por programa.
- [ ] **Solo editar celdas de texto** (nombres, criterios); **nunca** tocar fórmulas.
- [ ] openpyxl al guardar **conserva las fórmulas pero borra sus valores cacheados** → leer luego
  con `data_only=True` devuelve `None` hasta **abrir y guardar el archivo en Excel** (recalcula).
  Hacerlo antes de cualquier reproceso programático.
- [ ] Dejar **un solo archivo** (sin copias `_original`/`_v2`) para evitar confusión.

### 13.8. Cómo correr el importador

```bash
$env:PYTHONUTF8="1"                                   # Windows: acentos en consola
python mag/manage.py importar_v1 migracion/archivo.xlsx           # simula (no escribe)
python mag/manage.py importar_v1 migracion/archivo.xlsx --commit  # escribe (update_or_create)
```

- El `--dry-run` (sin `--commit`) **reporta** qué crearía (modelos, catálogo, evaluaciones,
  totales) y las divergencias; revisarlo antes de escribir.
- Usa `update_or_create`, así que reimportar **sobrescribe** puntajes/ponderaciones ya cargados.

### 13.9. Verificación post-cargue (obligatoria)

- [ ] **Cruce Excel ↔ BD:** comparar puntajes, ponderaciones y detalles mensuales de cada
  `EvaluacionResultado` contra el Excel; **0 diferencias** y **0 filas sobrantes** en la BD.
- [ ] **`ponderado = puntaje × peso`** en toda la BD: 0 desajustes (salvo el redondeo de 0.01 ya
  mencionado).
- [ ] **Conteos** (modelos, dependencias, periodos, resultados, detalles) coinciden con lo
  reportado por el `--dry-run`.
- [ ] **Coherencia dashboard ↔ pantalla de evaluación** para alguna dependencia/periodo de muestra.

---

## 14. Migración del periodo v1 2026 (primer trimestre)

Segunda migración del histórico (vigencia 2026, **Enero - Febrero - Marzo**). A diferencia de
2025, aquí **no se crean modelos**: la versión 1 ya existe, así que cada dependencia se vincula a
su `ModeloEvaluacion` v1 actual y solo se le **agrega el periodo nuevo**. Fuente:
`migracion/estructura_modelo_version_1_2026.xlsx`.

### 14.1. Comando `importar_periodo_v1`

```bash
$env:PYTHONUTF8="1"
python mag/manage.py importar_periodo_v1 migracion/estructura_modelo_version_1_2026.xlsx          # simula
python mag/manage.py importar_periodo_v1 migracion/estructura_modelo_version_1_2026.xlsx --commit # escribe
```

- **Detecta el periodo desde los encabezados** (`_detectar_periodos`): el 2026 trae un layout
  distinto al de 2025 (un trimestre: enero/febrero/marzo + `ponderacion_…` + observación, cols
  9–16). El nombre del periodo se arma con sus meses → **"Enero - Febrero - Marzo"**. La
  **vigencia** se toma del nombre del archivo (o con `--vigencia`).
- **Reusa el modelo v1** de cada dependencia (vía `DependenciaModelo`); no agrupa ni crea modelos.
- Si una hoja trae un **subindicador nuevo** (no estaba en v1), lo crea bajo su indicador en ese
  modelo (ver Estratégicos abajo).
- Igual que `importar_v1`: escala ×100, 5 decimales, **ponderación recalculada** (`puntaje × peso`)
  y `update_or_create` (reimportar sobrescribe).
- **Periodo:** `activo=False`, `publico=True`, `orden` = siguiente al último.
- **Totales cargados:** 14 evaluaciones · 180 `EvaluacionResultado` · 395 detalles mensuales.

### 14.2. Textos normalizados para igualar a v1

El catálogo de 2026 debía ser **idéntico a v1** salvo cambios intencionales. Se corrigieron en el
Excel (con respaldo previo) estas diferencias —principalmente **tildes** que el importador no
normaliza y un typo— para que reusara el catálogo v1 en lugar de crear entradas nuevas:

| Nivel | 2026 (antes) | v1 (corregido a) | Motivo |
|---|---|---|---|
| Subindicador (PIIP) | `Índice de Cumplimiento a la Programación - PIIP` | `Indice de Cumplimiento a la Programación - PIIP` | tilde en "Índice" |
| Subindicador (GESPROY) | `Índice de Eficiencia en la Contratación o Índice de Eficiencia en la Ejecución - GESPROY` | `Indice de Eficiencia en la Contratación o Indice de Eficiencia en la Ejecución - GESPROY` | dos tildes |
| Criterio (de `Tiempo`) | `Después de tiempo = No reportar` | `Despues de tiempo = No reportar` | tilde en "Después" |
| Criterio | `Índice mensual de acuerdo con la ejecución física cargada` | `Indice mensual de acuerdo con la ejecución física cargada` | tilde en "Índice" |
| Subindicador | `Cumplimento Acumulado: Avance en el tiempo…` | `Cumplimiento Acumulado: Avance en el tiempo…` | typo "Cumplim**ento**" → "Cumplim**iento**" |

Además se recortaron **espacios** sobrantes/dobles y `\xa0` (no-break space) en los textos
(p. ej. `"Resultados: 70% (Se promedia el  valor…"` con doble espacio). Verificación final del
Excel: catálogo idéntico a v1 **salvo Estratégicos**, 0 espacios, 0 typos, cascada de pesos OK y
`ponderado = puntaje × peso` OK.

### 14.3. Cambio real (NO normalizado): subindicador de Estratégicos

El subindicador de **`Ciclos de Gerencia > Estratégicos`** **cambió de verdad** en 2026 y se
**conserva** como nuevo (no se iguala a v1):

- v1 (2025): `Indice de Cumplimiento a la Programación etapa previa a asignación de recursos y ejecución - ESTRATÉGICOS`
- 2026: `Resultados: 70% (Se promedia el valor de cada proyecto de acuerdo a su estado de avance) Gestión (Cumplimiento de Compromisos):30%`

Consecuencia: en los **5 modelos** que tienen el indicador Estratégicos (Salud, Infraestructura,
Inclusión Social, Aguas de Sucre, Unidad del Riesgo) ese indicador queda con **dos**
subindicadores: el de v1 (datos solo de 2025) y el de 2026 (datos solo de 2026). Es válido: cada
`EvaluacionResultado` apunta a su subindicador.

> **Nota:** un mismo modelo/categoría puede, en distintos periodos, **no evaluar** un subindicador
> o **agregar** uno (p. ej. en 2026 *Unidad del Riesgo* sumó Estratégicos y *Tránsito* —mismo
> modelo— no). Es esperado; el periodo simplemente no crea resultado para los subindicadores que
> no aplican.

---

## 15. Módulo de Reportes (Excel / PDF por dependencia)

`/reportes/` (sidebar **General → Reportes**, con login) genera **informes descargables** con la
evaluación diligenciada de cada dependencia, **calcando la estructura de la pantalla de
evaluación**. Los constructores viven en `mag/contenido/reportes.py`; las vistas y el armado de
datos en `views.py`; la plantilla en `templates/reportes/reportes.html`.

### 15.1. Filtros y lógica de alcance
- **Versión**, **Categoría** (incluye "Todas las categorías") y **Periodo**: selección **única**
  (cascada por GET, `onchange submit`, reutilizando `_versiones_disponibles`, `_resolver_categoria`,
  `_periodos_con_datos`, `_eval_kwargs`).
- **Dependencia**: **opcional / múltiple** (checklist buscable con chips).
- Alcance (`_deps_en_alcance`): dependencias con `Evaluacion` en ese periodo+versión (y categoría si
  no es "Todas"). **Sin selección o "Todas"** → todas, **una hoja/página por dependencia**; con
  selección → solo esas.
- El POST a `reporte_generar` arma la matriz (`construir_matriz`, read-only) y devuelve el archivo
  con `HttpResponse` (descarga). **No escribe en BD.**

### 15.2. Estructura del informe (Excel y PDF)
Columnas **Pilar | Indicador | Subindicador | Tipo | Criterios | [meses bajo "Puntaje (0-100)"] |
Ponderación | Observaciones**, cabecera de 2 filas, logo de la Gobernación arriba a la derecha e
info (Categoría · Dependencia · Periodo · Versión).
- **Pilar/Indicador combinados** por grupo: en Excel con *merge* de celdas; en **PDF sin `rowspan`**
  (fpdf2 no puede partir un rowspan entre páginas → daba error 500): se rotula en la primera fila del
  grupo y se colorea la columna.
- **Meses = área de puntaje**: `mensual` → un valor por mes; **`directo` → celdas de meses
  combinadas** con el puntaje (no hay columna de puntaje consolidado, igual que en la evaluación).
- **Pesos** con **2 decimales**; puntaje/ponderación con el filtro min2/max5.

### 15.3. Motores y dependencias
- **Excel:** `openpyxl` (ya estaba). **PDF:** **`fpdf2`** (Python puro). Se **descartó `reportlab`**
  porque **importa Pillow al cargar** y en Windows con *Smart App Control* el DLL nativo de Pillow
  queda **bloqueado por el SO**; `fpdf2` no importa Pillow al cargar.
- **Logo *best-effort*:** tanto openpyxl como fpdf2 necesitan Pillow para incrustar imágenes; si
  Pillow no está disponible, el informe se genera **igual, sin el logo** (envuelto en try/except).
  En Railway (Linux, Pillow OK) el logo **sí** aparece.
- El PDF usa fuente 6.5 + un tope defensivo (`_cap`, ~1400 chars/celda) para que una observación
  muy larga no exceda una página (re-dispararía el error de fpdf2).

### 15.4. Permisos
Ambas vistas llevan `@login_required` y están en `EVALUADOR_URLS_PERMITIDAS` (`roles.py`): las ve
**todo usuario con login**, incluido el rol Evaluador.
