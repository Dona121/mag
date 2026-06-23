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
  dependencia. Constraint: **un solo modelo activo por dependencia**.
- **Periodo**: si su nombre incluye meses ("Enero - Febrero - Marzo"), el
  diligenciamiento mensual mostrará solo esos meses.
- **Evaluacion**: única por `(periodo, dependencia)`. Fija el modelo al crearse y
  **no se puede cambiar** después (validado en `clean()`).
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
   dependencia y el sistema toma automáticamente el **modelo activo** de esa
   dependencia. Valida que no exista ya `(periodo, dependencia)`.
6. **Diligenciar** (`evaluacion_diligenciar`): se renderiza la matriz
   Pilar → Indicador → Subindicador. Cada usuario edita solo lo permitido.

### Lógica de ponderación (`views.evaluacion_diligenciar`)

Todos los valores se **cuantizan a 2 decimales** (`ROUND_HALF_UP`, helper `_q2`).

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
| `/reporte/ranking/` | `reporte_ranking` | Reporte público — vista Ranking (Categoría = Modelo) |
| `/reporte/variaciones/` | `reporte_variaciones` | Reporte público — vista Variaciones |
| `/auth/login/` | `LoginView` | Inicio de sesión (template rediseñado) |
| `/auth/logout/` | `LogoutView` | Cierre de sesión |
| `/auth/password-change/` | `PasswordChangeView` | Cambio de contraseña |
| `/categorias/<tipo>/` … | `categoria_list/create/editar` | Catálogos de nombres (tipo: pilar/indicador/subindicador) |
| `/modelos/` … | parametrización | CRUD de modelo/pilar/indicador/sub/criterio |
| `/evaluaciones/` | `EvaluacionListView` | Listado de evaluaciones (solo periodos activos) |
| `/evaluaciones/nueva/` | `EvaluacionCreateView` | Crear evaluación (acceso por botón del listado, no por menú) |
| `/evaluaciones/<pk>/diligenciar/` | `evaluacion_diligenciar` | Diligenciar matriz (bloqueada si el periodo está inactivo) |
| `/periodos/` | `PeriodoListView` | Gestión de periodos (estado + activar/desactivar) |
| `/periodos/<pk>/activar/` | `periodo_activar` | Activar periodo — abre diligenciamiento (POST) |
| `/periodos/<pk>/desactivar/` | `periodo_desactivar` | Desactivar periodo (POST) |
| `/periodos/<pk>/publicar/` | `periodo_publicar` | Marcar `publico=True` — visible en reporte público (POST) |
| `/periodos/<pk>/despublicar/` | `periodo_despublicar` | Marcar `publico=False` (POST) |
| `/admin/` | django-unfold | Panel administrativo |

> El **rol Evaluador** solo puede acceder a `/`, `/dashboard/*`, `/evaluaciones/`,
> `/evaluaciones/<pk>/diligenciar/`, auth y el reporte público; el resto lo redirige
> al listado de evaluaciones (`RolEvaluadorMiddleware`).

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

Mapeo Excel/Power BI → modelos en `Mapeo_Dashboard_Django.md`; esquema de modelos
en `MODELOS.md`.

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
- **Ranking:** ranking de dependencias (Categoría = Modelo) contra el objetivo.
- **Variaciones:** Δ por dependencia vs. periodo anterior + mejor/peor.

### Filtros (server-side, vía GET)

- modelo, periodo, comparar (`0` = ninguno), pilar; Desempeño añade dependencia.
- Helpers `_resolver`, `_periodos_con_datos(modelo, solo_publicos)`, `_reporte_filtros`,
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

### Identidad visual

Consistente con la página y con el **Manual de Identidad** (`manual_identidad/…pdf`):
tipografía **Montserrat** y paleta institucional (verde `#109d39`, verde profundo
`#0e4d2a`, azul `#0b72ab`, rojo `#d92a34`, naranja `#ffa700`, ámbar `#d88c16`,
grises). El semáforo del modelo (verde/ámbar/rojo) codifica los datos.

### Las cuatro vistas (pestañas)

Replican las láminas del Power BI. El **"Indicador" del Power BI = `Pilar`** del
modelo; las **"Categorías" (Categoría 1/2/3/Gobernación) = `ModeloEvaluacion`**.

1. **IMAG** (`reporte_publico`, `/reporte/`) — KPIs de IMAG (último %, anterior %,
   variación en puntos), evolución del **% de cumplimiento por pilar**
   (`promedio/peso·100`) y tabla *Pilar | Anterior | Último* con sombreado verde.
2. **Desempeño** (`reporte_desempeno`, `/reporte/desempeno/`) — por dependencia:
   KPIs del puntaje del periodo contra **objetivo 60 %** (con la brecha) y
   **small-multiples**: una mini-gráfica de evolución por cada pilar.
3. **Ranking** (`reporte_ranking`, `/reporte/ranking/`) — fila de pestañas de
   **Categoría = Modelo**; barras por dependencia (mejor en verde + **línea de
   objetivo 40 %**) y tabla *Dependencia | Puntaje* con sombreado azul, ordenada.
4. **Variaciones** (`reporte_variaciones`, `/reporte/variaciones/`) — KPIs
   (mejor/peor variación y mejor/peor desempeño), tabla *Dependencia | Anterior |
   Último | Variación* con sombreado verde/rojo y barras horizontales de variación.

### Cálculos y filtros

- Reutiliza los **mismos helpers** del dashboard interno (`_datos_dashboard`,
  `_serie_temporal`, `_datos_dependencia`, `_serie_dependencia`, `_imag_max`,
  `_estado_semaforo`, `_shade` para el sombreado de tablas). Todo en puntos/%.
- Filtros **server-side (GET)**, auto-submit: modelo, periodo, comparar, pilar
  (y dependencia en Desempeño). Helper compartido `_reporte_filtros` /
  `_ctx_filtros`. Parámetros inválidos caen al valor por defecto.
- **Gráficos con Chart.js** vendorizado; los datos se inyectan inline con
  `{{ payload|json_script }}` (no hay endpoint AJAX aparte). Anchos/sombras usan
  `|unlocalize` (locale `es-col` mete coma decimal).
- Los **objetivos 60 % (Desempeño) y 40 % (Ranking)** son constantes que replican
  el Power BI; si deben venir de la BD o variar por modelo, se parametrizan.

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
  **Activar/Desactivar** (POST). También se gestiona desde `PeriodoAdmin`
  (filtro, edición en línea y acciones masivas).
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
```
