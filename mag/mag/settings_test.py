"""
Settings SOLO para la suite de tests.

Fuerza SQLite en memoria para que los tests NUNCA toquen la base de datos
remota (Supabase/Railway) definida por DATABASE_URL, y usa un hasher de
contrasenas rapido. Todo lo demas se hereda de settings.py.

Uso (desde la carpeta `mag/`):
    python manage.py test --settings=mag.settings_test
"""
from .settings import *  # noqa: F401,F403

# BD aislada y efimera: se crea/destruye en cada corrida, en memoria.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Hasher rapido: acelera create_user/login en los tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Evita depender de collectstatic durante los tests.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEBUG = False
