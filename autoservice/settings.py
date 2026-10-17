"""
Настройки на приложението „АвтоТакт“ (Django).

База данни SQLite, потребители и роли, български език и данни за сервиза.
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
    "web",                          # слой „Уеб“: изгледи, шаблони, дизайн
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",            # защита от CSRF за всички POST
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "web.live.ChangeNotifierMiddleware",                     # сигнал „нещо се промени“ за таблата
    "web.middleware.StatusPagesMiddleware",                  # страница на сайта за 405, 400 и др.
    "web.middleware.CanonicalUrlMiddleware",                 # /repairorders/details/5/ → /RepairOrders/Details/5
]

ROOT_URLCONF = "autoservice.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.context.garage",   # данните за сервиза и ролите във всеки шаблон
            ],
            "builtins": ["web.templatetags.display"],  # филтрите |euro, |bg и т.н. без {% load %}
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
    {"NAME": "web.validators.DigitAndUppercaseValidator"},
]

LOGIN_URL = "/Account/Login"
LOGIN_REDIRECT_URL = "/"

# Български език и местно време (датите се пазят като местно време).
LANGUAGE_CODE = "bg"
TIME_ZONE = "Europe/Sofia"
USE_I18N = True
USE_TZ = False

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "web" / "static"]

# Снимките от проверките - извън static, отдават се само през изглед с проверка на правата.
PHOTO_ROOT = Path(os.environ.get("AUTOSERVICE_PHOTOS", BASE_DIR / "private" / "photos"))

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Страница при липсващ/невалиден CSRF токен - на сайта, на български.
CSRF_FAILURE_VIEW = "web.views.core.csrf_failure"

# Грешките се записват в конзолата и когато DEBUG е изключен.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}


# Съобщенията след действие (успех / предупреждение / грешка) - пазят се в сесията до следващата страница.
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Данни за сервиза, които се показват на сайта.
GARAGE = {
    "name": "АвтоТакт",
    "city": "София",
    "address": "ул. „Моторна“ 7, 1000 София",
    "phone": "02 000 0000",
    "email": "info@avtotakt.com",
    "hero_image": "/static/img/hero.jpg?v=2",
    "hero_image_phone": "/static/img/hero-phone.jpg?v=2",
    "opening_hours": [
        {"days": "Понеделник – петък", "hours": "8:00 – 18:00"},
        {"days": "Събота и неделя", "hours": "почивни дни"},
    ],
}

AUTH_USER_MODEL = "data.User"
