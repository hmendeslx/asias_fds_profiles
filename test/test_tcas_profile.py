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

import tcas_profile as tcas
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
'''
TCASSensitivityAtTCASRAStart,
VerticalSpeedAtTCASRAStart,
AltitudeQNHAtTCASRAStart,
'''


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
        tcas_vert = M( 'TCAS Vertical Control', 
                              array=np.ma.array([0,0,1,0,0]),
                              values_mapping=values_mapping, frequency=1., offset=0.)
        expected = [ KeyPointValue(index=2, value=1, name='TCAS Vertical Control|B'), 
                              KeyPointValue(index=3, value=0, name='TCAS Vertical Control|A')]
        node = TCASVerticalControl()
        node.derive(tcas_vert)
        self.assertEqual(expected,  node)


class TestTCASSensitivityAtTCASRAStart(unittest.TestCase):
    def test_can_operate(self):
        expected = [('TCAS Sensitivity Level', 'TCAS RA Start')]
        opts =tcas.TCASSensitivityAtTCASRAStart.get_operational_combinations()
        self.assertEqual(opts, expected)
    
    def test_derive(self):
        '''[[[State]]]
          0 = SL = 0 (Automatic)
          1 = SL = 1 (Standby)
          2 = SL = 2 (TA Only)
          3 = SL = 3
          ...
        '''
        values_mapping = {  0: '0',    1: '1', }
        tcas_sens = M( 'TCAS Sensitivity Level', 
                              array=np.ma.array([0,0,1,0,0]),
                              values_mapping=values_mapping, frequency=.25, offset=0.)
        start = KTI( items= [KeyTimeInstance(index=2,   name='TCAS RA Start'),  ] )
        node = tcas.TCASSensitivityAtTCASRAStart()
        node.derive(tcas_sens, start)
        
        expected = [ KeyPointValue(index=2, value=1, name='TCAS RA Start Pilot Sensitivity Mode'), ]
        self.assertEqual(expected,  node)


class TestVerticalSpeedAtTCASRAStart(unittest.TestCase):
    def setUp(self):
        self.klass =tcas.VerticalSpeedAtTCASRAStart
    
    def test_can_operate(self):
        self.assertEqual(self.klass.get_operational_combinations(),[('Vertical Speed', 'TCAS RA Start')])

    def test_derive(self):
        start = KTI( items= [KeyTimeInstance(index=2,   name='TCAS RA Start'),  ] )
        vspd = P( 'Vertical Speed', array=np.ma.arange(10)*10.0, frequency=1., offset=0.)
        expected = [KeyPointValue(index=2, value=20.0, name='TCAS RA Start Vertical Speed'),]

        k = self.klass()
        k.derive(vspd, start)
        self.assertEqual(k, expected)


class TestAltitudeQNHAtTCASRAStart(unittest.TestCase):
    def setUp(self):
        self.klass =tcas.AltitudeQNHAtTCASRAStart
    
    def test_can_operate(self):
        self.assertEqual(self.klass.get_operational_combinations(),[('Altitude QNH', 'TCAS RA Start')])

    def test_derive(self):
        start = KTI( items= [KeyTimeInstance(index=2,   name='TCAS RA Start'),  ] )
        alt = P( 'Altitude QNH', array=np.ma.arange(10)*10.0, frequency=1., offset=0.)
        expected = [KeyPointValue(index=2, value=20.0, name='TCAS RA Start Altitude QNH'),]

        k = self.klass()
        k.derive(alt, start)
        self.assertEqual(k, expected)
        
        
class TestPitchAtTCASRAStart(unittest.TestCase):
    def setUp(self):
        self.klass =tcas.PitchAtTCASRAStart
    
    def test_can_operate(self):
        self.assertEqual(self.klass.get_operational_combinations(),[('Pitch', 'TCAS RA Start')])

    def test_derive(self):
        start = KTI( items= [KeyTimeInstance(index=2,   name='TCAS RA Start'),  ] )
        param = P( 'Pitch', array=np.ma.arange(10)*10.0, frequency=1., offset=0.)
        expected = [KeyPointValue(index=2, value=20.0, name='TCAS RA Start Pitch'),]

        k = self.klass()
        k.derive(param, start)
        self.assertEqual(k, expected)

        
class TestRollAtTCASRAStart(unittest.TestCase):
    def setUp(self):
        self.klass =tcas.RollAtTCASRAStart
    
    def test_can_operate(self):
        self.assertEqual(self.klass.get_operational_combinations(),[('Roll', 'TCAS RA Start')])

    def test_derive(self):
        start = KTI( items= [KeyTimeInstance(index=2,   name='TCAS RA Start'),  ] )
        param = P( 'Roll', array=np.ma.arange(10)*10.0, frequency=1., offset=0.)
        expected = [KeyPointValue(index=2, value=20.0, name='TCAS RA Start Roll Abs'),]

        k = self.klass()
        k.derive(param, start)
        self.assertEqual(k, expected)
        
        
class TestAirspeedAtTCASRAStart(unittest.TestCase):
    def setUp(self):
        self.klass =tcas.AirspeedAtTCASRAStart
    
    def test_can_operate(self):
        self.assertEqual(self.klass.get_operational_combinations(),[('Airspeed', 'TCAS RA Start')])

    def test_derive(self):
        start = KTI( items= [KeyTimeInstance(index=2,   name='TCAS RA Start'),  ] )
        param = P( 'Airspeed', array=np.arange(100,200,10)*1.0, frequency=1., offset=0.)
        expected = [KeyPointValue(index=2, value=120.0, name='TCAS RA Start Airspeed'),]
        k = self.klass()
        k.derive(param, start)
        self.assertEqual(k, expected)


class TestAutopilotAtTCASRAStart(unittest.TestCase):
    def setUp(self):
        self.klass =tcas.AutopilotAtTCASRAStart
    
    def test_can_operate(self):
        self.assertEqual(self.klass.get_operational_combinations(),[('AP Engaged', 'TCAS RA Start')])

    def test_derive(self):
        start = KTI( items= [KeyTimeInstance(index=2,   name='TCAS RA Start'),  ] )
        param = P( 'AP Engaged', array=np.ma.arange(10)*1.0, frequency=1., offset=0.)
        expected = [KeyPointValue(index=2, value=2.0, name='TCAS RA Start Autopilot'),]
        k = self.klass()
        k.derive(param, start)
        self.assertEqual(k, expected)
        

class TestTCASRATimeToAPDisengage(unittest.TestCase):
    def setUp(self):
        self.klass =tcas.TCASRATimeToAPDisengage
    
    def test_can_operate(self):
        self.assertEqual(self.klass.get_operational_combinations(),[('AP Disengaged Selection', 'TCAS RA Sections')])

    def test_derive(self):
        ra_sections = buildsections('TCAS RA Sections', [2,4] )
        ap_dis = KTI( items= [KeyTimeInstance(index=3,   name='AP Disengaged Selection'),       ])
        expected = [KeyPointValue(index=3, value=1.0, name='TCAS RA Time To AP Disengage'),]
        k = self.klass()
        k.derive(ap_dis, ra_sections)
        self.assertEqual(k, expected)
        
        
if __name__=='__main__':
    print 'testing tcas profile'
    try:
        unittest.main()
    except SystemExit as inst: #ignore extraneous error from interactive prompt
        pass
        