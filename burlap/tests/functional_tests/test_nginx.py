# import pytest
# 
# 
# pytestmark = pytest.mark.network
# 
# 
# def test_require_nginx_server():
#     try:
#         from burlap.require.nginx import server
#         server()
#     finally:
#         uninstall_nginx()
# 
# 
# @pytest.yield_fixture
# def nginx_server():
#     from burlap.require.nginx import server
#     server()
#     yield
#     uninstall_nginx()
# 
# 
# def uninstall_nginx():
#     from burlap.system import distrib_family
#     family = distrib_family()
#     if family == 'debian':
#         from burlap.require.deb import nopackage
#         nopackage('nginx')
# 
# 
# def test_site_disabled(nginx_server):
# 
#     from burlap.require.nginx import disabled as require_nginx_site_disabled
#     from burlap.files import is_link
# 
#     require_nginx_site_disabled('default')
#     assert not is_link('/etc/nginx/sites-enabled/default')
# 
# 
# def test_site_enabled(nginx_server):
# 
#     from burlap.require.nginx import enabled as require_nginx_site_enabled
#     from burlap.files import is_link
# 
#     require_nginx_site_enabled('default')
#     assert is_link('/etc/nginx/sites-enabled/default')
