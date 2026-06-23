"""
Django settings for mag project.
"""
from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()
from django.urls import reverse_lazy
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-dev-only")
# DEBUG booleano desde env
DEBUG = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes", "on")

# ALLOWED_HOSTS configurable por env; auto-incluye dominio de Railway
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if _railway_domain:
    ALLOWED_HOSTS.append(_railway_domain)
if not ALLOWED_HOSTS:
    # Fallback abierto solo en desarrollo
    ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'contenido.apps.ContenidoConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise sirve los static files comprimidos en produccion.
    # Debe ir INMEDIATAMENTE despues de SecurityMiddleware.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Restringe la navegacion del rol Evaluador (despues de Auth y Messages).
    'contenido.middleware.RolEvaluadorMiddleware',
]

ROOT_URLCONF = 'mag.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'contenido.context_processors.roles',
            ],
        },
    },
]

WSGI_APPLICATION = 'mag.wsgi.application'

# Base de datos. Si DATABASE_URL existe (Railway), la usa; si no, sqlite local.
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600),
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-col'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# Traducciones personalizadas (sobrescribe mensajes de Django/Unfold).
LOCALE_PATHS = [BASE_DIR / "locale"]

# ----------------------------------------------------------- Static
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Storage backends (Django 4.2+).
# Usamos CompressedStaticFilesStorage (sin manifest) para que el admin no
# falle con 500 si `collectstatic` no se corrio en el build. Comprime
# (gzip + brotli) pero no requiere `staticfiles.json`.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ----------------------------------------------------------- Auth
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login/"

# Railway pone la app detras de proxy https
CSRF_TRUSTED_ORIGINS = [
    "https://modeloaltagerencia-production.up.railway.app",
    "https://mag-production.up.railway.app",
]
_extra_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS += [o.strip() for o in _extra_csrf.split(",") if o.strip()]
if _railway_domain:
    CSRF_TRUSTED_ORIGINS.append("https://{}".format(_railway_domain))

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# =============================================================================
# DJANGO-UNFOLD — solo titulos y navegacion. Colores por defecto.
# =============================================================================
UNFOLD = {
    "SITE_TITLE": "Modelo de Alta Gerencia",
    "SITE_HEADER": "Gobernacion de Sucre",
    "SITE_SUBHEADER": "Modelo de Alta Gerencia",
    "SITE_URL": "/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,

    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Administracion",
                "separator": True,
                "items": [
                    {"title": "Grupos",   "icon": "group",  "link": reverse_lazy("admin:auth_group_changelist")},
                    {"title": "Usuarios", "icon": "person", "link": reverse_lazy("admin:auth_user_changelist")},
                ],
            },
            {
                "title": "Parametrizacion",
                "separator": True,
                "items": [
                    {"title": "Modelos de evaluacion", "icon": "schema",      "link": "/admin/contenido/modeloevaluacion/"},
                    {"title": "Pilares",               "icon": "view_column", "link": "/admin/contenido/pilar/"},
                    {"title": "Indicadores",           "icon": "insights",    "link": "/admin/contenido/indicador/"},
                    {"title": "Subindicadores",        "icon": "format_list_bulleted", "link": "/admin/contenido/subindicador/"},
                    {"title": "Criterios",             "icon": "rule",        "link": "/admin/contenido/criterio/"},
                    {"title": "Categorías de pilar",        "icon": "category", "link": "/admin/contenido/pilarcategoria/"},
                    {"title": "Categorías de indicador",    "icon": "category", "link": "/admin/contenido/indicadorcategoria/"},
                    {"title": "Categorías de subindicador", "icon": "category", "link": "/admin/contenido/subindicadorcategoria/"},
                ],
            },
            {
                "title": "Catalogos",
                "separator": True,
                "items": [
                    {"title": "Categorias",         "icon": "label",          "link": "/admin/contenido/categoria/"},
                    {"title": "Dependencias",       "icon": "account_tree",   "link": "/admin/contenido/dependencia/"},
                    {"title": "Dependencia/Modelo", "icon": "swap_horiz",     "link": "/admin/contenido/dependenciamodelo/"},
                    {"title": "Periodos",           "icon": "calendar_today", "link": "/admin/contenido/periodo/"},
                ],
            },
            {
                "title": "Operacion",
                "separator": True,
                "items": [
                    {"title": "Evaluaciones",       "icon": "fact_check",     "link": "/admin/contenido/evaluacion/"},
                    {"title": "Resultados",         "icon": "scoreboard",     "link": "/admin/contenido/evaluacionresultado/"},
                    {"title": "Detalles mensuales", "icon": "calendar_month", "link": "/admin/contenido/evaluacionresultadodetalle/"},
                ],
            },
        ],
    },
}
