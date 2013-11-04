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
    MappedArray, MultistateDerivedParameterNode, SectionNode,
    KeyTimeInstance, Section, S
)

from example_profile import (
    SimpleAttribute,
    FileAttribute,
    MydictAttribute,
    SimpleKTI,
    SimplerKTI,
    SimpleKPV,
    SimplerKPV,
    TCASRAStart,
)


def buildsection(name, begin, end):
    '''from FlightDataAnalyzer tests
       A little routine to make building Sections for testing easier.
       Example: land = buildsection('Landing', 100, 120)
    '''
    result = Section(name, slice(begin, end, None), begin, end)
    return SectionNode(name, items=[result])


def buildsections(*args):
    '''from FlightDataAnalyzer tests
       Example: approach = buildsections('Approach', [80,90], [100,110])
    '''
    built_list=[]
    name = args[0]
    for a in args[1:]:
        begin,end=a[0],a[1]
        new_section = Section(name, slice(begin, end, None), begin, end)
        built_list.append(new_section)
    return SectionNode(name, items=built_list)
       
       
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
        self.assertEqual(SimplerKTI.get_operational_combinations(),[('Start Datetime',)])

    def test_derive(self):
        k = SimplerKTI()
        k.derive(self.start_datetime )
        expected = [KeyTimeInstance(index=700., name='My Simpler KTI')]
        self.assertEqual(k, expected)


class TestSimpleKPV(unittest.TestCase):
    def setUp(self):
        self.start_datetime = A('Start Datetime', value=datetime(2012,4,1,1,0,0))
    
    def test_can_operate(self):
        self.assertEqual(SimpleKPV.get_operational_combinations(),[('Start Datetime',)])

    def test_derive(self):
        k = SimpleKPV()
        k.derive(self.start_datetime )
        expected = [KeyPointValue(index=3.0, value=999.9, name='Simple KPV')]
        self.assertEqual(k, expected)


class TestSimplerKPV(unittest.TestCase):
    def setUp(self):
        self.start_datetime = A('Start Datetime', value=datetime(2012,4,1,1,0,0))
    
    def test_can_operate(self):
        self.assertEqual(SimplerKPV.get_operational_combinations(),[('Start Datetime',)])

    def test_derive(self):
        k = SimplerKPV()
        k.derive(self.start_datetime )
        expected = [KeyPointValue(index=42.5, value=666.6, name='My Simpler KPV'),
                            KeyPointValue(index=42.5, value=666.6, name='My Simpler KPV 2'),
                            ]
        self.assertEqual(k, expected)


class TestTCASRAStart(unittest.TestCase):
    def setUp(self):
        pass
    
    def test_can_operate(self):
        expected = [('TCAS Combined Control', 'Airborne')]
        opts = TCASRAStart.get_operational_combinations()
        self.assertEqual(opts, expected)        

    def test_derive(self):
        #based on FDS TestTCASRAWarningDuration()
        values_mapping = {
            0: 'A',
            1: 'B',
            2: 'Drop Track',
            3: 'Altitude Lost',
            4: 'Up Advisory Corrective',
            5: 'Down Advisory Corrective',
            6: 'G',
        }
        tcas = M( 'TCAS Combined Control', array=np.ma.array([0,1,2,3,4,5,4,5,6]),
                       values_mapping=values_mapping, frequency=1, offset=0,)
        #                                                                                       _,_, a,a,a,a,a,a,_  
        #                                                                                                   u,d,u,d
        #                                                                                                3.5 4.5 5.5 
        airborne = buildsection('Airborne', 2, 7)
        node = TCASRAStart()
        node.derive(tcas, airborne)  # create_ktis_on_state_change() offsets times by 0.5
        expected = [KeyTimeInstance(index=3.5, name='TCAS RA Start'), ]
        self.assertEqual(expected,  node)
        
"""
class TCASRAStart(KeyTimeInstanceNode):
    '''Time of up or down advisory'''
    name = 'TCAS RA Start'

    def derive(self, tcas=M('TCAS Combined Control'), air=S('Airborne')):
        #print 'in TCASRAStart'
        self.create_ktis_on_state_change(
                    'Up Advisory Corrective',
                    tcas.array,
                    change='entering',
                    phase=air
                )                           
        self.create_ktis_on_state_change(
                    'Down Advisory Corrective',
                    tcas.array,
                    change='entering',
                    phase=air
                )                           
        return            
"""
        
if __name__=='__main__':
    print 'hi'
    try:
        unittest.main()
    except SystemExit as inst: #ignore extraneous error from interactive prompt
        pass
        