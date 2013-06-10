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
    ''' a phase, derived from other phases.  S()=section=phase'''
    name = 'TCAS RA Sections'
    def derive(self, tcas=M('TCAS Combined Control'), off=KTI('Liftoff') ):
        print 'HELLO from TCAS RA Sections'
        ras_local = tcas.array.any_of('Drop Track',
                                      'Altitude Lost',
                                      'Up Advisory Corrective',
                                      'Down Advisory Corrective')                    
        ras_slices = library.runs_of_ones(ras_local)
        if ras_slices:
            # require RA to start at least 10 seconds after liftoff 
            # also ignore flights with lots of cycling RA alerts
            is_post_liftoff =  (ras_slices[0].start - off.get_first().index) > 10 
            #is_too_long = 
            if is_post_liftoff and len(ras_slices)<5:
                print 'ra section', ras_slices
                for ra_slice in ras_slices:                    
                    duration = ra_slice.stop-ra_slice.start                     
                    #if 3.0 <= duration < 120.0:
                    print ' ra section', ra_slice
                    #pdb.set_trace()
                    self.create_phase( ra_slice )    
        return


class TCASRAStart(KeyTimeInstanceNode):
    name = 'TCAS RA Start'
    def derive(self, tcas=M('TCAS Combined Control'), off=KTI('Liftoff') ):
        ras_local = tcas.array.any_of('Drop Track',
                                      'Altitude Lost',
                                      'Up Advisory Corrective',
                                      'Down Advisory Corrective')                    
        ras_slices = library.runs_of_ones(ras_local)
        #pdb.set_trace()
        if ras_slices:
            # require RA to start at least 10 seconds after liftoff 
            # also ignore flights with lots of cycling RA alerts
            is_post_liftoff =  (ras_slices[0].start - off.get_first().index) > 10 
            #is_too_long = 
            if is_post_liftoff and len(ras_slices)<5:
                for ra_slice in ras_slices:
                    duration = ra_slice.start-ra_slice.stop 
                    if 3.0 <= duration < 120.0:
                        self.create_kti(ra_slice.start)

### TODO sort out Drop Track and Altitude 
### TODO check if Climb really means 1500 fpm regardless of circumstance
### TODO what if TCAS Vertical Control is Maintain; How does Vertical Control play with the others?
def tcas_vertical_speed_initial_up( ra_slice, tcas_up_initial, 
                                    vertical_speed_initial
                                   ):
    '''determine the change in vertical speed initially commanded  by a tcas ra 
            if TCAS combined control is Up Advisory
    '''
    upcmd = tcas_up_initial
    if upcmd=='Climb':
        return 1500  # climb at least 1500 fpm 
    elif upcmd=="Don't Descent 500":
        return -500  # don't descend more than 500 fpm
    elif upcmd=="Don't Descent 1000":
        return -1000
    elif upcmd=="Don't Descent 2000":
        return -2000
    elif upcmd=="Preventative":
        return vertical_speed_initial  #don't descend more than the current rate
    else: 
        return None
        

def tcas_vertical_speed_initial_down( ra_slice, tcas_down_initial, 
                                    vertical_speed_initial
                                   ):
    '''determine the change in vertical speed initially commanded  by a tcas ra
        if TCAS combined control is Down Advisory
    '''
    downcmd = tcas_down_initial
    if downcmd=='Descent':
        return -1500  #descent at least 1500 fpm 
    elif downcmd=="Don't Climb 500":
        return 500 #don't descend more than 500 fpm
    elif downcmd=="Don'Climb 1000":
        return 1000
    elif downcmd=="Don'Climb 2000":
        return 2000
    else: 
        return None

    
def aplot(array_dict={}, title='array plot', grid=True, legend=True):
    '''plot a dictionary of up to four arrays, with legend by default
        example dict:  {'Airspeed': airspeed.array }
    '''
    import matplotlib.pyplot as plt
    print 'title:', title
    if len(array_dict.keys())==0:
        print 'Nothing to plot!'
        return
    figure = plt.figure()
    figure.set_size_inches(10,5)
    series_names = array_dict.keys()[:4]  #only first 4
    series_formats = ['k','g','b','r']    #color codes
    for i,nm in enumerate(series_names):
        plt.plot(array_dict[nm], series_formats[i])
    if grid: plt.grid(True, color='gray')
    plt.title(title)
    if legend: plt.legend(series_names, 'upper left')
    plt.xlabel('time index')
    print 'Paused for plot review. Close plot window to continue.'
    plt.show()
    #plt.clf()
    plt.close()


def ra_plot(ra_section,     array_dict, 
            tcas_ctl_array, tcas_up_array, tcas_down_array, 
            vert_ctl_array, sens_array,    filename, orig, dest):
    '''plot tcas: vertical speed + controls    '''
    import matplotlib.pyplot as plt
    plt.figure(figsize=(15,15)) #set size in inches
    plt.subplots_adjust(left=None, bottom=None, right=None, top=None, wspace=None, hspace=0.5)
    
    # top time series plot
    axts    = plt.subplot2grid((8, 1), (0, 0), rowspan=3) #time series    
    series_names = array_dict.keys()[:4]  #only first 4
    series_formats = ['k','g','b','r']    #color codes
    for i,nm in enumerate(series_names):
        axts.plot(array_dict[nm], series_formats[i], alpha=0.3)
    leg = axts.legend(series_names, 'upper left', fancybox=True)
    leg.get_frame().set_alpha(0.5)
    axts.grid(True, color='gray')
    plt.title('Vertical Speed (fpm)')
    #plt.xlim(8300,8500)
    axts.set_xlim(xmin=8300) #failed
    axts.autoscale(enable=False)
    
    # combined control
    ax_ctl = plt.subplot2grid((8, 1), (3, 0), sharex=axts)     # 
    #states
    ctl_states = tcas_ctl_array.values_mapping.values()
    ctl_states = [s.replace('Advisory','Advzy').replace('Corrective', 'Corr.') for s in ctl_states]
    plt.yticks( np.arange(len(ctl_states)), ctl_states )
    # adjust data for display
    ctl_array = tcas_ctl_array.data 
    ax_ctl.plot(ctl_array, 'g')
    ax_ctl.grid(True, color='gray')
    plt.ylim(0, len(ctl_states)) 
    plt.title('TCAS Combined Control')

    # up and down advisory
    ax_updown   = plt.subplot2grid((8, 1), (4, 0), sharex=axts, rowspan=2)  
    # states
    up_states   = [' ']+tcas_up_array.values_mapping.values()
    down_states = [' ']+tcas_down_array.values_mapping.values()
    ud_states    = up_states + down_states
    
    def disp_state(st):
        st = st.replace('Descent Corrective','Desc Corr.')
        st = st.replace('Descent ','Desc>')
        st = st.replace('Descent','Descend')
        st = st.replace('Advisory','Advzy')
        st = st.replace("Don'Cl","Don't Cl")
        st = st.replace("Don't Climb ","Don't Climb>")
        return st

    ud_states = [ disp_state(s) for s in ud_states]
    plt.yticks( np.arange(len(ud_states)), ud_states )
    
    # adjust data for display
    up_array = tcas_up_array.data + 1
    ax_updown.plot(up_array, 'g')
    down_array = tcas_down_array.data + len(up_states)+1
    ax_updown.plot(down_array, 'r')
    ax_updown.grid(True, color='gray')
    plt.ylim(0, len(up_states) + len(down_states)) 
    plt.title('TCAS Up/Down Advisory')
    
    # vertical control
    ax_vert   = plt.subplot2grid((8, 1), (6, 0), sharex=axts)  
    # states
    vert_states   = vert_ctl_array.values_mapping.values()    
    vert_states = [' ']+[s.replace("Advisory is not one of the following types",'NA') for s in vert_states]
    plt.yticks( np.arange(len(vert_states)), vert_states )
    #adjust data for display
    vert_array = vert_ctl_array.data + 1
    ax_vert.plot(vert_array, 'g')   
    ax_vert.grid(True, color='gray')
    plt.ylim(0, len(vert_states)) 
    plt.title('TCAS Vertical Control')
    
    #pdb.set_trace()

    #sensitivity mode    
    ax_sens   = plt.subplot2grid((8, 1), (7, 0), sharex=axts)  
    # states
    sens_states   = sens_array.values_mapping.values()    
    sens_states = [' ']+[s.replace("SL = ",'') for s in sens_states]
    plt.yticks( np.arange(len(sens_states)), sens_states )
    #adjust data for display
    sens_arr = sens_array.data + 1
    ax_sens.plot(sens_arr, 'g')   
    ax_sens.grid(True, color='gray')
    plt.ylim(0, len(sens_states)) 
    plt.title('TCAS Sensitivity Mode')
    
    plt.xlabel('time index')
    xmin = max( ra_section.start_edge-30.0, 0)   
    xmax = min( ra_section.stop_edge+30.0, len(vert_array)) 
    plt.xlim(xmin, xmax) 
    plt.suptitle('TCAS RA: '+filename.value + '\n  '+orig.value['code']['icao']+'-'+dest.value['code']['icao'])
    return plt
    
    
### TODO deal with reversals later
class TCASRAStandardResponse(DerivedParameterNode):
    '''nominal pilot response -- a vertical speed curve
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
                     tcas_sens =  M('TCAS Sensitivity Level'), 
                     vertspd   =  P('Vertical Speed'), 
                     ra_sections = S('TCAS RA Sections'), 
                     raduration  = KPV('TCAS RA Warning Duration'),
                     filename    = A('Myfile'),
                     orig = A('FDR Takeoff Airport'),
                     dest = A('FDR Landing Airport'),
              ):
                    
        standard_vert_accel = 8.0  # ft/sec^2
        self.array = vertspd.array * 0 #make a copy, mask and zero out

        self.array.mask = True
        for ra in ra_sections:                      
            print 'in sections'
            #find corresponding raduration
            #pdb.set_trace()
            duration = ra.stop_edge-ra.start_edge
            if duration<5.0:   #no response: vert speed does not change from starting value
                self.array[ra] = vertspd[ra.start]
            else:  #spd unchanged first five seconds, then ramps up as 8 ft/sec^2 to target
                self.array[ra.start_edge:ra.start_edge+5] = vertspd.array[ra.start_edge]
                post_response_duration = duration - 5.0
                if tcas_ctl.array[ra.start_edge] == 'Up Advisory Corrective':
                    required_fpm = tcas_vertical_speed_initial_up( ra.slice, 
                                                tcas_up.array[ra.start_edge], 
                                                vertspd.array[ra.start_edge]
                                                )
                    print 'UP required:', required_fpm 
                    #NEXT : loop over ra period.  increment speed until we hit target, then level off
                    print 'UP required:', required_fpm
                    seconds_for_change = required_fpm / standard_vert_accel
                    seconds_of_accel = min(seconds_for_change, post_response_duration)
                    #seconds_at_target_fpm
                    #if post_response_duration < seconds_for_change:
                    #    pass #we don't have enough time to hit the target, just accel for

                elif tcas_ctl.array[ra.start_edge] == 'Down Advisory Corrective':
                    required_fpm = tcas_vertical_speed_initial_down( ra.slice, 
                                                tcas_down.array[ra.start_edge], 
                                                vertspd.array[ra.start_edge]
                                                )
                    print 'DOWN required:', required_fpm 
                    seconds_for_change = required_fpm / standard_vert_accel
                
                else:
                    required_fpm = 0
                    print 'I am very CONFUSED by this RA!!!'
            required_fpm_array = vertspd.array * 0
            required_fpm_array[ra.slice] = required_fpm  
            #mytitle = 'TCAS response. Cmb Ctl: '+tcas_ctl.array[ra.start_edge] + ' Up: '+ tcas_up.array[ra.start_edge] + ' Down: '+tcas_down.array[ra.start_edge]
            #aplot({'vertspd':vertspd.array, 'tcas100':tcas_ctl.array*100-25, 'required fpm':required_fpm}, title=mytitle)
            """    
            plt = ra_plot(ra, {'vertspd':vertspd.array, 'required fpm':required_fpm_array}, 
                    tcas_ctl.array, tcas_up.array, tcas_down.array, 
                    tcas_vert.array, tcas_sens.array, filename, orig, dest)  

            #print 'Paused for plot review. Close plot window to continue.'
            #plt.show()            
            plt.draw()
            fname = filename.value.replace('.hdf5', '.png')
            plt.savefig(fname, transparent=False ) #, bbox_inches="tight")
            plt.close()
            """    

def deltas(myarray):
    '''returns changes in value, same dimension as original array. 
        The first element is always 0
    '''
    d=np.diff(myarray)
    delta = np.concatenate([[0],d])
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
    '''a simple KPV. start_datetime is used only to provide a dependency
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
    '''
        find tcas_ctl.array.data value changes (first diff)
        for each change point return a kpv using the control name

       No Advisory
       Clear of Conflict
       Drop Track
       Altitude Lost
       Up Advisory Corrective
       Down Advisory Corrective
       Preventive
    '''
    units = 'state'    

    def derive(self, tcas_ctl=M('TCAS Combined Control'), airs=S('Airborne') ):
        #for air in airs:
        #    ctl = tcas_ctl.array[air.slice]
            
        _change_points = change_indexes(tcas_ctl.array.data) #returns array index
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_ctl.array.data[cp]
            _name = 'TCAS Combined Control|' + tcas_ctl.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)
                                 
class TCASSensitivityAtTCASRAStart(KeyPointValueNode):
    name = 'TCAS RA Start Pilot Sensitivity Mode'
    def derive(self, tcas_sens=P('TCAS Sensitivity Level'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(tcas_sens.array, ra)

"""
class TCASSensitivity(KeyPointValueNode):
    name = 'TCAS Pilot Sensitivity Mode'
    def derive(self, tcas_sens=P('TCAS Sensitivity Level'), airs=S('Airborne') ):
        _change_points = change_indexes(tcas_sens.array.data) #returns array index
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_sens.array.data[cp]
            _name = 'TCAS Sensitivity|' + tcas_sens.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)
"""

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
                    orig_icao='KJFK' and dest_icao in ('KFLL','KMCO' )"""
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return files_to_process

def ra_pkl_check():
   '''verify tcas profile using flights from updated LFL and load from pkl'''   
   query="""select distinct f.file_path 
                from (select * from fds_flight_record where file_path like '%2012-07-11%' and analysis_time>to_date('2013-06-08 13:00','YYYY-MM-DD HH24:MI')) f 
                join 
                 fds_kpv kpv 
                  on kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and  f.base_file_path like '%cleansed%' 
                   and  (kpv.name='TCAS RA Warning Duration'
                         and kpv.value between 2.5 and 120.0                   
                       )  --ignore excessively long warnings
                   and (kpv.TIME_INDEX - f.LIFTOFF_MIN)>10.0  --starts at least 10 secs after liftoff
                   --and rownum<=2"""
   files_to_process = fds_oracle.flight_record_filepaths(query)
   return files_to_process


def test_ra_flights():
    '''look only at flights with an RA'''
    query="""select distinct f.file_path 
                from fds_flight_record f join fds_kpv kpv 
                  on kpv.base_file_path=f.base_file_path
                 where f.base_file_path is not null 
                   and  f.base_file_path like '%cleansed%' 
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
    FILES_TO_PROCESS = ra_pkl_check() #test_ra_flights()  #test10() #tiny_test() #test_kpv_range() #test_sql_jfk() #
    COMMENT   = 'loaded from pkl and used updated lfl'
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
    