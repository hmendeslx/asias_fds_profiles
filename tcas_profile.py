# -*- coding: utf-8 -*-
"""
TCAS Profile
@author: KEITHC, May 2013

TCAS Elements
    scrubbed TCAS:                this: new TCAS RA Start KTI  cycle count, active at liftoff, maximum duration (start with KTI)
    when did TCAS occur?          base: TCAS RA Warning Duration  .time_index
    how long was it active?       base: TCAS RA Warning Duration
    what was directive?           this: TCASCombinedControl|x, TCASVerticalControl|x
            was there a Reversal? this: TCASVerticalControl|Reversal
    was the directive followed?   TODO  e.g. altitude exceedance (PARTIALLY IMPLEMENTED)
    State at Start of RA:
        Vertical Speed  --        this: 'TCAS RA Start Vertical Speed' = VerticalSpeedAtTCASRAStart()
        Altitude        --        this: 'TCAS RA Start Altitude QNH'   = AltitudeQNHAtTCASRAStart()
        AP              --        this: 'TCAS RA Start Autopilot'      = AutopilotAtTCASRAStart()
        Pitch           --        this: 'TCAS RA Start Pitch'          = PitchAtTCASRAStart()
        Roll            --        this: 'TCAS RA Start Roll'           = RollAtTCASRAStart()
    Change in state during RA?    base: 'Heading Increase'             = absolute change
    How did pilot respond?        base: 'TCAS RA Reaction Delay' (uses normal acceleration)
        disengage AP?             base: 'TCAS RA To AP Disengaged Duration'
                                  base: 'TCAS RA Initial Reaction Strength' (positive if alt change consistent with RA)
  
For event rates: build a simple KPV or KTI to just check pre-req and count reference flights.
NOTE: we are assuming 1 Hz TCAS Combined Control
"""
### Section 1: dependencies (see FlightDataAnalyzer source files for additional options)
import pdb
import os, glob
import numpy as np
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
                            
import library
# asias_fds stuff
import analyser_custom_settings as settings
import staged_helper  as helper 
import fds_oracle

   
### Section 2: measure definitions -- attributes, KTI, phase/section, KPV, DerivedParameter
#      DerivedParameters will cause a set of hdf5 files to be generated.


# use as cross-check on kti processing
class SimpleKTI(KeyTimeInstanceNode):
    '''a simple KTI. start_datetime is used only to provide a dependency'''
    def derive(self, start_datetime=A('Start Datetime')):
        #print 'in SimpleKTI'
        self.create_kti(3)    


class TCASRASections(FlightPhaseNode):
    '''TCAS RA sections that pass quality filtering '''
    name = 'TCAS RA Sections'
    def derive(self, tcas=M('TCAS Combined Control'), off=KTI('Liftoff') ):
        ras_local = tcas.array.any_of('Drop Track', 'Altitude Lost', 'Up Advisory Corrective','Down Advisory Corrective')                    
        ras_slices = library.runs_of_ones(ras_local)
        if ras_slices:
            # require RA to start at least 10 seconds after liftoff 
            is_post_liftoff =  (ras_slices[0].start - off.get_first().index) > 10 
            if is_post_liftoff and len(ras_slices)<5: #ignore cycling
                #print 'ra section', ras_slices
                for ra_slice in ras_slices:                    
                    duration = ra_slice.stop-ra_slice.start                     
                    if 3.0 <= duration < 120.0: #ignore if too short to do anything
                        #print ' ra section', ra_slice
                        self.create_phase( ra_slice )    
        return


class TCASRAStart(KeyTimeInstanceNode):
    name = 'TCAS RA Start'
    def derive(self, ra_sections=S('TCAS RA Sections')):
        for s in ra_sections:
            self.create_kti(s.start_edge)


def tcas_vert_spd_up(tcas_up, vert_speed, tcas_vert):
    '''determine the change in vertical speed commanded  by a tcas ra 
            if TCAS combined control is Up Advisory
    '''
    upcmd = tcas_up
    if upcmd=='Climb':
        if tcas_vert=="Increase":            
            return 2500  # climb at least 1500 fpm 
        else:
            return 1500
    elif upcmd=="Don't Descend 500":
        return -500  # don't descend more than 500 fpm
    elif upcmd=="Don't Descend 1000":
        return -1000
    elif upcmd=="Don't Descend 2000":
        return -2000
    else: # 'Preventative' state seems questionable
        print 'Other initial up: ', tcas_up
        return None
        

def tcas_vert_spd_down(tcas_down, vert_speed, tcas_vert):
    '''determine the change in vertical speed commanded  by a tcas ra
        if TCAS combined control is Down Advisory
    '''
    downcmd = tcas_down
    if downcmd=='Descend':
        if tcas_vert=="Increase":            
            return -2500  # climb at least 1500 fpm 
        else:
            return -1500
    elif downcmd=="Don't Climb 500":
        return 500 #don't descend more than 500 fpm
    elif downcmd=="Don't Climb 1000":
        return 1000
    elif downcmd=="Don't Climb 2000":
        return 2000
    else: 
        print 'Other initial down: ', tcas_down
        return None


def plot_mapped_array(plt, myaxis, states, mapped_array, title="", series_format="g"):
    '''MappedArray maps discrete states to an integer array.
       Here we plot the states as a time series with states labelled on the y axis.'''
    plt.yticks( np.arange(len(states)), states )
    myaxis.plot(mapped_array, 'g')
    myaxis.grid(True, color='gray')
    plt.ylim(0, len(states)) 
    plt.title(title)

    
def ra_plot(array_dict, tcas_ctl_array, tcas_up_array, tcas_down_array, 
            vert_ctl_array, sens_array, filename, orig, dest, tstart, tend):
    '''plot tcas: vertical speed + controls    '''
    import matplotlib.pyplot as plt
    plt.figure(figsize=(15,15)) #set size in inches
    plt.subplots_adjust(left=None, bottom=None, right=None, top=None, wspace=None, hspace=0.5)
    
    # top time series plot
    axts    = plt.subplot2grid((8, 1), (0, 0), rowspan=3) #time series    
    series_names = array_dict.keys()  #only first 4
    series_formats = ['k','g','b','r']    #color codes
    for i,nm in enumerate(series_names):
        axts.plot(array_dict[nm], series_formats[i], alpha=0.45)
    leg = axts.legend(series_names, 'upper left', fancybox=True)
    leg.get_frame().set_alpha(0.5)
    axts.grid(True, color='gray')
    plt.title('Vertical Speed (fpm)')
    axts.autoscale(enable=False)
    
    # combined control
    ax_ctl = plt.subplot2grid((8, 1), (3, 0), sharex=axts)     # 
    ctl_states = tcas_ctl_array.values_mapping.values()
    ctl_states = [s.replace('Advisory','Advzy').replace('Corrective', 'Corr.') for s in ctl_states]
    ctl_array = tcas_ctl_array.data 
    plot_mapped_array(plt, ax_ctl, ctl_states, ctl_array, title="TCAS Combined Control")

    # up and down advisory
    ax_updown   = plt.subplot2grid((8, 1), (4, 0), sharex=axts, rowspan=2)  
    up_states   = [' ']+tcas_up_array.values_mapping.values()
    down_states = [' ']+tcas_down_array.values_mapping.values()
    ud_states    = up_states + down_states
    
    def disp_state(st):
        st = st.replace('Descent Corrective','Desc Corr.')
        st = st.replace('Descend ','Desc>')
        #st = st.replace('Descent','Descend')
        st = st.replace('Advisory','Advzy').replace('advisory','Advzy')
        #st = st.replace("Don'Cl","Don't Cl")
        st = st.replace("Don't Climb ","Don't Climb>")
        return st

    ud_states = [ disp_state(s) for s in ud_states]
    plt.yticks( np.arange(len(ud_states)), ud_states )   

    up_array = tcas_up_array.data + 1 # adjust for display
    ax_updown.plot(up_array, 'g')
    down_array = tcas_down_array.data + len(up_states)+1 # adjust for display
    ax_updown.plot(down_array, 'r')
    ax_updown.grid(True, color='gray')
    plt.ylim(0, len(up_states) + len(down_states)) 
    plt.title('TCAS Up/Down Advisory')
    
    # vertical control
    ax_vert   = plt.subplot2grid((8, 1), (6, 0), sharex=axts)  
    vert_states   = vert_ctl_array.values_mapping.values()    
    vert_states = [' ']+[s.replace("Advisory is not one of the following types",'NA') for s in vert_states]
    vert_array = vert_ctl_array.data + 1
    plot_mapped_array(plt, ax_vert, vert_states, vert_array, title="TCAS Vertical Control")
    
    #sensitivity mode    
    ax_sens   = plt.subplot2grid((8, 1), (7, 0), sharex=axts)  
    sens_states   = sens_array.values_mapping.values()    
    sens_states = [' ']+[s.replace("SL = ",'') for s in sens_states]
    sens_arr = sens_array.data + 1 # adjust for display
    plot_mapped_array(plt, ax_sens, sens_states, sens_arr, title="TCAS Sensitivity Mode")

    plt.xlabel('time index')
    plt.xlim(tstart, tend) 
    plt.suptitle('TCAS RA: '+filename.value + '\n  '+orig.value['code']['icao']+'-'+dest.value['code']['icao'])
    return plt
    

def update_std_vert_spd(t, lag_end, cmb_ctl, acceleration, required_fpm, std_vert_spd):
    if t<lag_end: # not responding yet
        pass
    else:
        if cmb_ctl == 'Down Advisory Corrective':
            if std_vert_spd>required_fpm: std_vert_spd -= acceleration
            if std_vert_spd<required_fpm: std_vert_spd = required_fpm #correct overshoot
        elif cmb_ctl == 'Up Advisory Corrective':
            if std_vert_spd<required_fpm: std_vert_spd += acceleration
            if std_vert_spd>required_fpm: std_vert_spd = required_fpm #correct overshoot
        else: #better have a look
            print 'TCAS RA Standard Response: Ctl not Up or Down Corrective. Take a look!'
            pdb.set_trace()    
    return std_vert_spd


"""
class TCASRAResponsePlot(DerivedParameterNode):
    '''dummy node for diagnostic plotting '''
    name = "TCAS RA Response Plot"
    def derive(self, std_vert_spd = P('TCAS RA Standard Response'), 
                     tcas_ctl  =  M('TCAS Combined Control'), 
                     tcas_up   =  M('TCAS Up Advisory'), 
                     tcas_down =  M('TCAS Down Advisory'), 
                     tcas_vert =  M('TCAS Vertical Control'), 
                     tcas_sens =  M('TCAS Sensitivity Level'), 
                     vertspd   =  P('Vertical Speed'), 
                     ra_sections = S('TCAS RA Sections'), 
                     raduration  = KPV('TCAS RA Warning Duration'),
                     filename    = A('Myfile'),
                     orig = A('FDR Takeoff Airport'),
                     dest = A('FDR Landing Airport'),
              ):
        print 'starting', filename
        if len(ra_sections)>0:
            tstart = max( min([ra.start_edge for ra in ra_sections])-15.0, 0)
            tend   = min( max([ra.stop_edge for ra in ra_sections]) +15.0, len(tcas_ctl.array))
            #pdb.set_trace()
            plt = ra_plot({'vertspd':vertspd.array, 'std response':std_vert_spd.array}, 
                      tcas_ctl.array, tcas_up.array, tcas_down.array, 
                      tcas_vert.array, tcas_sens.array, filename, orig, dest,
                      tstart, tend
                      )  
            #helper.show_plot(plt)                      
            fname = filename.value.replace('.hdf5', '.png')
            helper.save_plot(plt, fname)
        self.array = std_vert_spd.array
        print 'finishing', filename
        return
"""



### TODO sort out Drop Track and Altitude 
### TODO what if TCAS Vertical Control is Maintain; 
class TCASRAStandardResponse(DerivedParameterNode):
    '''standard pilot response -- a vertical speed curve to use as a reference
        source for standard response time and acceleration:
               "Introduction to TCAS II version 7.1" 
                Federal Aviation Administration, February 28, 2011.  p. 39
            
        initial response time = 5 sec    (2.5 sec for reversal)
        acceleration to advised vert speed = 8.0 ft^2  (reversal=11.2 ft/sec^2)
        maintain advised fpm until end
    '''
    name = 'TCAS RA Standard Response'
    units='fpm'
    
    def derive(self, tcas_ctl  =  M('TCAS Combined Control'), 
                     tcas_up   =  M('TCAS Up Advisory'), 
                     tcas_down =  M('TCAS Down Advisory'), 
                     tcas_vert =  M('TCAS Vertical Control'), 
                     vertspd   =  P('Vertical Speed'), 
                     ra_sections = S('TCAS RA Sections'), 
                     raduration  = KPV('TCAS RA Warning Duration'),
              ):
                    
        standard_vert_accel            =  8.0 * 60   #  8 ft/sec^2, converted to ft/min^2
        standard_vert_accel_reversal   = 11.2 * 60   # ft/sec^2 ==> ft/min^2
        standard_response_lag          =  5.0        # seconds
        standard_response_lag_reversal =  2.5        # seconds       
        self.array = vertspd.array * 0 #make a copy, mask and zero out
        self.array.mask = True
        required_fpm_array = vertspd.array * 0
        
        for ra in ra_sections:                      
            self.debug('TCAS RA Standard Response: in sections')
            #initialize response state
            ra_ctl_prev     = tcas_ctl.array[ra.start_edge] # used to check if the command has changed
            up_prev         = tcas_ctl.array[ra.start_edge] # used to check if the command has changed
            down_prev       = tcas_ctl.array[ra.start_edge] # used to check if the command has changed
            initial_vert_spd = vertspd.array[ra.start_edge]
            std_vert_spd    = initial_vert_spd # current standard response vert speed in fpm
            required_fpm    = None # nominal vertical speed in fpm required by the RA
            lag_end         = ra.start_edge + standard_response_lag # time pilot response lag ends
            acceleration    = standard_vert_accel
                        
            for t in range(int(ra.start_edge), int(ra.stop_edge)):               
                # set required_fpm for initial ra or a change in command
                if ra_ctl_prev!=tcas_ctl.array[t] or up_prev!=tcas_up.array[t] or down_prev!=tcas_down.array[t]:                        
                    if tcas_ctl.array[t] == 'Up Advisory Corrective':
                        required_fpm = tcas_vert_spd_up(tcas_up.array[t], vertspd.array[t], tcas_vert.array[t])                            
                    elif tcas_ctl.array[t] == 'Down Advisory Corrective':
                        required_fpm = tcas_vert_spd_down(tcas_down.array[t], vertspd.array[t], tcas_vert.array[t])
                    if tcas_vert.array[t]=='Reversal':                                                
                        lag_end = t + standard_response_lag_reversal
                        acceleration = standard_vert_accel_reversal                    
                        initial_vert_spd = std_vert_spd
                if required_fpm is None:
                    self.warning('TCAS RA Standard Response: No required_fpm found. Take a look!')                
                    pdb.set_trace()                        

                std_vert_spd= update_std_vert_spd(t, lag_end, tcas_ctl.array[t], acceleration, required_fpm, std_vert_spd)
                self.array.data[t] = std_vert_spd
                self.array.mask[t] = False
                required_fpm_array[t] = required_fpm
                ra_ctl_prev = tcas_ctl.array[t]
                up_prev     = tcas_up.array[t] 
                down_prev   = tcas_down.array[t]                
                #end of time loop within ra section
        return

    

def deltas(myarray):
    '''returns changes in value, same dimension as original array. 
        The first element is always set
    '''
    #pdb.set_trace()
    d=np.diff(myarray)
    delta = np.concatenate([ [0],d])
    return delta

def change_indexes(myarray):
    '''returns array indexes at which the delta was non-zero.
       intended for multi-state params.  Not tested for masking.
    '''
    return np.where( deltas(myarray)!=0 )[0]

###TODO try np.ediff1d(), use airborne or add simple phase to kpv
class TCASUpAdvisory(KeyPointValueNode):
    '''
       No Up Advisory
       Climb  
       Don't Descend> 500 
       Don't Descend> 1000 
       Don't Descend> 2000 
       Corrective 
    '''
    units = 'state'    
    
    def derive(self, tcas_up=M('TCAS Up Advisory'), airs=S('Airborne') ):
        _change_points = change_indexes(tcas_up.array.data) #returns array index
        print 'up', _change_points
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_up.array.data[cp]
            _name = 'TCAS Up Advisory|' + tcas_up.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)

class TCASDownAdvisory(KeyPointValueNode):
    '''
       No down advisory
       Descent
       Don't Climb> 500      
       Don't Climb> 1000     
       Don't Climb> 2000
       Corrective    # Boeing = Don't Climb > 2000
    '''
    units = 'state'    

    def derive(self, tcas_down=M('TCAS Down Advisory'), airs=S('Airborne') ):
        _change_points = change_indexes(tcas_down.array.data) #returns array index
        print 'down', _change_points
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_down.array.data[cp]
            _name = 'TCAS Down Advisory|' + tcas_down.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)
            
class TCASVerticalControl(KeyPointValueNode):
    '''
           Advisory is not one of the following types
           Crossing
           Reversal
           Increase
           Maintain    
    '''
    units = 'state'    

    def derive(self, tcas_vrt=M('TCAS Vertical Control'), airs=S('Airborne') ):
        _change_points = change_indexes(tcas_vrt.array.data) #returns array index
        print 'vert', _change_points
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_vrt.array.data[cp]
            _name = 'TCAS Vertical Control|' + tcas_vrt.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)


class TCASCombinedControl(KeyPointValueNode):
    ''' find tcas_ctl.array.data value changes (first diff)
        for each change point return a kpv using the control name. States:
          ( No Advisory, Clear of Conflict, Drop Track, Altitude Lost,
            Up Advisory Corrective, Down Advisory Corrective, Preventive )            
    '''
    units = 'state'    
    def derive(self, tcas_ctl=M('TCAS Combined Control'), airs=S('Airborne') ):
        _change_points = change_indexes(tcas_ctl.array.data) #returns array index
        for cp in _change_points:
            _value = tcas_ctl.array.data[cp]
            _name = 'TCAS Combined Control|' + tcas_ctl.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)

                                 
class TCASSensitivityAtTCASRAStart(KeyPointValueNode):
    name = 'TCAS RA Start Pilot Sensitivity Mode'
    def derive(self, tcas_sens=P('TCAS Sensitivity Level'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(tcas_sens.array, ra)


class TCASSensitivity(KeyPointValueNode):
    name = 'TCAS Pilot Sensitivity Mode'
    def derive(self, tcas_sens=P('TCAS Sensitivity Level'), airs=S('Airborne') ):
        _change_points = change_indexes(tcas_sens.array.data) #returns array index
        for cp in _change_points:
            _value = tcas_sens.array.data[cp]
            _name = 'TCAS Sensitivity|' + tcas_sens.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)


class VerticalSpeedAtTCASRAStart(KeyPointValueNode):
    units = 'fpm'
    name = 'TCAS RA Start Vertical Speed'
    def derive(self, vrt_spd=P('Vertical Speed'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(vrt_spd.array, ra)


class AltitudeQNHAtTCASRAStart(KeyPointValueNode):
    units = 'fpm'
    name = 'TCAS RA Start Altitude QNH'
    def derive(self, vrt_spd=P('Altitude QNH'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(vrt_spd.array, ra)


class PitchAtTCASRAStart(KeyPointValueNode):
    units = 'deg'
    name = 'TCAS RA Start Pitch'
    def derive(self, pitch=P('Pitch'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(pitch.array, ra)


class RollAtTCASRAStart(KeyPointValueNode):
    units = 'deg'
    name = 'TCAS RA Start Roll Abs'
    def derive(self, roll=P('Roll'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(np.abs(roll.array), ra)


class AutopilotAtTCASRAStart(KeyPointValueNode):
    '''1=Engaged, otherwise Disengaged'''
    name = 'TCAS RA Start Autopilot'
    def derive(self, ap=P('AP Engaged'), ra=KTI('TCAS RA Start')):
        #print 'AUTOPILOT'
        self.create_kpvs_at_ktis(ap.array, ra)



### Section 3: pre-defined test sets
def tiny_test():
    '''quick test set'''
    input_dir  = settings.BASE_DATA_PATH + 'tiny_test/'
    print input_dir
    files_to_process = glob.glob(os.path.join(input_dir, '*.hdf5'))
    return files_to_process


    
# we will probably need pairings of denominator set + event set.
def ra_denominator_superset():
    '''Used to find denominator. include all flights of interest,
            filtering on availability of required parameters.
            
       This could be a large set.  
       Intent is to run it rarely, and only for denominator kpv's.
       
       KPVs with additional dependencies will need to have their denominators
         further whittled down accordingly, so this is just a starting point.
        
       If fancy data quality filters are needed, those may need to be implemented
         within DataQuality or Denominator KPVs.
    '''
    query="""select distinct f.file_path 
                from fds_flight_record f 
                 where f.base_file_path is not null 
                   and recorded_parameters like '%TCAS Combined Control%'
          """
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return files_to_process


def ra_measure_set():
    '''Compute all metrics for these, looking only at flights with an RA.
         These calculations may be expensive, so we want a small set of flights to deal with.
    '''
    query="""select distinct f.file_path 
                from fds_flight_record f join fds_kpv kpv 
                  on kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and  (kpv.name='TCAS RA Warning Duration'
                         and kpv.value between 2.5 and 120.0                   
                       )  --ignore excessively long warnings
                   and (kpv.TIME_INDEX - f.LIFTOFF_MIN)>10.0  --starts at least 10 secs after liftoff
                   --and rownum<=2
                """
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return files_to_process
    
    
if __name__=='__main__':
    ###CONFIGURATION options###################################################
    FILES_TO_PROCESS = ra_measure_set() #test_ra_flights()  #test10() #tiny_test() #test_kpv_range() #test_sql_jfk() #
    COMMENT   = 'loaded from pkl and used updated lfl'
    LOG_LEVEL = 'WARNING'   #'WARNING' shows less, 'INFO' moderate, 'DEBUG' shows most detail
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
    