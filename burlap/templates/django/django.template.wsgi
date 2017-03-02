import os
import sys

os.environ['DJANGO_SETTINGS_MODULE'] = '{{ django_settings_module }}'
os.environ['CELERY_LOADER'] = 'django'
os.environ['SITE'] = '{{ SITE }}'
os.environ['ROLE'] = '{{ ROLE }}'

#This is where the python stuff will be deployed
#sys.path.append(os.path.join(os.path.realpath(os.path.dirname(__file__)), '..'))
sys.path.append(os.path.join(os.path.realpath(os.path.dirname(__file__)), '../src'))

# For django.VERSION < (1, 7)
import django.core.handlers.wsgi
application=django.core.handlers.wsgi.WSGIHandler()

# # For django.VERSION >= (1, 7)
#from django.core.wsgi import get_wsgi_application
#application = get_wsgi_application()
