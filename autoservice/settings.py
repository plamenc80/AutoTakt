"""
Настройки на приложението „АвтоТакт“ (Django).

База данни SQLite, потребители и роли, български език.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Ключът за подписване на бисквитките. В продукция се задава като променлива на средата.
SECRET_KEY = os.environ.get("AUTOSERVICE_SECRET_KEY", "dev-only-6tSs1lYG5INS8Qh8QaCo2c26mNd0hBy0pOyz8tW3Em0")
# Режим за разработка (подробни страници за грешки) - само изрично: AUTOSERVICE_DEBUG=1.
# По подразбиране е изключен, за да не се показват код и SQL при грешка.
DEBUG = os.environ.get("AUTOSERVICE_DEBUG", "0") == "1"
# Допълнителни адреси, напр. IP на компютъра, за да се отвори от телефон в същата мрежа: AUTOSERVICE_HOSTS=192.168.1.10
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"] + [h for h in os.environ.get("AUTOSERVICE_HOSTS", "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.auth",          # потребители, групи (роли), хеширане на пароли (PBKDF2 + salt)
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",      # съобщенията „Записано“ / „Грешка“ след действие
    "django.contrib.staticfiles",
    "data",                         # слой „Данни“: модели, миграции, демо данни
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",            # защита от CSRF за всички POST
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "autoservice.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "autoservice.wsgi.application"

# База данни - SQLite файл, който се създава автоматично (python manage.py start).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("AUTOSERVICE_DB", BASE_DIR / "autoservice.db"),
        # Транзакциите взимат правото за запис още в началото, а едновременните заявки чакат (до 20 s),
        # вместо да получат грешка „database is locked“.
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

# Български език и местно време (датите се пазят като местно време).
LANGUAGE_CODE = "bg"
TIME_ZONE = "Europe/Sofia"
USE_I18N = True
USE_TZ = False

STATIC_URL = "/static/"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Грешките се записват в конзолата и когато DEBUG е изключен.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}


# Съобщенията след действие (успех / предупреждение / грешка) - пазят се в сесията до следващата страница.
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

AUTH_USER_MODEL = "data.User"
