from .settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'mapaction_test',  # Test database name
        'USER': 'postgres',        # Default PostgreSQL superuser
        'PASSWORD': 'postgres',    # Default PostgreSQL password
        'HOST': 'localhost',       # Use localhost for local development
        'PORT': '5432',
    }
}