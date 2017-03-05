from burlap.host import TimezoneSatchel

def test_timezone():    
    ts = TimezoneSatchel()
    ts.verbose = True
    
    current_tz0 = ts.get_current_timezone()
    assert current_tz0 == 'UTC'
    
    ts.env.timezone = 'EST'
    ts.configure()
    
    current_tz = ts.get_current_timezone()
    assert current_tz == 'EST'

    ts.env.timezone = current_tz0
    ts.configure()
