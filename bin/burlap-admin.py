#!/usr/bin/env python
"""
Command line tool for initializing Burlap-structured Django projects.

e.g.

    burlap skel --name=myproject
"""
from __future__ import print_function

import argparse
import os
import sys
import re

_path = os.path.normpath(os.path.join(os.path.realpath(__file__), '../..'))
sys.path.insert(0, _path)

import burlap # pylint: disable=wrong-import-position
from burlap import common # pylint: disable=wrong-import-position

fabfile_template = os.path.join(
    os.path.dirname(burlap.__file__),
    'templates',
    'burlap',
    'fabfile.py.template',
)

ACTIONS = (
    SKEL,
    ADD_ROLE,
    CREATE_SATCHEL,
) = (
    'skel',
    'add-role',
    'create-satchel',
)

def md(d):
    if os.path.isdir(d):
        return
    os.makedirs(d)

def to_camelcase(value):
    value = re.sub(r'[^a-zA-Z0-9]+', ' ', value).strip()
    return ''.join(x.capitalize() for x in value.split(' '))

def init_django(args, virtualenv='.env'):
    
    site_name = args.project_name
    
    print('Initializing Django project...')
    if not os.path.isdir('src/%s' % site_name):
        print('Initializing base django project...')
        os.system('. %s/bin/activate; django-admin.py startproject %s src; deactivate' \
            % (virtualenv, site_name,))
        _settings_fn = 'src/%s_site/settings.py' % args.project_name
        _content = open(_settings_fn, 'r').read()
        _sites = '''SITE_{name_upper} = "{name_lower}"
    SITES = (
    SITE_{name_upper},
    )
    '''.format(
            name_upper=args.project_name.upper(),
            name_lower=args.project_name.lower(),
        )
        _top = []
        for _role in default_roles:
            _top.append("ROLE_%s = '%s'" % (_role.upper(), _role.lower()))
        _top.append('ROLES = (')
        for _role in default_roles:
            _top.append("    ROLE_%s," % (_role.upper(),))
        _top.append(')')
        _index = _content.find('"""\n\n')+4
        _bottom = '''
PROJECT_DIR = os.path.abspath(os.path.join(os.path.split(__file__)[0], '..', '..'))

STATIC_ROOT = os.path.join(PROJECT_DIR, 'static')

MEDIA_ROOT = os.path.join(PROJECT_DIR, 'media')
MEDIA_URL = '/media/'

STATICFILES_FINDERS = (
'django.contrib.staticfiles.finders.FileSystemFinder',
'django.contrib.staticfiles.finders.AppDirectoriesFinder',
)
TEMPLATE_LOADERS = (
'django.template.loaders.filesystem.Loader',
'django.template.loaders.app_directories.Loader',
)
TEMPLATE_DIRS = (
'%s/src/{app_name}/templates' % PROJECT_DIR
)
ADMIN_TITLE = '{app_name_title}'
ADMIN_TITLE_SIMPLE = '{app_name_simple}'
'''.format(
    app_name=args.project_name,
    app_name_title=args.project_name.title() + ' Administration',
    app_name_simple=args.project_name.title())
        open(_settings_fn, 'w').write(_content[:_index]+_sites+('\n'.join(_top))+_content[_index:]+_bottom)
    
    print('Creating Django helper scripts...')
    open('src/manage', 'w').write('''#!/bin/bash
# Helper script for ensuring we use the Python binary in our local
# virtual environment when calling management commands.
# Otherwise, we'd have to always run `. ../.env/bin/activate`, which can be
# annoying.
# Be sue to run `fab <role> pip.init` first in order to setup
# the target role's Python virtual environment.
DIR=`dirname $0`;
cd $DIR;
../.env/bin/python manage.py $@''')
    open('src/runserver', 'w').write('''#!/bin/bash
# Helper script for running the local dev server, ensuring
# our virtual environment is used.
#set -e
#script_dir=`dirname $0`
#cd $script_dir
if [ -z "$PORT" ]; then
export PORT=8111
fi
if [ -z "$ROLE" ]; then
export ROLE=dev
fi
. ~/.bash_aliases
./manage runserver localhost:$PORT''')
    open('src/shell', 'w').write(r'''#!/bin/bash
# Creates a local PIP-aware shell.
#set -e
if [ $_ == $0 ]
then
echo "Please source this script. Do not execute."
exit 1
fi
#script_dir=`dirname $0`
#cd $script_dir
. .env/bin/activate
PS1="\u@\h:\W(fab)\$ "''')

    md('media')
    md('static')
    
    os.system('chmod +x src/shell')
    os.system('chmod +x src/manage')
    os.system('chmod +x src/runserver')

    # Create the primary app for containing models/urls/views.
    if not os.path.isdir('src/%s' % args.project_name):
        os.system('cd src; ./manage startapp %s' % (args.project_name,))
        
    os.system('cd src; ./manage syncdb')

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(
        description=('Initialize and manage a Burlap structured project.'),
    )
    parser.add_argument(
        '-v', '--version',
        help='Show version.',
        action='version',
        version=burlap.__version__,
    )   
    subparsers = parser.add_subparsers(
        dest='action',
    )
    
    skel_parser = subparsers.add_parser(
        SKEL,
        help='Creates a skeleton project.')
    skel_parser.add_argument(
        'project_name',
        type=str,
        help='project name')
    skel_parser.add_argument(
        '--pip-requirements',
        type=str,
        default='Fabric',
        help='The default Python packages to install.')
    skel_parser.add_argument(
        '--virtualenv-dir',
        type=str,
        default='.env',
        help='The default virtualenv directory.')
    skel_parser.add_argument(
        '--roles',
        type=str,
        default='',#dev,prod',
        help='The default roles to populate.')
    skel_parser.add_argument(
        '--components',
        type=str,
        default='',
        help='The default components to enable (e.g. django).')
        
    add_role_parser = subparsers.add_parser(
        ADD_ROLE,
        help='Adds a new role to the project.')
    add_role_parser.add_argument(
        'roles', metavar='roles', type=str, nargs='+',
        help='Names of roles to add.')
                   
    create_satchel_parser = subparsers.add_parser(
        CREATE_SATCHEL,
        help='Adds a new role to the project.')
    create_satchel_parser.add_argument(
        'name', type=str,
        help='Names of the satchel to create.')
        
    args = parser.parse_args()

    if args.action == SKEL:
        assert args.project_name, 'Specify project name.'
        site_name = args.project_name
        
        app_name = args.project_name + '_site'
        
        default_roles = [_ for _ in args.roles.split(',') if _.strip()]
        default_components = [_.strip().lower() for _ in args.components.split(',') if _.strip()]
        
        print('Creating folders...')
        md('roles/all')
        for _role in default_roles:
            md('roles/%s' % _role)
        md('src')
        
        print('Creating roles...')
        open('roles/all/settings.yaml', 'w').write(
            common.render_to_string(
                'burlap/all_settings.yaml.template',
                extra=dict(project_name=args.project_name, site_name=site_name, app_name=app_name)))
        for _role in default_roles:
            open('roles/%s/settings.yaml' % _role, 'w').write(
                common.render_to_string(
                    'burlap/role_settings.yaml.template',
                    extra=dict(project_name=args.project_name, site_name=site_name, role=_role)))
        
        default_packages = args.pip_requirements.split(',')
        if default_packages:
            open('roles/all/pip-requirements.txt', 'w').write('\n'.join(default_packages))
            
        open('roles/all/apt-requirements.txt', 'w').write('')
        
        content = open(fabfile_template, 'r').read()
        content = content.format(project_name=args.project_name)
        open('fabfile.py', 'w').write(content)
        
        print('Initializing local development virtual environment...')
        os.system('virtualenv --no-site-packages %s' % args.virtualenv_dir)
        for package in default_packages:
            os.system('. %s/bin/activate; pip install %s; deactivate' % (args.virtualenv_dir, package))

        # Install burlap dependencies.
        burlap_pip_requirements = os.path.join(os.path.dirname(burlap.__file__), '../requirements.txt')
        print('burlap_pip_requirements:', burlap_pip_requirements)
        assert os.path.exists(burlap_pip_requirements)
        for package in open(burlap_pip_requirements, 'r').readlines():
            if not package.strip():
                continue
            cmd = '%s/bin/pip install %s' % (args.virtualenv_dir, package)
            print('cmd:', cmd)
            assert not os.system(cmd)

        open('setup.bash', 'w').write(common.render_to_string('burlap/setup.bash.template'))
        
        os.system('chmod +x shell')
        
        open('.gitignore', 'w').write(common.render_to_string('burlap/gitignore.template'))
        
        for component in default_components:
            globals()['init_%s' % component](args)
        
        print('='*80)
        print()
        print('Skeleton created for project %s!' % (args.project_name.title(),))
        print()

    elif args.action == ADD_ROLE:
        
        for role in args.roles:
            _role = role.strip().lower()
            fn = 'roles/%s/settings.yaml' % _role
            if os.path.isfile(fn):
                continue
            fn_dir = os.path.split(fn)[0]
            if not os.path.isdir(fn_dir):
                os.makedirs(fn_dir)
            open(fn, 'w').write(
                common.render_to_string(
                    'burlap/role_settings.yaml.template',
                    extra=dict(role=_role)))
            print('Added role %s!' % role)
    
    elif args.action == CREATE_SATCHEL:
        
        name_simple = re.sub(r'[^a-z0-9]+', '', args.name.lower())
        content = common.render_to_string(
            'burlap/satchel.py.template',
            extra=dict(
                name_camelcase=to_camelcase(args.name),
                name_simple=name_simple,
            ))
        if not os.path.isdir('satchels'):
            os.makedirs('satchels')
            os.system('touch satchels/__init__.py')
        satchel_fn = 'satchels/%s.py' % name_simple
        open(satchel_fn, 'w').write(content.strip()+'\n')
        print('Wrote %s.' % satchel_fn)
    
    else:
        raise NotImplementedError, 'Unknown action: %s' % (args.action)
        