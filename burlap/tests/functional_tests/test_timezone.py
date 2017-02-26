
import pytest

def test_timezone():
    from burlap.host import TimezoneSatchel
    
    ts = TimezoneSatchel()
    
    current_tz = ts.get_current_timezone()
    assert current_tz == 'UTC'
    
    ts.env.timezone = 'EST'
    ts.configure()
    
    current_tz = ts.get_current_timezone()
    assert current_tz == 'EST'
