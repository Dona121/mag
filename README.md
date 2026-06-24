# Modelo de Alta Gerencia (MAG) — Gobernación de Sucre

Aplicación **Django 5.2** para **parametrizar, diligenciar y reportar** las
evaluaciones de desempeño de las dependencias de la Gobernación de Sucre. Sustituye
el flujo previo en Excel + Power BI por un sistema web con:

- **Parametrización** del modelo de evaluación (pilares, indicadores, subindicadores, criterios y pesos).
- **Diligenciamiento** de puntajes por periodo y dependencia, con permisos por indicador.
- **Dashboard interno** (con login) y **reporte público** (`/reporte/`, sin login), ambos réplica de las 4 vistas del Power BI: **IMAG, Desempeño, Ranking y Variaciones**.

---

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Django 5.2, vistas función + clase |
| Admin | django-unfold |
| Base de datos | PostgreSQL (Railway) · SQLite en local |
| Estáticos | WhiteNoise |
| Gráficos | Chart.js v4 (vendorizado en `mag/static/vendor/`) |
| Servidor | Gunicorn |
| Tipografía / paleta | Montserrat + colores del Manual de Identidad |

Dependencias en `requirements.txt` (o `pyproject.toml` + `uv.lock`).

---

## Estructura

```
modelo_alta_gerencia/
├── mag/
│   ├── manage.py
│   ├── .env                  # variables de entorno (NO versionar)
│   ├── mag/                  # proyecto (settings.py, urls.py, wsgi.py)
│   ├── contenido/            # app principal (models, views, urls, admin, roles, middleware)
│   ├── templates/            # base/, reporte/, evaluaciones/, periodos/, modelos/, registration/
│   └── static/               # css/, logos/, vendor/
├── DOCUMENTACION.md          # documentación funcional y técnica detallada
├── NOTAS_TECNICAS.md         # modelos, flujo paso a paso, glosario del ORM y despliegue
├── GUIA_DISEÑO.md            # sistema de diseño (paleta, tipografía, componentes)
├── requirements.txt
└── README.md
```

---

## Puesta en marcha (local)

> Todos los comandos de `manage.py` se ejecutan **desde la carpeta `mag/`**
> (es donde `python-dotenv` encuentra el `.env`).

```bash
# 1. Entorno e instalación
python -m venv .venv
.venv\Scripts\activate            # Windows ;  source .venv/bin/activate en Unix
pip install -r requirements.txt    # o:  uv sync

# 2. Variables de entorno  ->  crear  mag/.env
#    (ver sección siguiente)

# 3. Migraciones y superusuario
cd mag
python manage.py migrate
python manage.py createsuperuser

# 4. Servidor de desarrollo
python manage.py runserver
```

### Variables de entorno (`mag/.env`)

| Variable | Para qué | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave de Django | `una-clave-larga-y-secreta` |
| `DEBUG` | Modo depuración | `1` en local, `0` en producción |
| `ALLOWED_HOSTS` | Hosts permitidos (coma) | `localhost,127.0.0.1` |
| `DATABASE_URL` | Postgres (si se omite, usa SQLite local) | `postgres://user:pass@host:5432/db` |

> El `.env` contiene secretos: está en `.gitignore` y **no debe versionarse**.

### Estáticos (punto crítico)

Con `DEBUG=False`, WhiteNoise sirve los archivos **recolectados**. Tras cambiar
imágenes/CSS hay que correr:

```bash
python manage.py collectstatic
```

---

## Áreas principales

| Ruta | Acceso | Descripción |
|---|---|---|
| `/` | login | Inicio (tarjetas de resumen) |
| `/dashboard/`, `/dashboard/{desempeno,ranking,variaciones}/` | login | Dashboard interno: 4 vistas del reporte **sin** restricción de periodo público (ve todos los periodos) |
| `/reporte/`, `/reporte/{desempeno,ranking,variaciones}/` | **público** | Reporte de resultados: solo periodos marcados como públicos |
| `/evaluaciones/` | login | Listado de evaluaciones activas + diligenciamiento |
| `/modelos/`, `/categorias/...`, `/periodos/` | login | Parametrización y operación |
| `/admin/` | staff | Admin de Django (django-unfold) |

---

## Roles y permisos

Dos capas, **independientes pero combinables** (los **superusuarios** quedan exentos de ambas):

1. **Edición por indicador (`PerfilUsuario`):** cada usuario solo edita el puntaje de los indicadores que tiene asignados; el resto los ve en **solo lectura**. La validación es server-side (un POST con indicadores no asignados se ignora).
2. **Rol `Evaluador` (grupo de Django):** en el panel solo ve **General** (Inicio + Dashboard), **Operación → Evaluaciones** y **Cuenta**. Un middleware bloquea (deny-by-default) cualquier otra URL.

Para un evaluador del equipo: agréguelo al grupo **Evaluador** y asígnele sus indicadores en el `PerfilUsuario` (ambos desde el admin de User).

---

## Convenciones clave

- **La base de datos es fija**: el desarrollo toca solo vistas, plantillas, admin, URLs, settings y estáticos (no `models.py`, salvo decisión explícita).
- **Jerarquía:** `ModeloEvaluacion → Pilar → Indicador → Subindicador → Criterio`; operación con `Dependencia`, `Categoria`, `Periodo`, `Evaluacion`, `EvaluacionResultado` (+ detalle mensual).
- **`Periodo.activo`** controla la disponibilidad de diligenciamiento; **`Periodo.publico`** controla la visibilidad en el reporte público; **`Periodo.vigencia`** (año) alimenta el filtro por año y **`Periodo.umbral`** es el objetivo (%) del ranking.
- **Pivote del dashboard/reporte = `Categoria`** (clasificación de la dependencia, **congelada en `Evaluacion.categoria`** al crearla); incluye la opción **"Todas las categorías"** (IMAG general). Las 4 vistas se filtran además por **versión del modelo** y por **vigencia (año)**.
- **Filtro de versión = por número de versión** (1, 2, …), no por estructura: una versión puede tener **varias estructuras** (varios `ModeloEvaluacion` para distintos grupos de dependencias), y al elegir una versión entran **todas** sus estructuras. Por eso los pilares se agregan por **nombre** (si no, se duplicarían).
- **Precisión decimal:** `peso`, `puntaje` y `ponderacion` son `DecimalField(max_digits=10, decimal_places=5)`.
- **Ponderación:** `EvaluacionResultado.ponderacion = puntaje × peso_subindicador / 100`; agrega subindicador → (suma) dependencia → (promedio) pilar → (suma) IMAG. Hoy solo pesa el subindicador (los pesos de Indicador/Pilar no cascadean: decisión de negocio pendiente).

---

## Migración del histórico (v1)

El histórico **versión 1** (vigencia 2025, antes en Excel) se importa con un management
command. Las hojas del `.xlsx` son una por dependencia (más la hoja `categorias` que mapea
dependencia → categoría); las dependencias se agrupan por **estructura** y se crea un
`ModeloEvaluacion` (version=1) por estructura.

```bash
$env:PYTHONUTF8="1"                                  # Windows: acentos en consola
python manage.py importar_v1 migracion/archivo.xlsx           # simula (no escribe)
python manage.py importar_v1 migracion/archivo.xlsx --commit  # escribe en la BD
```

Para **agregar un periodo nuevo a una v1 ya existente** (p. ej. el trimestre de 2026) se usa otro
command que **no recrea modelos**: vincula cada dependencia a su modelo v1 y solo añade el periodo
(detecta el layout del periodo desde los encabezados).

```bash
python manage.py importar_periodo_v1 migracion/archivo.xlsx           # simula
python manage.py importar_periodo_v1 migracion/archivo.xlsx --commit  # escribe en la BD
```

Requiere `openpyxl` (ya en `pyproject.toml`). Detalle completo en `NOTAS_TECNICAS.md`; la guía de
revisión de un Excel y la bitácora de la migración 2026 (con los textos normalizados) están en
`DOCUMENTACION.md` §13 y §14.

## Documentación

- **`DOCUMENTACION.md`** — documentación funcional y técnica detallada (frontend, flujo de datos, ponderación, URLs, bitácora).
- **`NOTAS_TECNICAS.md`** — descripción de cada modelo, ejemplo guiado de punta a punta, glosario del ORM (qué hace cada operador), localización de decimales y guía de despliegue en Railway.
- **`GUIA_DISEÑO.md`** — sistema de diseño reutilizable (paleta institucional, tipografía Montserrat, componentes, logos) basado en el Manual de Identidad.
