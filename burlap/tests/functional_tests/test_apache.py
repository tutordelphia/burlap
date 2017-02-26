# from pipes import quote
# from textwrap import dedent
# import posixpath
# 
# import pytest
# 
# from fabric.api import quiet, run, shell_env, sudo
# 
# from burlap.files import is_link
# from burlap.system import distrib_family
# 
# def test_apache():
#     from burlap.project import Project
#     project = Project(name='test_apache', base_dir='/tmp')
#     project.init()
#     project.add_role('prod')
#     project.roles.prod.add_service('apache')
#     project.deploy()
