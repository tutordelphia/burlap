import pytest

from fabric.api import run

from burlap.utils import run_as_root


pytestmark = pytest.mark.network


@pytest.fixture(scope='module', autouse=True)
def check_for_debian_family():
    from burlap.system import distrib_family
    if distrib_family() != 'debian':
        pytest.skip("Skipping apt-key test on non-Debian distrib")


def test_add_apt_key_with_key_id_from_url():
    from burlap.deb import add_apt_key
    try:
        add_apt_key(keyid='C4DEFFEB', url='http://repo.varnish-cache.org/debian/GPG-key.txt')
        run_as_root('apt-key finger | grep -q C4DEFFEB')
    finally:
        run_as_root('apt-key del C4DEFFEB', quiet=True)


def test_add_apt_key_with_key_id_from_specific_key_server():
    from burlap.deb import add_apt_key
    try:
        add_apt_key(keyid='7BD9BF62', keyserver='keyserver.ubuntu.com')
        run_as_root('apt-key finger | grep -q 7BD9BF62')
    finally:
        run_as_root('apt-key del 7BD9BF62', quiet=True)


def test_add_apt_key_with_key_id_from_file():
    from burlap.deb import add_apt_key
    try:
        run('wget http://repo.varnish-cache.org/debian/GPG-key.txt -O /tmp/tmp.burlap.test.key')
        add_apt_key(keyid='C4DEFFEB', filename='/tmp/tmp.burlap.test.key')
        run_as_root('apt-key finger | grep -q C4DEFFEB')
    finally:
        run_as_root('apt-key del C4DEFFEB', quiet=True)


def test_add_apt_key_without_key_id_from_url():
    from burlap.deb import add_apt_key
    try:
        add_apt_key(url='http://repo.varnish-cache.org/debian/GPG-key.txt')
        run_as_root('apt-key finger | grep -q C4DEFFEB')
    finally:
        run_as_root('apt-key del C4DEFFEB', quiet=True)


def test_add_apt_key_without_key_id_from_file():
    from burlap.deb import add_apt_key
    try:
        run('wget http://repo.varnish-cache.org/debian/GPG-key.txt -O /tmp/tmp.burlap.test.key')
        add_apt_key(filename='/tmp/tmp.burlap.test.key')
        run_as_root('apt-key finger | grep -q C4DEFFEB')
    finally:
        run_as_root('apt-key del C4DEFFEB', quiet=True)


def test_require_deb_key_from_url():
    from burlap.require.deb import key as require_key
    try:
        require_key(keyid='C4DEFFEB', url='http://repo.varnish-cache.org/debian/GPG-key.txt')
        run_as_root('apt-key finger | grep -q C4DEFFEB')
    finally:
        run_as_root('apt-key del C4DEFFEB', quiet=True)


def test_require_deb_key_from_specific_keyserver():
    from burlap.require.deb import key as require_key
    try:
        require_key(keyid='7BD9BF62', keyserver='keyserver.ubuntu.com')
        run_as_root('apt-key finger | grep -q 7BD9BF62')
    finally:
        run_as_root('apt-key del 7BD9BF62', quiet=True)


def test_require_deb_key_from_file():
    from burlap.require.deb import key as require_key
    try:
        run('wget http://repo.varnish-cache.org/debian/GPG-key.txt -O /tmp/tmp.burlap.test.key')
        require_key(keyid='C4DEFFEB', filename='/tmp/tmp.burlap.test.key')
        run_as_root('apt-key finger | grep -q C4DEFFEB')
    finally:
        run_as_root('apt-key del C4DEFFEB', quiet=True)
