# -*- coding: utf-8 -*-
"""
test_tca_profile.py
Created  2013 Nov 4
@author: keithc

start unit testing
"""
import numpy as np
import unittest
from datetime import datetime

from mock import Mock, call, patch

from analysis_engine.library import align
from analysis_engine.node import (
    A, App, ApproachItem, KPV, KTI, load, M, P, KeyPointValue,
    MappedArray, MultistateDerivedParameterNode, SectionNode,
    KeyTimeInstance, Section, S
)

from tcas_profile import (
    TCASCtlSections,
    TCASRAStart,
    TCASRASections,    
    
    TCASAltitudeExceedance,
    TCASRAStandardResponse,
    TCASCombinedControl,
    
    TCASUpAdvisory,
    TCASDownAdvisory,
    TCASVerticalControl,
)

### fixtures
_ra  =np.ma.hstack( [np.ma.zeros(16), np.ma.ones(4), np.ma.zeros(16)] )
ra  = P('TCAS RA', _ra, frequency=1.0, offset=0.0)
off = KTI( items= [KeyTimeInstance(index=2,   name='Liftoff'),           ] )
td  = KTI( items= [KeyTimeInstance(index=34, name='Touchdown'),  ] )
tcas_ra_sections = TCASRASections()
tcas_ra_sections.derive(ra, off, td)

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
tcas_ctl = M( 'TCAS Combined Control', array=np.ma.array([0,1,2,3,4,5,4,5,6]),
                     values_mapping=values_mapping, frequency=1., offset=0.,)


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
       

class TestTCASRASections(unittest.TestCase):
    def setUp(self):
        pass
    
    def test_can_operate(self):
        expected = [('TCAS RA','Liftoff','Touchdown')]
        opts = TCASRASections.get_operational_combinations()
        self.assertEqual(opts, expected)        
    
    def test_derive(self):
        node = TCASRASections()
        node.derive(ra, off, td)
        expected = buildsection( 'TCAS RA Sections', 16., 20.)         
        self.assertEqual(expected.get_slices(),  node.get_slices())
    

class TestTCASRAStart(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS RA Sections',)]
        opts = TCASRAStart.get_operational_combinations()
        self.assertEqual(opts, expected)        

    def test_derive(self):
        expected = KTI( items= [KeyTimeInstance(index=16.,   name='TCAS RA Start'),  ] )
        node =  TCASRAStart()
        node.derive(tcas_ra_sections)          
        self.assertEqual(expected,  node)


class TestTCASCtlSections(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS Combined Control',)]
        opts = TCASCtlSections.get_operational_combinations()
        self.assertEqual(opts, expected)        

    def test_derive(self):
        #[0,1,2,3,4,5,4,5,6]
        expected = buildsection('TCAS Ctl Sections', 2, 8)
        node =  TCASCtlSections()
        node.derive(tcas_ctl)          
        print 'expected', expected.get_slices()
        print 'node', node.get_slices()
        self.assertEqual(expected,  node)


class TestTCASAltitudeExceedance(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS RA Sections','TCAS Combined Control',
                             'TCAS Up Advisory','TCAS Down Advisory',
                             'TCAS RA Standard Response','Vertical Speed')]
        opts = TCASAltitudeExceedance.get_operational_combinations()
        self.assertEqual(opts, expected)        
    
    def test_derive(self):
        ###TODO
        pass
    

class TestTCASRAStandardResponse(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS Combined Control', 'TCAS Up Advisory','TCAS Down Advisory',
                              'TCAS Vertical Control', 'Vertical Speed',
                             'TCAS RA Sections', 'TCAS RA Warning Duration')]
        opts = TCASRAStandardResponse.get_operational_combinations()
        self.assertEqual(opts, expected)        
    
    def test_derive(self):
        ###TODO
        pass
    

class TestTCASCombinedControl(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS Combined Control',)] 
        opts = TCASCombinedControl.get_operational_combinations()
        self.assertEqual(opts, expected)        
    
    def test_derive(self):
        #4: 'Up Advisory Corrective',
        tcas_ctl = M( 'TCAS Combined Control', 
                              array=np.ma.array([0,0,4,0,0]),
                              values_mapping=values_mapping, frequency=1., offset=0.)
        expected = [ KeyPointValue(index=2, value=4, name='TCAS Combined Control|Up Advisory Corrective'), 
                           ]
        node = TCASCombinedControl()
        node.derive(tcas_ctl) 
        self.assertEqual(expected,  node)


class TestTCASUpAdvisory(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS Up Advisory', )]
        opts = TCASUpAdvisory.get_operational_combinations()
        self.assertEqual(opts, expected)        
    
    def test_derive(self):
        #4: 'Up Advisory Corrective',
        tcas_up = M( 'TCASUpAdvisory', 
                              array=np.ma.array([0,0,1,0,0]),
                              values_mapping=values_mapping, frequency=1., offset=0.)
        expected = [ KeyPointValue(index=2, value=1, name='TCAS Up Advisory|B'), 
                              KeyPointValue(index=3, value=0, name='TCAS Up Advisory|A')]
        node = TCASUpAdvisory()
        node.derive(tcas_up)
        self.assertEqual(expected,  node)

    
class TestTCASDownAdvisory(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS Down Advisory', )]
        opts = TCASDownAdvisory.get_operational_combinations()
        self.assertEqual(opts, expected)        
    
    def test_derive(self):
        #4: 'Up Advisory Corrective',
        tcas_down = M( 'TCASDownAdvisory', 
                              array=np.ma.array([0,0,1,0,0]),
                              values_mapping=values_mapping, frequency=1., offset=0.)
        expected = [ KeyPointValue(index=2, value=1, name='TCAS Down Advisory|B'), 
                              KeyPointValue(index=3, value=0, name='TCAS Down Advisory|A')]
        node = TCASDownAdvisory()
        node.derive(tcas_down)
        self.assertEqual(expected,  node)

    
    
class TestTCASVerticalControl(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS Vertical Control', )]
        opts = TCASVerticalControl.get_operational_combinations()
        self.assertEqual(opts, expected)        
    
    def test_derive(self):
        #4: 'Up Advisory Corrective',
        tcas_vert = M( 'TCAS Vertical Control', 
                              array=np.ma.array([0,0,1,0,0]),
                              values_mapping=values_mapping, frequency=1., offset=0.)
        expected = [ KeyPointValue(index=2, value=1, name='TCAS Vertical Control|B'), 
                              KeyPointValue(index=3, value=0, name='TCAS Vertical Control|A')]
        node = TCASVerticalControl()
        node.derive(tcas_vert)
        self.assertEqual(expected,  node)


        
if __name__=='__main__':
    print 'testing tcas profile'
    try:
        unittest.main()
    except SystemExit as inst: #ignore extraneous error from interactive prompt
        pass
        