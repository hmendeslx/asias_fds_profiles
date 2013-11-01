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
        self.myfile = A('Myfile', value="/fake/path")
    
    def test_can_operate(self):
        self.assertEqual(FileAttribute.get_operational_combinations(),[('Myfile',)])

    def test_derive(self):
        fa = FileAttribute()
        fa.set_flight_attr = Mock()
        fa.derive(self.myfile)
        fa.set_flight_attr.assert_called_once_with("/fake/path")             

"""
class MydictAttribute(FlightAttributeNode):
    '''a simple FlightAttribute. tests availability of Filename'''
    #name = 'FDR Analysis Datetime'
    def derive(self, mydict=A('Mydict')):
        mydict.value['testkey'] = [1,2,3]
        self.set_flight_attr(mydict)
"""
        
if __name__=='__main__':
    print 'hi'
    try:
        unittest.main()
    except SystemExit as inst: #ignore extraneous error from interactive prompt
        pass
        