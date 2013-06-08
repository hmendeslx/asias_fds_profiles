# -*- coding: utf-8 -*-
"""
Example profile module: defines a set of measures that run against 
FDS' FlightDataAnalyzer base data.

@author: KEITHC, April 2013
"""
### Section 1: dependencies (see FlightDataAnalyzer source files for additional options)
import pdb
import os, glob
from analysis_engine.node import ( A,   FlightAttributeNode,               # one of these per flight. mostly arrival and departure stuff
                                   App, ApproachNode,                      # per approach
                                   P,   DerivedParameterNode,              # time series with continuous values 
                                   M,   MultistateDerivedParameterNode,    # time series with discrete values
                                   KTI, KeyTimeInstanceNode,               # a list of time points meeting some criteria
                                   KPV, KeyPointValueNode,                 # a list of measures meeting some criteria; multiples are allowed and common 
                                   S,   SectionNode,  FlightPhaseNode,      # Sections=Phases
                                   KeyPointValue, KeyTimeInstance, Section  # data records, a list of which goes into the corresponding node
                                 )
# A Node is a list of items.  Each item type is a class with the fields listed below:
#   FlightAttribute = name, value.  could be a scolor or a collection, e.g. list or dict
#   ApproachItem    = recordtype('ApproachItem',    'type slice airport runway gs_est loc_est ils_freq turnoff lowest_lat lowest_lon lowest_hdg', default=None)  
#   KeyTimeInstance = recordtype('KeyTimeInstance', 'index name datetime latitude longitude', default=None)
#   Section = namedtuple('Section',                  'name slice start_edge stop_edge')   #=Phase
#   KeyPointValue   = recordtype('KeyPointValue', '  index value name slice datetime latitude longitude', field_defaults={'slice':slice(None)}, default=None)
                            
from analysis_engine.library import (integrate, repair_mask, index_at_value, all_of, any_of)
# asias_fds stuff
import analyser_custom_settings as settings
import staged_helper  as helper 
import fds_oracle

   
### Section 2: measure definitions -- attributes, KTI, phase/section, KPV, DerivedParameter
#      DerivedParameters will cause a set of hdf5 files to be generated.
class SimpleAttribute(FlightAttributeNode):
    '''a simple FlightAttribute. start_datetime is used only to provide a dependency'''
    #name = 'FDR Analysis Datetime'
    def derive(self, start_datetime=A('Start Datetime')):
        self.set_flight_attr('Keith')


class FileAttribute(FlightAttributeNode):
    '''a simple FlightAttribute. tests availability of Filename'''
    #name = 'FDR Analysis Datetime'
    def derive(self, filename=A('Myfile')):
        self.set_flight_attr(filename)


class MydictAttribute(FlightAttributeNode):
    '''a simple FlightAttribute. tests availability of Filename'''
    #name = 'FDR Analysis Datetime'
    def derive(self, mydict=A('Mydict')):
        mydict.value['testkey'] = [1,2,3]
        self.set_flight_attr(mydict)

             
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
    
class SimpleKPV(KeyPointValueNode):
    '''a simple KPV. start_datetime is used only to provide a dependency'''
    units='fpm'
    def derive(self, start_datetime=A('Start Datetime')):
        self.create_kpv(3.0, 999.9)

class SimplerKPV(KeyPointValueNode):
    '''just build it manually'''
    units='deg'
    def derive(self, start_datetime=A('Start Datetime')):
        self.append(KeyPointValue(index=42.5, value=666.6,name='My Simpler KPV'))
        print 'simpler KPV 2'
        self.append(KeyPointValue(index=42.5, value=666.6,name='My Simpler KPV 2'))

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


class InitialApproach(FlightPhaseNode):
    ''' a phase, derived from other phases.  S()=section=phase'''
    def derive(self, approach=S('Approach'), final=S('Final Approach') ):
        if len(approach)>0 and len(final)>0:
            dbegin = min([d.start_edge for d in approach])
            dend   = min([d.start_edge for d in final]) #exclude approach time
            self.create_phase(slice( dbegin, dend ))
        return


def aplot(array_dict={}, grid=True, legend=True):
    '''plot a dictionary of up to four arrays, with legend by default
        example dict:  {'Airspeed': airspeed.array }
    '''
    import matplotlib.pyplot as plt
    if len(array_dict.keys())==0:
        print 'Nothing to plot!'
        return
    series_names = array_dict.keys()[:4]  #only first 4
    series_formats = ['k','g','b','r']    #color codes
    for i,nm in enumerate(series_names):
        plt.plot(array_dict[nm], series_formats[i])
    if grid: plt.grid(True, color='gray')
    if legend: plt.legend(series_names, 'upper center')
    plt.xlabel('time index')
    print 'Paused for plot review. Close plot window to continue.'
    plt.show()
    plt.clf()
    

class DistanceTravelledInAir(DerivedParameterNode):
    '''a simple derived parameter = a new time series'''
    units='nm'
    def derive(self, airspeed=P('Airspeed True'), grounded=S('Grounded') ):
        for section in grounded:                      # zero out travel on the ground
            airspeed.array[section.slice]=0.0         # this is already a copy 
        repaired_array = repair_mask(airspeed.array)  # to avoid integration hiccups 
        adist      = integrate( repaired_array, airspeed.frequency, scale=1.0/3600.0 )
        self.array = adist
        aplot({'air dist':adist, 'airspd':airspeed.array})


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
    query = """select distinct file_path from fds_flight_record 
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
    query="""select distinct f.file_path --, kpv.name, kpv.value
                from fds_flight_record f join fds_kpv kpv 
                  on kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and f.orig_icao='KJFK' and f.dest_icao='KFLL'
                   and ( 
                         (kpv.name='Airspeed 500 To 20 Ft Max' and kpv.value between 100.0 and 200.0)
                        or (kpv.name='Simple Kpv' and kpv.value>100)
                       ) 
                order by file_path
                """
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return files_to_process
    
    
if __name__=='__main__':
    ###CONFIGURATION options###################################################
    FILES_TO_PROCESS = tiny_test() #test_kpv_range()  #test10() #tiny_test() #test_kpv_range() #test_sql_jfk() #
    COMMENT   = 'updated paths'
    LOG_LEVEL = 'INFO'   #'WARNING' shows less, 'INFO' moderate, 'DEBUG' shows most detail
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
    