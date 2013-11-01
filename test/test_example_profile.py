# -*- coding: utf-8 -*-
"""
test_example_profile.py
Created on Fri Nov  1 10:35:56 2013
@author: keithc

start unit testing
"""
import os
import numpy as np
import sys
import unittest
import math
from datetime import datetime

from mock import Mock, call, patch


from analysis_engine.library import align
from analysis_engine.node import (
    A, App, ApproachItem, KPV, KTI, load, M, P, KeyPointValue,
    MappedArray, MultistateDerivedParameterNode,
    KeyTimeInstance, Section, S
)

from example_profile import (
    SimpleAttribute,
    FileAttribute,
    MydictAttribute,
    SimpleKTI,
    SimplerKTI,
)


             
class TestSimpleAttribute(unittest.TestCase):
    def setUp(self):
        self.start_datetime = A('Start Datetime', value=datetime(2012,4,1,1,0,0))
    
    def test_can_operate(self):
        self.assertEqual(SimpleAttribute.get_operational_combinations(),[('Start Datetime',)])

    def test_derive(self):
        sa = SimpleAttribute()
        sa.set_flight_attr = Mock()
        sa.derive(self.start_datetime)
        sa.set_flight_attr.assert_called_once_with('Keith')             


class TestFileAttribute(unittest.TestCase):
    def setUp(self):
        self.myfile = A('Myfile', value="/fake/path")
    
    def test_can_operate(self):
        self.assertEqual(FileAttribute.get_operational_combinations(),[('Myfile',)])

    def test_derive(self):
        fa = FileAttribute()
        fa.set_flight_attr = Mock()
        fa.derive(self.myfile)
        fa.set_flight_attr.assert_called_once_with("/fake/path")             


class TestMydictAttribute(unittest.TestCase):
    def setUp(self):
        self.mydict = A('Mydict', value={}) 
    
    def test_can_operate(self):
        self.assertEqual(MydictAttribute.get_operational_combinations(),[('Mydict',)])

    def test_derive(self):
        da = MydictAttribute()
        da.set_flight_attr = Mock()
        da.derive(self.mydict)
        da.set_flight_attr.assert_called_once_with({'testkey': [1, 2, 3]})             

"""           
class SimpleKTI(KeyTimeInstanceNode):
    '''a simple KTI. start_datetime is used only to provide a dependency'''
    def derive(self, start_datetime=A('Start Datetime')):
        #print 'in SimpleKTI'
        self.create_kti(3)      

class SimplerKTI(KeyTimeInstanceNode):
    '''manually built KTI. start_datetime is used only to provide a dependency'''
    def derive(self, start_datetime=A('Start Datetime')):
        #print 'in SimpleKTI'
        kti=KeyTimeInstance(index=700., name='My Simpler KTI') #freq=1hz and offset=0 by default
        self.append( kti )
"""
class TestSimpleKTI(unittest.TestCase):
    def setUp(self):
        self.start_datetime = A('Start Datetime', value=datetime(2012,4,1,1,0,0))
    
    def test_can_operate(self):
        self.assertEqual(SimpleKTI.get_operational_combinations(),[('Start Datetime',)])

    def test_derive(self):
        k = SimpleKTI()
        k.derive(self.start_datetime )
        expected = [KeyTimeInstance(index=3, name='Simple KTI')]
        self.assertEqual(k, expected)

class TestSimplerKTI(unittest.TestCase):
    def setUp(self):
        self.start_datetime = A('Start Datetime', value=datetime(2012,4,1,1,0,0))
    
    def test_can_operate(self):
        self.assertEqual(SimpleKTI.get_operational_combinations(),[('Start Datetime',)])

    def test_derive(self):
        k = SimplerKTI()
        k.derive(self.start_datetime )
        expected = [KeyTimeInstance(index=700., name='My Simpler KTI')]
        self.assertEqual(k, expected)
        
if __name__=='__main__':
    print 'hi'
    try:
        unittest.main()
    except SystemExit as inst: #ignore extraneous error from interactive prompt
        pass
        