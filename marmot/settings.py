"""
Django settings for marmot project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_IMAGE_UPLOAD_DIR = os.path.join(BASE_DIR, "media")
os.makedirs(TEMP_IMAGE_UPLOAD_DIR, exist_ok=True)

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def get_env_var(key):
    val = os.getenv(key)
    if val is None:
        raise KeyError(f"Required environment variable '{key}' is missing from .env.")
    return val


def env_to_bool(key):
    val = get_env_var(key)
    return val.lower() in ("true", "1", "yes", "on")


# Core Environment Configuration & Debug
SECRET_KEY = get_env_var("SECRET_KEY")
OTP_SECRET_KEY = get_env_var("OTP_SECRET_KEY")
DEBUG = env_to_bool("DEBUG")
ENVIRONMENT = get_env_var("ENVIRONMENT")
ALLOWED_HOSTS = [host.strip() for host in get_env_var("ALLOWED_HOSTS").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in get_env_var("CSRF_TRUSTED_ORIGINS").split(",") if origin.strip()]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# WebSockets & Endpoints
MARMOT_WS_URL = get_env_var("MARMOT_WS_URL")
WS_PORT = get_env_var("WS_PORT")

# Role-Based Access Control Settings
POSTBACK_VIEW_ROLES = [role.strip() for role in get_env_var("POSTBACK_VIEW_ROLES").split(",") if role.strip()]
MANAGEMENT_ROLES = ['admin', 'manager']

APPEND_SLASH = True

# Application definition
INSTALLED_APPS = [
    # Custom User Model App FIRST (fixes admin migration dependency order)
    'apps.users',

    # Built-in Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third-Party Apps
    'cloudinary_storage',
    'cloudinary',
    'apscheduler',
    'django_filters',

    # Project Apps
    'apps.admins',
    'apps.api',
    'apps.backtest',
    'apps.common',
    'apps.market',
    'apps.masters',
    'apps.notifications',
    'apps.postback',
    'apps.trade_config',
    'apps.trade_core',

    # Allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.github',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Allauth account middleware
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'marmot.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.common.context_processors.theme_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'marmot.wsgi.application'

# Database Configuration
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE'),
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static & Media Storage Configuration
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cloudinary Configuration
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}

# Storage backends depending on DEBUG mode
if DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
        "staticfiles": {"BACKEND": "cloudinary_storage.storage.StaticCloudinaryStorage"},
    }

# Custom User Model & Authentication Settings
AUTH_USER_MODEL = "users.User"
LOGIN_URL = "users:marmot-login"
LOGIN_REDIRECT_URL = "users:marmot-dashboard"
LOGOUT_REDIRECT_URL = "home"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

handler404 = 'marmot.views.handler404'

# APScheduler Configuration
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_TIMEZONE = 'Asia/Kolkata'

# Pagination and Caching
PAGINATION_COUNT = int(os.getenv('PAGINATION_COUNT'))
REDIS_URL = os.getenv('REDIS_URL')

# Master Admin Dhan API credentials — used exclusively for market backup/ingestion (Admin only).
# User trading credentials are stored per-user in UserTradingAccount.
DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_API_KEY = os.getenv('DHAN_API_KEY')
DHAN_API_SECRET = os.getenv('DHAN_API_SECRET')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')

# OpenAlgo Integration
OPENALGO_API_KEY = os.getenv('OPENALGO_API_KEY')
OPENALGO_HOST = os.getenv('OPENALGO_HOST')

# Username Role Prefixes
PREFIX_TRADERS = os.getenv('PREFIX_TRADERS')
PREFIX_ADMIN = os.getenv('PREFIX_ADMIN')
PREFIX_MANAGER = os.getenv('PREFIX_MANAGER')

# Email / SMTP Configuration
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT'))
EMAIL_USE_TLS = env_to_bool('EMAIL_USE_TLS')
EMAIL_USE_SSL = env_to_bool('EMAIL_USE_SSL')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
TWILIO_VERIFY_SERVICE_SID = os.getenv('TWILIO_VERIFY_SERVICE_SID')

# Structured Logger Settings
LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS'))

# Allauth Configuration
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_ADAPTER = 'apps.users.adapter.MarmotSocialAccountAdapter'

# Social Account Providers Configuration
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'key': ''
        },
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    },
    'github': {
        'APP': {
            'client_id': os.getenv('GITHUB_CLIENT_ID'),
            'secret': os.getenv('GITHUB_CLIENT_SECRET'),
            'key': ''
        },
        'SCOPE': [
            'user:email',
            'read:user',
        ],
    }
}

# UI Theme Configuration (e.g. 'default', 'shadcn-zinc', 'shadcn-slate', 'shadcn-violet')
UI_THEME = os.getenv('UI_THEME', 'default')

