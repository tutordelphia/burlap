import pytest


pytestmark = pytest.mark.network


@pytest.fixture(scope='module')
def firewall():
    from burlap.require.shorewall import firewall
    import burlap.shorewall
    firewall(
        rules=[
            burlap.shorewall.Ping(),
            burlap.shorewall.SSH(),
            burlap.shorewall.HTTP(),
            burlap.shorewall.HTTPS(),
            burlap.shorewall.SMTP(),
            burlap.shorewall.rule(
                port=1234,
                source=burlap.shorewall.hosts(['example.com']),
            ),
        ]
    )


def test_require_firewall_started(firewall):
    from burlap.require.shorewall import started
    from burlap.shorewall import is_started
    started()
    assert is_started()


def test_require_firewall_stopped(firewall):
    from burlap.require.shorewall import stopped
    from burlap.shorewall import is_stopped
    stopped()
    assert is_stopped()
