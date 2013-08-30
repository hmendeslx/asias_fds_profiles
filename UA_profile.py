# -*- coding: utf-8 -*-
"""
Example profile module: defines a set of measures that run against Analyzer base data.
@author: SRANSOHOFF, MAY 2013

   
      save comments only to job records, not flight records.
"""
### Section 1: dependencies (see FlightDataAnalyzer source files for additional options)
import pdb
import os, glob, socket
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
                            
from analysis_engine.library import (integrate, repair_mask, index_at_value, all_of, any_of, max_value, min_value, max_abs_value, np_ma_masked_zeros_like, value_at_index,
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

Fast Approach --Fix Vref tables -done (mostly)
Slow Approach --Fix Vref tables -done (mostly)
Above Glideslope --split from GS Deviation -done
Below Glideslope -done
Localizer Deviation --change return value to be absolute deviation -done
High Rate of Descent (RateOfDescent500To50FtMax and RateOfDescent1000To500FtMax)
Low Power -- add AT settings??
Late Gear -- -done
Late Flaps --(AltitudeAtLastFlapChangeBeforeTouchdown)
'''

def sustained_max_abs(Param,window=3):
    '''
    sustained max function for sustained events, window default of 3 sec (+/- 1.5)
    must use at least 3 samples (+/-1 sample)
    '''
    x=np.ma.zeros(len(Param.array))
    add=Param.frequency*window/2
    absparam=abs(Param.array)
    if add<1.0:
        addint=1
    else:
        addint=int(add)
        
    shift=np.zeros(shape=(2*addint+1,len(Param.array)))
    for c in range(-addint,addint+1):
        shift[c+addint]=np.roll(absparam,c,axis=0)
    x.data[:]=shift.max(axis=0)        
        
    #length=len(Param.array)
    #for c in range(addint,length):
    #    x.data[c]=np.min(absparam[c-addint:c+addint+1])
    return x

def sustained_max(Param,window=3):
    '''
    sustained max function for sustained events, window default of 3 sec (+/- 1.5)
    must use at least 3 samples (+/-1 sample)
    '''
    x=np.ma.zeros(len(Param.array))
    add=Param.frequency*window/2
    if add<1.0:
        addint=1
    else:
        addint=int(add)
    #pdb.set_trace()
    shift=np.zeros(shape=(2*addint+1,len(Param.array)))
    for c in range(-addint,addint+1):
        shift[c+addint]=np.roll(Param.array,c,axis=0)
    x.data[:]=shift.min(axis=0)
    #length=len(Param.array)
    #for c in range(addint,length):
    #    x.data[c]=np.min(Param.array[c-addint:c+addint+1])
    return x
        
def sustained_min(Param,window=3):
    '''
    sustained min function for sustained events, window default of 3 sec (+/- 1.5)
    must use at least 3 samples (+/-1 sample)
    '''
    #pdb.set_trace()    
    x=np.ma.zeros(len(Param.array))
    add=Param.frequency*window/2
    if add<1.0:
        addint=1
    else:
        addint=int(add)
        
    shift=np.zeros(shape=(2*addint+1,len(Param.array)))
    for c in range(-addint,addint+1):
        shift[c+addint]=np.roll(Param.array,c,axis=0)
    x.data[:]=shift.max(axis=0)
    
    #length=len(Param.array)
    #for c in range(addint,length):
    #    x.data[c]=np.max(Param.array[c-addint:c+addint+1])
    return x
    

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


class AirspeedReferenceVref(FlightAttributeNode):
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
            #self.array = vref.array
            self.set_flight_attr(vref.array)
        elif afr_vref:
            # Use provided Vref from achieved flight record:
            afr_vspeed = afr_vref
            afrvref = np.ma.zeros(len(air_spd.array), np.double)
            afrvref.mask = True
            for approach in approaches:
                afrvref[approach.slice] = afr_vspeed.value
            self.set_flight_attr(afrvref)
        else:
            # Use speed card lookups
            lookup = np_ma_masked_zeros_like(air_spd.array)

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
                    '''TODO: Only uses max Vref setting, doesn't account for late config changes'''
                    index = np.ma.argmax(setting_param.array[_slice])
                    setting = setting_param.array[_slice][index]
                    weight = repaired_gw[_slice][index] if gw is not None else None
                    if setting in vspeed_table.vref_settings:
                       ##and is_index_within_slice(touchdowns.get_last().index, _slice):
                        # setting in vspeed table:
                        vspeed = vspeed_table.vref(setting, weight)
                    else:
                        ''' Do not like the default of using max Vref for go arounds... '''
                        ## No landing and max setting not in vspeed table:
                        #if setting_param.name == 'Flap':
                            #setting = max(get_flap_map(series.value, family.value))
                        #else:
                            #setting = max(get_conf_map(series.value, family.value).keys())
                            #vspeed = vspeed_table.vref(setting, weight)
                        self.warning("'Airspeed Reference' will be fully masked "
                                 "because Vref lookup table does not have corresponding values.")
                        return
 
                    lookup[_slice] = vspeed
                    self.set_flight_attr(lookup)


#class AirspeedReferenceVref(DerivedParameterNode):
    #'''a simple derived parameter = a new time series'''
    #name = 'Vref (Recorded then Lookup)'
    #units = 'kts'

    #@classmethod
    #def can_operate(cls, available):
        #vref = 'Vref' in available
        #afr = 'Airspeed' in available and any_of(['AFR Vref'], available)
        #x = set(available)
        #base = ['Airspeed', 'Series', 'Family', 'Approach And Landing',
                #'Touchdown', 'Gross Weight Smoothed']
        #weight = base + ['Gross Weight Smoothed']
        ###airbus = set(weight + ['Configuration']).issubset(x)
        #config = set(weight + ['Flap']).issubset(x)
        #return vref or afr or config

    #def derive(self,
               #flap=P('Flap'),
               ##conf=P('Configuration'),
               #air_spd=P('Airspeed'),
               #gw=P('Gross Weight Smoothed'),
               #touchdowns=KTI('Touchdown'),
               #series=A('Series'),
               #family=A('Family'),
               #engine=A('Engine Series'),
               #engine_type=A('Engine Type'),
               #eng_np=P('Eng (*) Np Avg'),
               #vref=P('Vref'),
               #afr_vref=A('AFR Vref'),
               #approaches=S('Approach And Landing')):

        #if vref:
            ## Use recorded Vref parameter:
            #self.array = vref.array
        #elif afr_vref:
            ## Use provided Vref from achieved flight record:
            #afr_vspeed = afr_vref
            #self.array = np.ma.zeros(len(air_spd.array), np.double)
            #self.array.mask = True
            #for approach in approaches:
                #self.array[approach.slice] = afr_vspeed.value
        #else:
            ## Use speed card lookups
            #self.array = np_ma_masked_zeros_like(air_spd.array)

            #x = map(lambda x: x.value if x else None, (series, family, engine, engine_type))

            #vspeed_class_test = get_vspeed_map_mitre(*x)
            
            #if vspeed_class_test:
                #vspeed_class = vspeed_class_test
            #else:
                #vspeed_class = get_vspeed_map(*x)

                        
            
            
            #if gw is not None:  # and you must have eng_np
                #try:
                    ## Allow up to 2 superframe values to be repaired:
                    ## (64 * 2 = 128 + a bit)
                    #repaired_gw = repair_mask(gw.array, repair_duration=130,
                                              #copy=True, extrapolate=True)
                #except:
                    #self.warning("'Airspeed Reference' will be fully masked "
                                 #"because 'Gross Weight Smoothed' array could not be "
                                 #"repaired.")
                    #return

                #setting_param = flap #or conf
                #vspeed_table = vspeed_class()
                #for approach in approaches:
                    #_slice = approach.slice
                    #'''TODO: Only uses max Vref setting, doesn't account for late config changes'''
                    #index = np.ma.argmax(setting_param.array[_slice])
                    #setting = setting_param.array[_slice][index]
                    #weight = repaired_gw[_slice][index] if gw is not None else None
                    #if setting in vspeed_table.vref_settings:
                       ###and is_index_within_slice(touchdowns.get_last().index, _slice):
                        ## setting in vspeed table:
                        #vspeed = vspeed_table.vref(setting, weight)
                    #else:
                        #''' Do not like the default of using max Vref for go arounds... '''
                        ### No landing and max setting not in vspeed table:
                        ##if setting_param.name == 'Flap':
                            ##setting = max(get_flap_map(series.value, family.value))
                        ##else:
                            ##setting = max(get_conf_map(series.value, family.value).keys())
                            ##vspeed = vspeed_table.vref(setting, weight)
                        #self.warning("'Airspeed Reference' will be fully masked "
                                 #"because Vref lookup table does not have corresponding values.")
                        #return
 
                    #self.array[_slice] = vspeed
                            
'''
Sustained UA metrics
'''                            

class AirspeedRelativeMin3Sec1000to500ftHAT (KeyPointValueNode):
    '''CAS-Vref 1000 to 500 ft HAT'''
    name = 'Airspeed Relative 1000 to 500 ft HAT Min (3 sec)'
    units = 'kts'
    
    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref
    
    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
        
        cas_run = sustained_min(cas)
        for app in approaches:          
            if vref is not None and vref.value is not None:
                cas_vref=cas_run.data-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(1000,500),min_value)
            else:
                return

              
class AirspeedRelativeMax3Sec1000to500ftHAT (KeyPointValueNode):
    '''CAS-Vref 1000 to 500 ft HAT'''
    name = 'Airspeed Relative 1000 to 500 ft HAT Max (3 sec)'
    units = 'kts'
    
    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref
    
    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
   
               approaches=S('Approach And Landing')):
                   
        cas_run = sustained_max(cas)
        for app in approaches:  
            #pdb.set_trace()
            if vref is not None and vref.value is not None:
                cas_vref=cas_run.data-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(1000,500),max_value)
            else:
                return

class AirspeedRelativeMax3Sec500to50ftHAT (KeyPointValueNode):
    '''CAS-Vref 500 to 50 ft HAT'''
    name = 'Airspeed Relative 500 to 50 ft HAT Max (3 sec)'
    units = 'kts'
    
    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref    
    
    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
        
        cas_run = sustained_max(cas)
        for app in approaches:  
            if vref is not None and vref.value is not None:            
                cas_vref=cas_run.data-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(500,50),max_value)
            else:
                return
            
class AirspeedRelativeMin3sec500to50ftHAT (KeyPointValueNode):
    '''CAS-Vref 500 to 50 ft HAT'''
    name = 'Airspeed Relative 500 to 50 ft HAT Min (3 sec)'
    units = 'kts'

    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref

    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
        cas_run = sustained_min(cas)
        for app in approaches:       
            if vref is not None and vref.value is not None:               
                cas_vref=cas_run.data-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(500,50),min_value)
            else:
                return


class GlideslopeDeviation5Sec1000To500FtMax(KeyPointValueNode):
    '''
    Determine maximum deviation from the glideslope between 1000 and 500 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 1000 To 500 Ft Max (5 sec)'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(1000, 500)
        ils_run = sustained_max(ils_glideslope, window=5)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_run.data,
                alt_bands,
                max_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return
        
class GlideslopeDeviation5Sec500To200FtMax(KeyPointValueNode):
    '''
    Determine maximum deviation from the glideslope between 500 and 200 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 500 To 200 Ft Max (5 sec)'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(500, 200)
        ils_run = sustained_max(ils_glideslope, window=5)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_run.data,
                alt_bands,
                max_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return
        
class GlideslopeDeviation5Sec1000To500FtMin(KeyPointValueNode):
    '''
    Determine minimium deviation from the glideslope between 1000 and 500 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 1000 To 500 Ft Min (5 sec)'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(1000, 500)
        ils_run = sustained_min(ils_glideslope, window=5)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_run.data,
                alt_bands,
                min_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return
        
class GlideslopeDeviation5Sec500To200FtMin(KeyPointValueNode):
    '''
    Determine minimium deviation from the glideslope between 500 and 200 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 500 To 200 Ft Min (5 sec)'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(500, 200)
        ils_run = sustained_min(ils_glideslope, window=5)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_run.data,
                alt_bands,
                min_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return

class LocalizerDeviation5Sec500To50FtMax(KeyPointValueNode):
    '''
    Determine maximum absolute deviation from the localizer between 500 and 50 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Localizer Deviation 500 To 50 Ft Max (5 sec)'
    units = 'dots'

    def derive(self,
               ils_localizer=P('ILS Localizer'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Localizer Established')
               ):

        alt_bands = alt_aal.slices_from_to(500, 50)
        ils_run = sustained_max_abs(ils_localizer, window=5)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_localizer:
            self.create_kpvs_within_slices(
                abs(ils_run.data),
                alt_bands,
                max_abs_value,
            )
        else:
            self.warning("ILS Localizer not measured on approach")            
            return
        
class LocalizerDeviation5Sec1000To500FtMax(KeyPointValueNode):
    '''
    Determine maximum absolute deviation from the localizer between 1000 and 500 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Localizer Deviation 1000 To 500 Ft Max (5 sec)'
    units = 'dots'

    def derive(self,
               ils_localizer=P('ILS Localizer'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Localizer Established')
               ):

        alt_bands = alt_aal.slices_from_to(1000, 500)
        ils_run = sustained_max_abs(ils_localizer, window=5)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_localizer:
            self.create_kpvs_within_slices(
                abs(ils_run.data),
                alt_bands,
                max_abs_value,
            )
        else:
            self.warning("ILS Localizer not measured on approach")            
            return


class RateOfDescent3Sec1000To500FtMax(KeyPointValueNode):
    '''
    '''
    name = 'Rate of Descent 1000 to 500 ft Max (3 sec)'
    units = 'fpm'

    def derive(self,
               vrt_spd=P('Vertical Speed'),
               alt_aal=P('Altitude AAL For Flight Phases')):

        vsi_run=sustained_min(vrt_spd)        
        self.create_kpvs_within_slices(
            vsi_run.data,
            alt_aal.slices_from_to(1000, 500),
            min_value,
        )


class RateOfDescent3Sec500To50FtMax(KeyPointValueNode):
    '''
    '''
    name = 'Rate of Descent 500 to 50 ft Max (3 sec)'
    units = 'fpm'

    def derive(self,
               vrt_spd=P('Vertical Speed'),
               alt_aal=P('Altitude AAL For Flight Phases')):

        vsi_run=sustained_min(vrt_spd)          
        self.create_kpvs_within_slices(
            vsi_run.data,
            alt_aal.slices_from_to(500, 50),
            min_value,
        )

class EngN15Sec500To50FtMin(KeyPointValueNode):
    '''
    '''

    name = 'Eng N1 500 To 50 Ft Min (5 sec)'
    units = '%'

    def derive(self,
               eng_n1_min=P('Eng (*) N1 Min'),
               alt_aal=P('Altitude AAL For Flight Phases')):
        
        eng_run=sustained_min(eng_n1_min, window=5)
        self.create_kpvs_within_slices(
            eng_run.data,
            alt_aal.slices_from_to(500, 50),
            min_value,
        )

class EngN15Sec1000To500FtMin(KeyPointValueNode):
    '''
    '''

    name = 'Eng N1 1000 To 500 Ft Min (5 sec)'
    units = '%'

    def derive(self,
               eng_n1_min=P('Eng (*) N1 Min'),
               alt_aal=P('Altitude AAL For Flight Phases')):
        
        eng_run=sustained_min(eng_n1_min, window=5)
        self.create_kpvs_within_slices(
            eng_run.data,
            alt_aal.slices_from_to(1000, 500),
            min_value,
        )



"""
'''
Instantaneous UA metrics
'''
class AirspeedRelativeMax1000to500ftHAT (KeyPointValueNode):
    '''CAS-Vref 1000 to 500 ft HAT'''
    name = 'Airspeed Relative 1000 to 500 ft HAT Max'
    units = 'kts'
    
    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref
    
    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
        
        for app in approaches:  
            if vref.value is not None:
                cas_vref=cas.array-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(1000,500),max_value)
            else:
                return
            
class AirspeedRelativeMin1000to500ftHAT (KeyPointValueNode):
    '''CAS-Vref 1000 to 500 ft HAT'''
    name = 'Airspeed Relative 1000 to 500 ft HAT Min'
    units = 'kts'
    
    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref
    
    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
        
        for app in approaches:          
            if vref.value is not None:
                cas_vref=cas.array-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(1000,500),min_value)
            else:
                return
            
class AirspeedRelativeMax500to50ftHAT (KeyPointValueNode):
    '''CAS-Vref 500 to 50 ft HAT'''
    name = 'Airspeed Relative 500 to 50 ft HAT Max'
    units = 'kts'
    
    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref    
    
    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
        
        for app in approaches:  
            if vref.value is not None:            
                cas_vref=cas.array-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(500,50),max_value)
            else:
                return
            
class AirspeedRelativeMin500to50ftHAT (KeyPointValueNode):
    '''CAS-Vref 500 to 50 ft HAT'''
    name = 'Airspeed Relative 500 to 50 ft HAT Min'
    units = 'kts'

    @classmethod
    def can_operate(cls, available):
        vref = 'Vref (Recorded then Lookup)' in available
        return vref

    def derive(self,
               #vref=P('Vref (Recorded then Lookup)'),
               vref=A('Vref (Recorded then Lookup)'),
               cas=P('Airspeed'),
               altitude=P('Altitude AAL'),
               touchdowns=KTI('Touchdown'),
               approaches=S('Approach And Landing')):
    
        for app in approaches:       
            if vref.value is not None:               
                cas_vref=cas.array-vref.value
                self.create_kpvs_within_slices(cas_vref,altitude.slices_from_to(500,50),min_value)
            else:
                return
            
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

class GlideslopeDeviation1000To500FtMax(KeyPointValueNode):
    '''
    Determine maximum deviation from the glideslope between 1000 and 500 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 1000 To 500 Ft Max'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(1000, 500)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_glideslope.array,
                alt_bands,
                max_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return
        
class GlideslopeDeviation500To200FtMax(KeyPointValueNode):
    '''
    Determine maximum deviation from the glideslope between 500 and 200 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 500 To 200 Ft Max'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(500, 200)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_glideslope.array,
                alt_bands,
                max_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return
        
class GlideslopeDeviation1000To500FtMin(KeyPointValueNode):
    '''
    Determine minimium deviation from the glideslope between 1000 and 500 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 1000 To 500 Ft Min'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(1000, 500)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_glideslope.array,
                alt_bands,
                min_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return
        
class GlideslopeDeviation500To200FtMin(KeyPointValueNode):
    '''
    Determine minimium deviation from the glideslope between 500 and 200 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Glideslope Deviation 500 To 200 Ft Min'
    units = 'dots'

    def derive(self,
               ils_glideslope=P('ILS Glideslope'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Glideslope Established')
               ):

        alt_bands = alt_aal.slices_from_to(500, 200)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_glideslope:
            self.create_kpvs_within_slices(
                ils_glideslope.array,
                alt_bands,
                min_value,
            )
        else:
            self.warning("ILS Glideslope not measured on approach")            
            return

class LocalizerDeviation500To50FtMax(KeyPointValueNode):
    '''
    Determine maximum absolute deviation from the localizer between 500 and 50 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Localizer Deviation 500 To 50 Ft Max'
    units = 'dots'

    def derive(self,
               ils_localizer=P('ILS Localizer'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Localizer Established')
               ):

        alt_bands = alt_aal.slices_from_to(500, 50)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_localizer:
            self.create_kpvs_within_slices(
                abs(ils_localizer.array),
                alt_bands,
                max_abs_value,
            )
        else:
            self.warning("ILS Localizer not measured on approach")            
            return
        
"""
class LocalizerDeviation1000To500FtMax(KeyPointValueNode):
    '''
    Determine maximum absolute deviation from the localizer between 1000 and 500 ft.
    
    ## MITRE edit: ILS established assumes that the aircraft was aligned then deviated, we want the full range
    '''

    name = 'Localizer Deviation 1000 To 500 Ft Max'
    units = 'dots'

    def derive(self,
               ils_localizer=P('ILS Localizer'),
               alt_aal=P('Altitude AAL For Flight Phases'),
               #ils_ests=S('ILS Localizer Established')
               ):

        alt_bands = alt_aal.slices_from_to(1000, 500)
        #ils_bands = slices_and(alt_bands, ils_ests.get_slices())
        if ils_localizer:
            self.create_kpvs_within_slices(
                abs(ils_localizer.array),
                alt_bands,
                max_abs_value,
            )
        else:
            self.warning("ILS Localizer not measured on approach")            
            return

### Section 3: pre-defined test sets
def tiny_test():
    '''quick test set'''
    repo = 'NA'
    input_dir  = settings.BASE_DATA_PATH + 'tiny_test/'
    print input_dir
    files_to_process = glob.glob(os.path.join(input_dir, '*.hdf5'))
    return repo, files_to_process

def test10():
    '''quick test set'''
    repo = 'NA'
    input_dir  = settings.BASE_DATA_PATH + 'test10/'
    print input_dir
    files_to_process = glob.glob(os.path.join(input_dir, '*.hdf5'))
    return repo, files_to_process
      
    
def test_sql_jfk():
    '''sample test set based on query from Oracle fds_flight_record'''
    repo = 'central'
    query = """select file_path from fds_flight_record 
                 where file_repository='REPO'
                    and orig_icao='KJFK' and dest_icao in ('KFLL','KMCO' )
                    """.replace('REPO',repo)
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return repo, files_to_process

def test_sql_jfk_local():
    '''sample test set based on query from Oracle fds_flight_record'''
    repo = 'local'
    query = """select file_path from fds_flight_record 
                 where file_repository='REPO'
                    and orig_icao='KJFK' and dest_icao in ('KFLL','KMCO' )
                    """.replace('REPO',repo)
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return repo, files_to_process

def test_sql_ua_apts():
    '''sample test set based on query from Oracle fds_flight_record'''
    repo = 'central'
    query = """select file_path from fds_flight_record 
                 where 
                    file_repository='REPO'
                    and dest_icao in ('KFLL','KMCO','KHPN','KIAD' )
                    """.replace('REPO',repo)
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return repo, files_to_process


def test_sql_ua_all():
    '''sample test set based on query from Oracle fds_flight_record'''
    repo = 'central'
    query = """select file_path from fds_flight_record 
                 where 
                    file_repository='REPO' 
                    """.replace('REPO',repo)
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return repo, files_to_process

def test_kpv_range():
    '''run against flights with select kpv values.
        TODO check how do multi-state params work
        TODO add index to FDS_KPV, FDS_KTI
        TODO improve support for profile KPV KTI phases
        TODO think more about treatment of multiples for a given KPV or KTI
    '''
    repo = 'central'
    query="""select f.file_path --, kpv.name, kpv.value
                from fds_flight_record f join fds_kpv kpv 
                  on kpv.file_repository=f.file_repository and kpv.base_file_path=f.base_file_path
                 where f.file_repository='REPO'
                   and ( 
                         (kpv.name='Airspeed 500 To 20 Ft Max' and kpv.value between 100.0 and 200.0)
                        or (kpv.name='Simple Kpv' and kpv.value>100)
                       ) 
                order by file_path
                """.replace('REPO',repo)
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return repo, files_to_process
    
def local_check():
   '''verify tcas profile using flights from updated LFL and load from pkl'''   
   repo = 'local'
   query="""select distinct f.file_path 
                from (select * from fds_flight_record where analysis_time>to_date('2013-06-08 13:00','YYYY-MM-DD HH24:MI')) f 
                join 
                 fds_kpv kpv 
                  on kpv.file_repository=f.file_repository and kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and  f.file_repository='REPO'
                   and orig_icao='KJFK' and dest_icao in ('KFLL')
                   """.replace('REPO',repo)
   files_to_process = fds_oracle.flight_record_filepaths(query)
   return repo, files_to_process

def pkl_check():
   '''verify tcas profile using flights from updated LFL and load from pkl'''   
   repo = 'central'
   query="""select distinct f.file_path 
                from (select * from fds_flight_record where analysis_time>to_date('2013-06-08 13:00','YYYY-MM-DD HH24:MI')) f 
                join 
                 fds_kpv kpv 
                  on kpv.file_repository=f.file_repository and kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and  f.file_repository='REPO'
                   and orig_icao='KJFK' and dest_icao in ('KFLL')
                   and rownum < 10""".replace('REPO',repo)
   files_to_process = fds_oracle.flight_record_filepaths(query)
   return repo, files_to_process
    
if __name__=='__main__':
    ###CONFIGURATION options###################################################
    PROFILE_NAME = 'UAv1'  + '-'+ socket.gethostname()   
    REPO, FILES_TO_PROCESS = test10() #test_sql_ua_all()   #test_sql_jfk_local() #test_kpv_range()  #test10() #test_kpv_range() #pkl_check() #tiny_test() #test_sql_ua_apts() # #test_sql_jfk()
    COMMENT   = 'UA with times'
    LOG_LEVEL = 'WARNING'   #'WARNING' shows less, 'INFO' moderate, 'DEBUG' shows most detail
    MAKE_KML_FILES=False    # Run times are much slower when KML is True
    ###########################################################################
    
    module_names = [ os.path.basename(__file__).replace('.py','') ]#helper.get_short_profile_name(__file__)   # profile name = the name of this file
    print 'profile', PROFILE_NAME 
    helper.run_profile(PROFILE_NAME , module_names, LOG_LEVEL, FILES_TO_PROCESS, COMMENT, MAKE_KML_FILES, REPO )
    