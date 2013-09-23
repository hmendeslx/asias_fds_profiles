
def mydiv(x,y):
    return x/y

def test0():
    result = mydiv(2,4)
    assert result==2/4; result

def test1():
    result = mydiv(3,7)
    assert result==3/7; result

def test2():
    result = mydiv(3,0)
    assert result==3.0/0.0; result   
    
def test3():
    result = mydiv(3,7)
    assert result==3./7.; result
    