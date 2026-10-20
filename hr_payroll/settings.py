"""
Django settings for hr_payroll project.
"""

import os
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

DEBUG = os.environ.get('DEBUG', '') == 'True'

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-pvtx-a7-_+*1kz%yr5(@2wxv(f^t0b_h4n-q87ye+9&j9qb+bm'
    else:
        raise ImproperlyConfigured(
            'The SECRET_KEY environment variable must be set in production. '
            'Generate one with: python -c "from django.core.management.utils '
            'import get_random_secret_key; print(get_random_secret_key())"')

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get(
        'ALLOWED_HOSTS',
        'corecloud.vercel.app,corecloud-banday.vercel.app,'
        'hr-payroll-system-one.vercel.app,.vercel.app,localhost,127.0.0.1'
    ).split(',') if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    'https://corecloud.vercel.app',
    'https://corecloud-banday.vercel.app',
    'https://hr-payroll-system-one.vercel.app',
    'https://corecloud-git-main-banday.vercel.app',
]
CSRF_TRUSTED_ORIGINS += [
    o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if o.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'employees',
    'payroll',
    'attendance',
    'leaves',
    'hr_modules',
    'collab',
    'soc',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hr_payroll.urls'

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
                'hr_payroll.context_processors.role_context',
                'hr_payroll.context_processors.login_slides',
            ],
        },
    },
]

WSGI_APPLICATION = 'hr_payroll.wsgi.application'

DATABASES = {}
if os.environ.get('DATABASE_URL'):
    import dj_database_url
    DATABASES['default'] = dj_database_url.parse(
        os.environ['DATABASE_URL'], conn_max_age=600)
elif os.environ.get('DB_HOST'):
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'neondb'),
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ['DB_HOST'],
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'sslmode': 'require',
        },
    }
else:
    raise ImproperlyConfigured(
        'Database not configured: set DATABASE_URL (preferred) or the '
        'DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT environment variables.')

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.StaticFilesStorage'},
}

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 3600
SESSION_COOKIE_HTTPONLY = True

# Security headers. On Vercel TLS terminates at the edge, so Django must
# trust X-Forwarded-Proto to know the original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if os.environ.get('VERCEL') and not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

AUTHENTICATION_BACKENDS = [
    'hr_payroll.backends.AuthorizedUserBackend',
    'django.contrib.auth.backends.ModelBackend',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if os.environ.get('EMAIL_HOST') and os.environ.get('EMAIL_HOST_USER'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ['EMAIL_HOST']
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.environ['EMAIL_HOST_USER']
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False') == 'True'
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# SOC: automated response playbooks (lock account, revoke sessions, open
# ticket) fire on critical alerts when enabled.
SOC_AUTO_RESPONSE = os.environ.get('SOC_AUTO_RESPONSE', 'True') == 'True'
# Secret required by the /cron/soc/ endpoint (Vercel cron).
SOC_CRON_SECRET = os.environ.get('SOC_CRON_SECRET', '')

# File logging: on Vercel serverless only /tmp is writable, so the activity
# log must live there; locally it stays next to the project root.
if os.environ.get('VERCEL'):
    _ACTIVITY_LOG = Path(tempfile.gettempdir()) / 'activity.log'
else:
    _ACTIVITY_LOG = BASE_DIR / 'activity.log'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': _ACTIVITY_LOG,
            'maxBytes': 1024 * 1024,
            'backupCount': 3,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'employees': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'soc': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
