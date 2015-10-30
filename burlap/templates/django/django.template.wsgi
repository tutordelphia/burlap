import os
import sys

os.environ['DJANGO_SETTINGS_MODULE'] = '{{ django_settings_module }}'
os.environ['CELERY_LOADER'] = 'django'
os.environ['SITE'] = '{{ apache_site }}'
os.environ['ROLE'] = '{{ ROLE }}'

#This is where the python stuff will be deployed
#sys.path.append(os.path.join(os.path.realpath(os.path.dirname(__file__)), '..'))
sys.path.append(os.path.join(os.path.realpath(os.path.dirname(__file__)), '../src'))

import django.core.handlers.wsgi
application=django.core.handlers.wsgi.WSGIHandler()
