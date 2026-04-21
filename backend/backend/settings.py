"""
Django settings for the Critter backend.

Mirrors the env-driven, PROD_DEPLOY-toggled approach from RateRail
(`~/Code/mine/local_django_react/django_loan/backend/backend/settings.py`).
Single settings file by design — the PROD_DEPLOY flag switches DB,
Redis, GCS, and CORS between local and Cloud Run modes.
"""

from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import os
import json
from google.oauth2 import service_account

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / '.env')

# ----------------------------------------------------------------------
# Core
# ----------------------------------------------------------------------

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-only-change-me')
PROD_DEPLOY = os.environ.get('PROD_DEPLOY', 'False')
DEBUG = PROD_DEPLOY != 'True'

SITE_URL = os.environ.get('SITE_URL', 'https://critter.app')
REACT_BASE_URL = os.environ.get('REACT_BASE_URL', 'http://localhost:5173')

ALLOWED_HOSTS = [
    'critter.app',
    'www.critter.app',
    '.run.app',  # Cloud Run
    'localhost',
    '127.0.0.1',
]

# Optional ngrok hostname — paste just the hostname (no scheme) into NGROK_HOST
# in .env. Free-tier ngrok URLs change every restart, so .env is easier to edit
# than settings.py. Adds it to both ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS.
NGROK_HOST = os.environ.get('NGROK_HOST', '').strip()
if NGROK_HOST:
    ALLOWED_HOSTS.append(NGROK_HOST)

# ----------------------------------------------------------------------
# GCP service account credentials
# Same pattern as RateRail: file path locally, JSON blob in prod (from Secret Manager)
# ----------------------------------------------------------------------

# Load the Critter service account once. We pass these credentials explicitly
# to every Google client (django-storages, google-cloud-storage, google-genai)
# so we NEVER fall back to the developer's `gcloud auth application-default
# login` user account. VERTEX_CREDENTIALS adds the cloud-platform scope that
# Vertex AI / Gemini calls require.
GOOGLE_SA_KEYFILE = os.environ.get('GOOGLE_SA_KEYFILE')
VERTEX_SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

if GOOGLE_SA_KEYFILE:
    if PROD_DEPLOY == 'True':
        # In prod the env var holds the raw JSON blob (from Secret Manager)
        _sa_info = json.loads(GOOGLE_SA_KEYFILE)
        GS_CREDENTIALS = service_account.Credentials.from_service_account_info(_sa_info)
        VERTEX_CREDENTIALS = service_account.Credentials.from_service_account_info(
            _sa_info, scopes=VERTEX_SCOPES,
        )
    else:
        GS_CREDENTIALS = service_account.Credentials.from_service_account_file(GOOGLE_SA_KEYFILE)
        VERTEX_CREDENTIALS = service_account.Credentials.from_service_account_file(
            GOOGLE_SA_KEYFILE, scopes=VERTEX_SCOPES,
        )
else:
    GS_CREDENTIALS = None
    VERTEX_CREDENTIALS = None
    print('⚠️  GOOGLE_SA_KEYFILE not set — Veo, Gemini Vision, and GCS uploads will fail')

# ----------------------------------------------------------------------
# Apps
# ----------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'storages',
    'django_rq',
    'django_ratelimit',

    # Local apps
    'core',
    'users',
    'orgs',
    'analytics',
    'subjects',
    'themes',
    'assets',
    'generations',
    'stories',
    'billing',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'users.middleware.SingleDeviceSessionMiddleware',
    'users.middleware.TwoFactorSecurityMiddleware',
    'users.middleware.AuthenticationErrorMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'analytics.middleware.AnalyticsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# ----------------------------------------------------------------------
# Database — Postgres only (Cloud SQL in prod, local Postgres or proxy in dev)
# ----------------------------------------------------------------------

gcp_db_name = os.environ.get('GCP_SQL_DB_NAME', 'critter')
gcp_db_user = os.environ.get('GCP_SQL_PROD_USER', 'postgres')
gcp_db_password = os.environ.get('GCP_SQL_PROD_PASSWORD', '')
gcp_db_connection_name = os.environ.get('GCP_SQL_CONNECTION_NAME', '')

if PROD_DEPLOY == 'True':
    print('🚀 Using production Cloud SQL via unix socket')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': gcp_db_name,
            'USER': gcp_db_user,
            'PASSWORD': gcp_db_password,
            'HOST': f'/cloudsql/{gcp_db_connection_name}',
            'PORT': '',
            'OPTIONS': {'sslmode': 'disable'},
            'CONN_MAX_AGE': 300,
            'CONN_HEALTH_CHECKS': True,
        }
    }
else:
    db_host = os.environ.get('GCP_SQL_PUBLIC_IP_ADDRESS', '127.0.0.1')
    db_port = os.environ.get('GCP_SQL_PORT', '5432')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': gcp_db_name,
            'USER': gcp_db_user,
            'PASSWORD': gcp_db_password,
            'HOST': db_host,
            'PORT': db_port,
            'OPTIONS': {'sslmode': 'disable', 'connect_timeout': 60},
            'CONN_MAX_AGE': 300,
        }
    }

# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------

AUTH_USER_MODEL = 'users.CustomUser'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ----------------------------------------------------------------------
# Internationalization
# ----------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Chicago'
USE_I18N = True
USE_TZ = True

# ----------------------------------------------------------------------
# Static + media (GCS)
# ----------------------------------------------------------------------

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
GS_BUCKET_NAME = os.environ.get('GS_BUCKET_NAME', 'critter-clean').strip()
GS_PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT_ID', 'wtroy-test-proj')
GS_DEFAULT_ACL = None
GS_QUERYSTRING_AUTH = True
GS_ACCESS_TOKEN_EXPIRE_SECONDS = 3600
GS_FILE_OVERWRITE = False
GS_MAX_MEMORY_SIZE = 50 * 1024 * 1024
GS_BLOB_CHUNK_SIZE = 1024 * 1024
MEDIA_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/'

FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# Three-bucket pipeline for user uploads (mirrors RateRail)
GS_UNSCANNED_BUCKET_NAME = os.environ.get('GS_UNSCANNED_BUCKET_NAME', 'critter-unscanned')
GS_CLEAN_BUCKET_NAME = os.environ.get('GS_CLEAN_BUCKET_NAME', 'critter-clean')
GS_QUARANTINE_BUCKET_NAME = os.environ.get('GS_QUARANTINE_BUCKET_NAME', 'critter-quarantine')

# ClamAV scanning (off by default in dev)
CLAMAV_SCANNER_URL = os.environ.get('CLAMAV_SCANNER_URL', '')
ENABLE_CLAMAV_SCANNING = os.environ.get('ENABLE_CLAMAV_SCANNING', 'false').lower() == 'true'
FAIL_CLOSED_ON_SCAN_ERROR = PROD_DEPLOY == 'True'

# ----------------------------------------------------------------------
# CORS / CSRF
# ----------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
    'cache-control', 'pragma',
]
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
CORS_EXPOSE_HEADERS = ['content-type', 'content-disposition', 'content-length', 'x-csrftoken']

CSRF_TRUSTED_ORIGINS = [
    'https://critter.app',
    'https://www.critter.app',
]
if PROD_DEPLOY != 'True':
    CSRF_TRUSTED_ORIGINS += [
        'http://localhost:8000', 'http://127.0.0.1:8000',
        'http://localhost:5173', 'http://127.0.0.1:5173',
    ]
    if NGROK_HOST:
        CSRF_TRUSTED_ORIGINS.append(f'https://{NGROK_HOST}')
else:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ----------------------------------------------------------------------
# DRF + JWT
# ----------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '10000/hour',
        'login': '0.1/min',
        'password_reset': '5/hour',
        'forgot_password': '3/hour',
        'username_recovery': '3/hour',
    }
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'LEEWAY': 30,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# ----------------------------------------------------------------------
# 2FA + sessions + password reset
# ----------------------------------------------------------------------

# Set REQUIRE_2FA=False in .env to bypass the email-code step entirely —
# initiate-login will issue a JWT directly. Useful in dev when you don't
# have an SMTP sender configured. Always keep this True in production.
REQUIRE_2FA = os.environ.get('REQUIRE_2FA', 'True') == 'True'

TWO_FACTOR_CODE_LENGTH = 6
TWO_FACTOR_CODE_EXPIRY_MINUTES = 10
MAX_2FA_ATTEMPTS = 3
MAX_DAILY_2FA_CODES = 10

PASSWORD_RESET_CODE_LENGTH = 8
PASSWORD_RESET_CODE_EXPIRY_MINUTES = 30
MAX_PASSWORD_RESET_ATTEMPTS = 3
MAX_DAILY_PASSWORD_RESET_CODES = 5

MAX_DAILY_USERNAME_RECOVERY_REQUESTS = 3

SINGLE_DEVICE_SESSION = True
MAX_CONCURRENT_SESSIONS = 1
SESSION_DEVICE_FINGERPRINT_FIELDS = [
    'HTTP_USER_AGENT',
    'HTTP_X_FORWARDED_FOR',
    'REMOTE_ADDR',
]

ACCOUNT_LOCKOUT_ENABLED = False
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'

# ----------------------------------------------------------------------
# Email
# ----------------------------------------------------------------------

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
if PROD_DEPLOY != 'True':
    # In dev, fall back to console backend if no SMTP credentials
    if not os.environ.get('EMAIL_HOST_PASSWORD'):
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'no-reply@critter.app')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Critter <no-reply@critter.app>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ----------------------------------------------------------------------
# Redis + RQ queues
# ----------------------------------------------------------------------

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', '6379'))

_redis_config = {
    'HOST': REDIS_HOST,
    'PORT': REDIS_PORT,
    'DB': 0,
    'CONNECTION_KWARGS': {
        'socket_connect_timeout': 30,
        'socket_timeout': 30,
        'retry_on_timeout': True,
    },
}

RQ_QUEUES = {
    'high':    {**_redis_config, 'DEFAULT_TIMEOUT': 60,   'DEFAULT_RESULT_TTL': 360},
    'default': {**_redis_config, 'DEFAULT_TIMEOUT': 600,  'DEFAULT_RESULT_TTL': 360},
    'low':     {**_redis_config, 'DEFAULT_TIMEOUT': 3600, 'DEFAULT_RESULT_TTL': 720},
}
RQ_RETRY_MAX_ATTEMPTS = 3
RQ_RETRY_DELAYS = [10, 60, 300]
RQ_WORKER_CLASS = 'rq.SimpleWorker'  # only used if RUN_JOBS_INLINE is False

# When True, jobs run in a daemon thread on the same Django process instead of
# being enqueued to RQ. No worker required, no Redis needed for jobs. Default
# True for dev simplicity. Flip to False in prod (or once Redis on Memorystore
# is wired up) to use a real worker fleet.
RUN_JOBS_INLINE = os.environ.get('RUN_JOBS_INLINE', 'True') == 'True'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/1',
        'OPTIONS': {'socket_connect_timeout': 30, 'socket_timeout': 30, 'retry_on_timeout': True},
        'KEY_PREFIX': 'critter_cache',
        'TIMEOUT': 300,
    }
}

# ----------------------------------------------------------------------
# AI provider keys
# ----------------------------------------------------------------------

GOOGLE_CLOUD_PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT_ID', 'wtroy-test-proj')
GOOGLE_CLOUD_REGION = os.environ.get('GOOGLE_CLOUD_REGION', 'us-central1')
GOOGLE_CLOUD_GEMINI_LOCATION = os.environ.get('GOOGLE_CLOUD_GEMINI_LOCATION', 'us-central1')
# Note: no GEMINI_API_KEY — Gemini Vision and Veo go through Vertex AI with
# the service account credentials (settings.VERTEX_CREDENTIALS), not via the
# public AI Studio endpoint.
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
RUNWAY_API_KEY = os.environ.get('RUNWAY_API_KEY', '')
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY', '')
# Kling uses access key + secret key (HS256 JWT auth). Get them at
# https://klingai.com → Developer Console.
KLING_ACCESS_KEY = os.environ.get('KLING_ACCESS_KEY', '')
KLING_SECRET_KEY = os.environ.get('KLING_SECRET_KEY', '')

# ----------------------------------------------------------------------
# Stripe (Phase 5)
# ----------------------------------------------------------------------

STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
DEFAULT_TRIAL_DAYS = 14

# ----------------------------------------------------------------------
# Analytics
# ----------------------------------------------------------------------

ANALYTICS_SAMPLING_RATE = 1.0
ANALYTICS_LOG_REQUESTS = True

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name}:{lineno} — {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'auth_file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'auth.log',
            'formatter': 'verbose',
        },
        'critter_file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'critter.log',
            'formatter': 'verbose',
        },
        'security_file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'security.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'users': {'handlers': ['console', 'auth_file', 'security_file'], 'level': 'INFO', 'propagate': False},
        'rest_framework_simplejwt': {'handlers': ['console', 'auth_file'], 'level': 'INFO', 'propagate': False},
        'auth_debug': {'handlers': ['console', 'auth_file', 'security_file'], 'level': 'DEBUG', 'propagate': False},
        'generations': {'handlers': ['console', 'critter_file'], 'level': 'INFO', 'propagate': False},
        'providers': {'handlers': ['console', 'critter_file'], 'level': 'INFO', 'propagate': False},
        'subjects': {'handlers': ['console', 'critter_file'], 'level': 'INFO', 'propagate': False},
        'assets': {'handlers': ['console', 'critter_file'], 'level': 'INFO', 'propagate': False},
        '': {'handlers': ['console', 'critter_file'], 'level': 'INFO', 'propagate': False},
        'django': {'handlers': ['console', 'critter_file'], 'level': 'INFO', 'propagate': False},
    },
}
