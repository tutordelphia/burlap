from __future__ import print_function

import os, sys, shutil

from fabric.api import puts, sudo

def test_deploy():
    """
    Creates a multi-site Apache Django powered web server with a MySQL backend.
    """
    
    # Delete any old tmp files
    PROJECT_DIR = '/tmp/burlap_test'
    if os.path.exists(PROJECT_DIR):
        shutil.rmtree(PROJECT_DIR)
    os.makedirs(PROJECT_DIR)

    # Create our test virtualenv.
    PYTHON_EXE = os.path.split(sys.executable)[-1]
#     os.system('cd {project_dir}; virtualenv -p {python} .env'.format(
#         project_dir=PROJECT_DIR,
#         python=sys.executable,
#     ))
    
    # Symlink burlap.
#     VIRTUALENV_DIR = os.path.join(PROJECT_DIR, '.env')
#     VIRTUALENV_BIN_DIR = os.path.join(PROJECT_DIR, '.env/bin')
#     SITE_PACKAGES = os.path.join(VIRTUALENV_DIR, 'lib/%s/site-packages' % PYTHON_EXE)
    BURLAP_DIR = os.path.abspath('./burlap')
    BURLAP_BIN = os.path.abspath('./bin/burlap')
#     os.system('ln -s %s %s' % (BURLAP_DIR, SITE_PACKAGES))
#     os.system('ln -s %s %s' % (os.path.abspath('./bin/burlap'), VIRTUALENV_BIN_DIR))
    
    # Install dependencies.
#     PYTHON_BIN = os.path.join(VIRTUALENV_DIR, 'bin/python')
#     PIP_BIN = os.path.join(VIRTUALENV_DIR, 'bin/pip')
#     os.system('%s install -r %s' % (PIP_BIN, 'pip-requirements.txt'))
    
    # Initialize project.
#     VIRTUALENV_ACTIVATE = '. %s/bin/activate' % VIRTUALENV_DIR
    kwargs = dict(
#         project_dir=PROJECT_DIR,
#         activate=VIRTUALENV_ACTIVATE,
        burlap_bin=BURLAP_BIN,
    )
    os.system('cd {project_dir}; {burlap} skel multitenant'.format(**kwargs))
    
    # Add production role.
    os.system('cd {project_dir}; {activate}; burlap add-role prod'.format(**kwargs))
    