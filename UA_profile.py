# -*- coding: utf-8 -*-
"""
Example profile module: defines a set of measures that run against Analyzer base data.
@author: SRANSOHOFF, MAY 2013

   
      save comments only to job records, not flight records.
"""
### Section 1: dependencies (see FlightDataAnalyzer source files for additional options)
import os, glob
import numpy as np
from analysis_engine.node import ( A,   FlightAttributeNode,               # one of these per flight. mostly arrival and departure stuff
                                   App, ApproachNode,                      # per approach
                                   P,   DerivedParameterNode,              # time series with continuous values 
                                   M,   MultistateDerivedParameterNode,    # time series with discrete values
                                   KTI, KeyTimeInstanceNode,               # a list of time points meeting some criteria
                                   KPV, KeyPointValueNode,                 # a list of measures meeting some criteria; multiples are allowed and common 
                                   S,   SectionNode,  FlightPhaseNode      # Sections=Phases
                                 )
# A Node is a list of items.  Each item type is a class with the fields listed below:
#   FlightAttribute = name, value.  could be a scolor or a collection, e.g. list or dict
#   ApproachItem    = recordtype('ApproachItem',    'type slice airport runway gs_est loc_est ils_freq turnoff lowest_lat lowest_lon lowest_hdg', default=None)  
#   KeyTimeInstance = recordtype('KeyTimeInstance', 'index name datetime latitude longitude', default=None)
#   Section = namedtuple('Section',                  'name slice start_edge stop_edge')   #=Phase
#   KeyPointValue   = recordtype('KeyPointValue', '  index value name slice datetime latitude longitude', field_defaults={'slice':slice(None)}, default=None)
                            
from analysis_engine.library import (integrate, repair_mask, index_at_value, all_of, any_of, max_value, min_value,np_ma_masked_zeros_like, value_at_index,
                                     is_index_within_slice)
# asias_fds stuff
import analyser_custom_settings as settings
import staged_helper  as helper 
import fds_oracle
from flightdatautilities.velocity_speed import get_vspeed_map, VelocitySpeed
from flightdatautilities.model_information import (get_conf_map,
                                                   get_flap_map,
                                                   get_slat_map)

   
### Section 2: measure definitions -- attributes, KTI, phase/section, KPV, DerivedParameter
#      DerivedParameters will cause a set of hdf5 files to be generated.


# Rate of descent (RateOfDescent500To50FtMax) already in library

'''
Needs for UA benchmark

Fast Approach --Fix Vref tables
Slow Approach --Fix Vref tables
Above Glideslope --split from GS Deviation
Below Glideslope
Localizer Deviation --change return value to be absolute deviation
High Rate of Descent (RateOfDescent500To50FtMax and RateOfDescent1000To500FtMax)
Low Power --add AT settings??
Late Gear -- 
Late Flaps --(AltitudeAtLastFlapChangeBeforeTouchdown)
'''
class A320(VelocitySpeed):
    '''
    Velocity speed tables for Airbus A320.
    '''
    interpolate = True
    source = 'http://www.satavirtual.org/fleet/A320PERFORMANCE.PDF'
    weight_unit = 't'
    tables = {
        'vref': {
            'weight': (45.360, 49.900, 54.430, 58.970, 63.500, 68.040, 72.580, 77.110),
                  35: (112, 118, 124, 129, 134, 138, 143, 147),
                },
    }
    
VELOCITY_SPEED_MAP = {
    # Airbus
    ('A320', None): A320,
}   
def get_vspeed_map_mitre(series=None, family=None, engine_series=None, engine_type=None):
    '''
    Accessor for fetching velocity speed table classes.

    :param series: An aircraft series e.g. B737-300
    :type series: string
    :param family: An aircraft family e.g. B737
    :type family: string
    :param engine_series: An engine series e.g. CF6-80C2
    :type engine_series: string
    :returns: associated VelocitySpeed class
    :rtype: VelocitySpeed
    :raises: KeyError -- if no velocity speed mapping found.
    '''
    lookup_combinations = ((series, engine_type),
                           (family, engine_type),
                           (series, engine_series),
                           (family, engine_series),
                           (series, None),
                           (family, None))

    for combination in lookup_combinations:
        if combination in VELOCITY_SPEED_MAP:
            return VELOCITY_SPEED_MAP[combination]
        #else:
            #found = 'None'
            #return found




class AirspeedReferenceVref(DerivedParameterNode):
    '''a simple derived parameter = a new time series'''
    name = 'Vref (Recorded then Lookup)'
    units = 'kts'

    @classmethod
    def can_operate(cls, available):
        vref = 'Vref' in available
        afr = 'Airspeed' in available and any_of(['AFR Vref'], available)
        x = set(available)
        base = ['Airspeed', 'Series', 'Family', 'Approach And Landing',
                'Touchdown', 'Gross Weight Smoothed']
        weight = base + ['Gross Weight Smoothed']
        ##airbus = set(weight + ['Configuration']).issubset(x)
        config = set(weight + ['Flap']).issubset(x)
        return vref or afr or config

    def derive(self,
               flap=P('Flap'),
               #conf=P('Configuration'),
               air_spd=P('Airspeed'),
               gw=P('Gross Weight Smoothed'),
               touchdowns=KTI('Touchdown'),
               series=A('Series'),
               family=A('Family'),
               engine=A('Engine Series'),
               engine_type=A('Engine Type'),
               eng_np=P('Eng (*) Np Avg'),
               vref=P('Vref'),
               afr_vref=A('AFR Vref'),
               approaches=S('Approach And Landing')):

        if vref:
            # Use recorded Vref parameter:
            self.array = vref.array
        elif afr_vref:
            # Use provided Vref from achieved flight record:
            afr_vspeed = afr_vref
            self.array = np.ma.zeros(len(air_spd.array), np.double)
            self.array.mask = True
            for approach in approaches:
                self.array[approach.slice] = afr_vspeed.value
        else:
            # Use speed card lookups
            self.array = np_ma_masked_zeros_like(air_spd.array)

            x = map(lambda x: x.value if x else None, (series, family, engine, engine_type))

            vspeed_class_test = get_vspeed_map_mitre(*x)
            
            if vspeed_class_test:
                vspeed_class = vspeed_class_test
            else:
                vspeed_class = get_vspeed_map(*x)

                        
            
            
            if gw is not None:  # and you must have eng_np
                try:
                    # Allow up to 2 superframe values to be repaired:
                    # (64 * 2 = 128 + a bit)
                    repaired_gw = repair_mask(gw.array, repair_duration=130,
                                              copy=True, extrapolate=True)
                except:
                    self.warning("'Airspeed Reference' will be fully masked "
                                 "because 'Gross Weight Smoothed' array could not be "
                                 "repaired.")
                    return

                setting_param = flap #or conf
                vspeed_table = vspeed_class()
                for approach in approaches:
                    _slice = approach.slice
                    index = np.ma.argmax(setting_param.array[_slice])
                    setting = setting_param.array[_slice][index]
                    weight = repaired_gw[_slice][index] if gw is not None else None
                    if is_index_within_slice(touchdowns.get_last().index, _slice) \
                       or setting in vspeed_table.vref_settings:
                        # Landing or approach with setting in vspeed table:
                        vspeed = vspeed_table.vref(setting, weight)
                    else:
                        # No landing and max setting not in vspeed table:
                        if setting_param.name == 'Flap':
                            setting = max(get_flap_map(series.value, family.value))
                        else:
                            setting = max(get_conf_map(series.value, family.value).keys())
                            vspeed = vspeed_table.vref(setting, weight)
                    self.array[_slice] = vspeed
                            
                            
class AirspeedRelativeMax1000to500ftHAT (KeyPointValueNode):
    '''CAS-Vref 1000 to 500 ft HAT'''
    name = 'Airspeed Relative 1000 to 500 ft HAT Max'
    units = 'kts'
    
    def derive(self,
               vref=P('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
        
        for app in approaches:          
            
            cas_vref=cas.array-vref.array
            self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(1000,500),max_value)
        
class AltitudeAtLastGearDownBeforeTouchdown(KeyPointValueNode):
    '''
    '''

    units = 'ft'

    def derive(self,
               gear=M('Gear Down'), 
               alt_aal=P('Altitude AAL'),              
               touchdowns=KTI('Touchdown')):

        for touchdown in touchdowns:
            rough_index = index_at_value(gear.array.data, 0.5, slice(touchdown.index, 0, -1))
            # index_at_value tries to be precise, but in this case we really
            # just want the index at the new flap setting.
            if rough_index:
                last_index = np.round(rough_index)
                alt_last = value_at_index(alt_aal.array, last_index)
                self.create_kpv(last_index, alt_last)     
        
### Section 3: pre-defined test sets
def tiny_test():
    '''quick test set'''
    input_dir  = settings.BASE_DATA_PATH + 'tiny_test/'
    print input_dir
    files_to_process = glob.glob(os.path.join(input_dir, '*.hdf5'))
    return files_to_process

def test10():
    '''quick test set'''
    input_dir  = settings.BASE_DATA_PATH + 'test10/'
    print input_dir
    files_to_process = glob.glob(os.path.join(input_dir, '*.hdf5'))
    return files_to_process
      
    
def test_sql_jfk():
    '''sample test set based on query from Oracle fds_flight_record'''
    query = """select file_path from fds_flight_record 
                 where 
                    orig_icao='KJFK' and dest_icao in ('KFLL','KMCO' )
                    """
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return files_to_process

def test_kpv_range():
    '''run against flights with select kpv values.
        TODO check how do multi-state params work
        TODO add index to FDS_KPV, FDS_KTI
        TODO improve support for profile KPV KTI phases
        TODO think more about treatment of multiples for a given KPV or KTI
    '''
    query="""select f.file_path --, kpv.name, kpv.value
                from fds_flight_record f join fds_kpv kpv 
                  on kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and ( 
                         (kpv.name='Airspeed 500 To 20 Ft Max' and kpv.value between 100.0 and 200.0)
                        or (kpv.name='Simple Kpv' and kpv.value>100)
                       ) 
                order by file_path
                """
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return files_to_process
    
def pkl_check():
   '''verify tcas profile using flights from updated LFL and load from pkl'''   
   query="""select distinct f.file_path 
                from (select * from fds_flight_record where analysis_time>to_date('2013-06-08 13:00','YYYY-MM-DD HH24:MI')) f 
                join 
                 fds_kpv kpv 
                  on kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and  f.base_file_path like '%cleansed%' 
                   and orig_icao='KJFK' and dest_icao in ('KFLL')
                   --and rownum < 10"""
   files_to_process = fds_oracle.flight_record_filepaths(query)
   return files_to_process
    
if __name__=='__main__':
    ###CONFIGURATION options###################################################
    FILES_TO_PROCESS = test_sql_jfk() # #test_kpv_range()  #test10()  #test_kpv_range() #pkl_check() #tiny_test()
    COMMENT   = 'lfl and pkl load check'
    LOG_LEVEL = 'DEBUG'   #'WARNING' shows less, 'INFO' moderate, 'DEBUG' shows most detail
    MAKE_KML_FILES=False    # Run times are much slower when KML is True
    ###########################################################################
    profile_name = os.path.basename(__file__).replace('.py','') #helper.get_short_profile_name(__file__)   # profile name = the name of this file
    print 'profile', profile_name
    save_oracle = True
    reports_dir = settings.PROFILE_REPORTS_PATH
    logger = helper.initialize_logger(LOG_LEVEL)
    # Determine module names so FlightDataAnalyzer knows what nodes it is working with. Must be in PYTHON_PATH.
    #  Normally we are just passing the current profile, but we could also send a list of profiles.
    module_names = [profile_name] #+'.'+short_profile, ]
    logger.warning('profile: '+profile_name)
    output_dir = settings.PROFILE_DATA_PATH + profile_name+'/' 
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    helper.run_analyzer(profile_name, module_names, 
             logger, FILES_TO_PROCESS, 
             'NA', output_dir, reports_dir, 
             include_flight_attributes=False, 
             make_kml=MAKE_KML_FILES, 
             save_oracle=save_oracle,
             comment=COMMENT)   
        
    logger.warning('done with profile')
    