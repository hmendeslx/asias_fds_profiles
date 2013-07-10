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
        Airspeed        --        this
        Altitude        --        this: 'TCAS RA Start Altitude QNH'   = AltitudeQNHAtTCASRAStart()
        AP              --        this: 'TCAS RA Start Autopilot'      = AutopilotAtTCASRAStart()
        Pitch           --        this: 'TCAS RA Start Pitch'          = PitchAtTCASRAStart()
        Roll            --        this: 'TCAS RA Start Roll'           = RollAtTCASRAStart()
    Change in state during RA?    ignore: 'Heading Increase'             = absolute change
    How did pilot respond?        base: 'TCAS RA Reaction Delay' (uses normal acceleration)
        disengage AP?             this: 'TCAS RA To AP Disengaged Duration'
                                  base: 'TCAS RA Initial Reaction Strength' (positive if alt change consistent with RA)
        altitude exceedance       this:  comparison of actual response to FAA standard RA response

NOTE: we are assuming 1 Hz TCAS Combined Control
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
                                   S,   SectionNode,  FlightPhaseNode,      # Sections=Phases
                                   KeyPointValue, KeyTimeInstance, Section  # data records, a list of which goes into the corresponding node
                                 )
# A Node is a list of items.  Each item type is a class with the fields listed below:
#   FlightAttribute = name, value.  could be a scolor or a collection, e.g. list or dict
#   ApproachItem    = recordtype('ApproachItem',    'type slice airport runway gs_est loc_est ils_freq turnoff lowest_lat lowest_lon lowest_hdg', default=None)  
#   KeyTimeInstance = recordtype('KeyTimeInstance', 'index name datetime latitude longitude', default=None)
#   Section = namedtuple('Section',                  'name slice start_edge stop_edge')   #=Phase
#   KeyPointValue   = recordtype('KeyPointValue', '  index value name slice datetime latitude longitude', field_defaults={'slice':slice(None)}, default=None)
                            
import analysis_engine.library as library
# asias_fds stuff
import analyser_custom_settings as settings
import staged_helper  as helper 
import fds_oracle

   
### Section 2: measure definitions -- attributes, KTI, phase/section, KPV, DerivedParameter
#      DerivedParameters will cause a set of hdf5 files to be generated.

class TCASCtlSections(FlightPhaseNode):  # OLD VERSION 
    '''TCAS RA sections that pass quality filtering '''
    name = 'TCAS Ctl Sections'
    def derive(self, tcas=M('TCAS Combined Control') ): #, off=KTI('Liftoff'), td=KTI('Touchdown') ):
        ras_local = tcas.array.any_of('Drop Track', 'Altitude Lost', 'Up Advisory Corrective','Down Advisory Corrective')                    
        ras_slices = library.runs_of_ones(ras_local)
        if ras_slices:
            for ra_slice in ras_slices:                    
                self.create_phase( ra_slice )    
        return


class TCASRAStart(KeyTimeInstanceNode):
    name = 'TCAS RA Start'
    def derive(self, ra_sections=S('TCAS RA Sections')):
        for s in ra_sections:
            self.create_kti(s.start_edge)


class TCASRASections(FlightPhaseNode):
    name = 'TCAS RA Sections'
    def derive(self, ra=M('TCAS RA'), off=KTI('Liftoff'), td=KTI('Touchdown') ):
        ras_local = ra.array
        ras_slices = library.runs_of_ones(ras_local)
        
        # put together runs separated by short drop-outs        
        ras_slicesb = library.slices_remove_small_gaps(ras_slices, time_limit=2, hz=1)        
        for ra_slice in ras_slicesb:                    
            is_post_liftoff =  (ra_slice.start - off.get_first().index) > 10 
            is_pre_touchdown = (td.get_first().index - ra_slice.start ) > 10 
            duration = ra_slice.stop-ra_slice.start                     
            if is_post_liftoff and is_pre_touchdown  and 3.0 <= duration < 300.0: #ignore if too short to do anything
                #print ' ra section', ra_slice
                self.create_phase( ra_slice )    
        return



def tcas_vert_spd_up(tcas_up, vert_speed, tcas_vert):
    '''determine the change in vertical speed commanded  by a tcas ra 
            if TCAS combined control is Up Advisory
    '''
    upcmd = tcas_up
    if upcmd=='Climb':
        if tcas_vert=="Increase":            
            return 2500  
        else:
            return 1500
    elif upcmd == "Don't Descend":
        return 0
    elif upcmd.endswith(" 500"):
        return -500  # don't descend more than 500 fpm
    elif upcmd.endswith("1000"):
        return -1000
    elif upcmd.endswith("2000"):
        return -2000
    elif upcmd.endswith('Corrective'): #temp hack pending full remapping
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
            return -2500  
        else:
            return -1500
    elif downcmd == "Don't Climb":
        return 0
    elif downcmd.endswith(" 500"):
        return 500 #don't descend more than 500 fpm
    elif downcmd.endswith("1000"):
        return 1000
    elif downcmd.endswith("2000"):
        return 2000
    elif downcmd.endswith('Corrective'): #temp hack pending full remapping
        return 2000
    else: 
        print 'Other initial down: ', tcas_down
        return None


def update_std_vert_spd(t, lag_end, cmb_ctl, up, down, acceleration, required_fpm, 
                        std_vert_spd, init_vert_spd, vert_spd):
    new_std_vert_spd = std_vert_spd    
    if cmb_ctl in ('Clear of Conflict','No Advzy'):
        new_std_vert_spd = vert_spd
    elif t<lag_end: # not responding yet
        new_std_vert_spd = init_vert_spd
    elif cmb_ctl == 'Down Advisory Corrective' or down.lower()!='no down advisory':
        if std_vert_spd>required_fpm: 
            new_std_vert_spd = std_vert_spd - acceleration            
        if new_std_vert_spd<=required_fpm: 
            new_std_vert_spd = required_fpm #correct overshoot
    elif cmb_ctl == 'Up Advisory Corrective'  or up.lower()!='no up advisory':
        if std_vert_spd<required_fpm: 
            new_std_vert_spd = std_vert_spd + acceleration
        if new_std_vert_spd>=required_fpm: 
            new_std_vert_spd = required_fpm #correct overshoot
    elif cmb_ctl in ('Preventive', 'Drop Track', 'Altitude Lost'):
        new_std_vert_spd = std_vert_spd
    else: #better have a look
        print 'RA Std Response Unknown: ', t, cmb_ctl
        new_std_vert_spd = vert_spd
    return new_std_vert_spd


def plot_mapped_array(plt, myaxis, states, mapped_array, title="", series_format="g"):
    '''MappedArray maps discrete states to an integer array.
       Here we plot the states as a time series with states labelled on the y axis.'''
    plt.yticks( np.arange(len(states)), states )
    myaxis.plot(mapped_array, 'g')
    myaxis.grid(True, color='gray')
    plt.ylim(0, len(states)) 
    plt.title(title)

    
def ra_plot(array_dict, tcas_ra_array, tcas_ctl_array, tcas_up_array, tcas_down_array, 
            vert_ctl_array, sens_array, filename, orig, dest, tstart, tend):
    '''plot tcas: vertical speed + controls    '''
    import matplotlib.pyplot as plt
    from matplotlib.ticker import ScalarFormatter 
    formatter = ScalarFormatter(useOffset=False) 
    formatter.set_powerlimits((-8,8)) 
    formatter.set_scientific(False) 
    formatter.set_useOffset(0.0) 

    plt.figure(figsize=(15,15)) #set size in inches
    plt.subplots_adjust(left=None, bottom=None, right=None, top=None, wspace=None, hspace=0.5)
    
    # top time series plot
    axts    = plt.subplot2grid((8, 1), (0, 0), rowspan=2) #time series    
    axts.xaxis.set_major_formatter(formatter) 
    series_names = array_dict.keys()  #only first 4
    series_formats = ['k','r','g','b']    #color codes
    for i,nm in enumerate(series_names):
        ln=axts.plot(array_dict[nm], series_formats[i], alpha=0.45)
        plt.setp(ln, linewidth=2)
    leg = axts.legend(series_names, 'upper left', fancybox=True)
    leg.get_frame().set_alpha(0.5)
    axts.grid(True, color='gray')
    plt.title('Vertical Speed (fpm)')
    axts.autoscale(enable=False)
    
    # tcas ra
    ax_ra = plt.subplot2grid((8, 1), (2, 0), sharex=axts)     # 
    ra_states = tcas_ra_array.values_mapping.values()
    ra_states = [s.replace('Most Dangerous','') for s in ra_states]
    ra_array = tcas_ra_array.data 
    plot_mapped_array(plt, ax_ra, ra_states, ra_array, title="TCAS RA")

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
        st = st.replace('Advisory','Advzy').replace('advisory','Advzy')
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
    plt.suptitle('TCAS RA: '+filename.value + '\n  '+orig.value['code']['icao']+'-'+dest.value['code']['icao']+ ' '+str(tstart)+':'+str(tend))
    return plt
    

#"""
class TCASRAResponsePlot(DerivedParameterNode):
    '''dummy node for diagnostic plotting '''
    name = "TCAS RA Response Plot"
    def derive(self, std_vert_spd = P('TCAS RA Standard Response'), 
                     tcas_ra   =  M('TCAS RA'),                      
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
            plt = ra_plot({'vertspd':vertspd.array, 'std response':std_vert_spd.array}, 
                      tcas_ra.array, tcas_ctl.array, tcas_up.array, tcas_down.array, 
                      tcas_vert.array, tcas_sens.array, filename, orig, dest,
                      tstart, tend
                      )  
            #helper.show_plot(plt)                      
            fname = filename.value.replace('.hdf5', '.png')
            helper.save_plot(plt, fname)
        self.array = std_vert_spd.array
        print 'finishing', filename
        return
#"""

class TCASAltitudeExceedance(KeyPointValueNode):
    '''Actual vs Standard Response.  Assumes 1 hz params'''
    name = 'TCAS RA Altitude Exceedance'
    def derive(self, ra_sections=S('TCAS RA Sections'),  tcas_ctl=M('TCAS Combined Control'),
                     tcas_up   =  M('TCAS Up Advisory'), tcas_down =  M('TCAS Down Advisory'), 
                     std=P('TCAS RA Standard Response'), vertspd=P('Vertical Speed') ):
        for ra in ra_sections:
            exceedance=0
            deviation=0
            for t in range(int(ra.start_edge), int(ra.stop_edge)): 
                if tcas_ctl.array[t] == 'Down Advisory Corrective' or tcas_down.array[t].lower()!='no down advisory':
                    deviation =  max(vertspd.array[t] - std.array[t], 0)
                elif tcas_ctl.array[t] == 'Up Advisory Corrective' or tcas_up.array[t].lower()!='no up advisory':
                    deviation =  max(std.array[t] - vertspd.array[t], 0)
                else:
                    deviation = abs(vertspd.array[t] - std.array[t])
                    deviation = max( deviation-250, 0 ) # allow 250 fpm buffer
                #print 't vert std DEV', t, vertspd.array[t], std.array[t], deviation
                if deviation and deviation!=0:
                    exceedance += deviation
            #print 'Alt Exceed', exceedance
            exceedance = exceedance / 60.0 # min to sec
            self.create_kpv(ra.start_edge, exceedance)


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
                        
            for t in range(int(ra.start_edge), int(ra.stop_edge)+1):               
                # set required_fpm for initial ra or a change in command
                if ra_ctl_prev!=tcas_ctl.array[t] or up_prev!=tcas_up.array[t] or down_prev!=tcas_down.array[t]:                        
                    if tcas_ctl.array[t] == 'Up Advisory Corrective' or tcas_up.array[t].lower()!='no up advisory':
                        required_fpm = tcas_vert_spd_up(tcas_up.array[t], vertspd.array[t], tcas_vert.array[t])                            
                    elif tcas_ctl.array[t] == 'Down Advisory Corrective'  or tcas_down.array[t].lower()!='no down advisory':
                        required_fpm = tcas_vert_spd_down(tcas_down.array[t], vertspd.array[t], tcas_vert.array[t])
                    else:
                        required_fpm = vertspd.array[t]
                    if tcas_vert.array[t]=='Reversal':                                                
                        lag_end = t + standard_response_lag_reversal
                        acceleration = standard_vert_accel_reversal                    
                        initial_vert_spd = std_vert_spd
                if required_fpm is None:
                    self.warning('TCAS RA Standard Response: No required_fpm found. Take a look! '+str(t))                

                std_vert_spd= update_std_vert_spd(t, lag_end, tcas_ctl.array[t], tcas_up.array[t], tcas_down.array[t],
                                                  acceleration, required_fpm, 
                                                  std_vert_spd, initial_vert_spd, vertspd.array[t])
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
    d=np.diff(myarray)
    delta = np.concatenate([ [0],d])
    return delta

def change_indexes(myarray):
    '''returns array indexes at which the delta was non-zero.
       intended for multi-state params.  Not tested for masking.
    '''
    return np.where( deltas(myarray)!=0 )[0]


class TCASCombinedControl(KeyPointValueNode):
    ''' find tcas_ctl.array.data value changes (first diff)
        for each change point return a kpv using the control name. States:
          ( No Advisory, Clear of Conflict, Drop Track, Altitude Lost,
            Up Advisory Corrective, Down Advisory Corrective, Preventive )            
    '''
    units = 'state'    
    def derive(self, tcas_ctl=M('TCAS Combined Control'), ra_sections = S('TCAS RA Sections') ):
        _change_points = change_indexes(tcas_ctl.array.data) #returns array index
        for cp in _change_points:
            _value = tcas_ctl.array.data[cp]
            if tcas_ctl.array.mask[cp]:
                _name = 'TCAS Combined Control|masked'
            else:
                _name = 'TCAS Combined Control|' + tcas_ctl.array[cp]
            if cp>0 and _value and _name:
                kpv = KeyPointValue(index=cp, value=_value, name=_name)
                self.append(kpv)


###TODO try np.ediff1d(), use airborne or add simple phase to kpv
class TCASUpAdvisory(KeyPointValueNode):
    units = 'state'        
    def derive(self, tcas_up=M('TCAS Up Advisory'), ra_sections=S('TCAS RA Sections') ):
        _change_points = change_indexes(tcas_up.array.data) #returns array index
        print 'up', _change_points
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_up.array.data[cp]
            if tcas_up.array.mask[cp]:
                _name = 'TCAS Up Advisory|masked'
            else:
                _name = 'TCAS Up Advisory|' + tcas_up.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)


class TCASDownAdvisory(KeyPointValueNode):
    units = 'state'    
    def derive(self, tcas_down=M('TCAS Down Advisory'), ra_sections = S('TCAS RA Sections') ):
        _change_points = change_indexes(tcas_down.array.data) #returns array index
        print 'down', _change_points
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_down.array.data[cp]
            if tcas_down.array.mask[cp]:
                _name = 'TCAS Down Advisory|masked'
            else:
                _name = 'TCAS Down Advisory|' + tcas_down.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)
            
            
class TCASVerticalControl(KeyPointValueNode):
    '''Advisory is one of the following types
           Crossing
           Reversal
           Increase
           Maintain    
    '''
    units = 'state'    
    def derive(self, tcas_vrt=M('TCAS Vertical Control'), ra_sections = S('TCAS RA Sections')):
        _change_points = change_indexes(tcas_vrt.array.data) #returns array index
        print 'vert', _change_points
        for cp in _change_points:
            #pdb.set_trace()
            _value = tcas_vrt.array.data[cp]
            if tcas_vrt.array.mask[cp]:
                _name = 'TCAS Vertical Control|masked'
            else:
                _name = 'TCAS Vertical Control|' + tcas_vrt.array[cp]
            kpv = KeyPointValue(index=cp, value=_value, name=_name)
            self.append(kpv)

                                 
class TCASSensitivityAtTCASRAStart(KeyPointValueNode):
    name = 'TCAS RA Start Pilot Sensitivity Mode'
    def derive(self, tcas_sens=P('TCAS Sensitivity Level'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(tcas_sens.array, ra)


class TCASSensitivity(KeyPointValueNode):
    name = 'TCAS Pilot Sensitivity Mode'
    def derive(self, tcas_sens=P('TCAS Sensitivity Level'), ra_sections=S('TCAS RA Sections') ):
        _change_points = change_indexes(tcas_sens.array.data) #returns array index
        for cp in _change_points:
            _value = tcas_sens.array.data[cp]
            if tcas_sens.array.mask[cp]:
                _name = 'TCAS Sensitivity|masked'
            else:
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


class AirspeedAtTCASRAStart(KeyPointValueNode):
    units = 'kts'
    name = 'TCAS RA Start Airspeed'
    def derive(self, airspeed=P('Airspeed'), ra=KTI('TCAS RA Start')):
        self.create_kpvs_at_ktis(np.abs(airspeed.array), ra)


class AutopilotAtTCASRAStart(KeyPointValueNode):
    '''1=Engaged, otherwise Disengaged'''
    name = 'TCAS RA Start Autopilot'
    def derive(self, ap=P('AP Engaged'), ra=KTI('TCAS RA Start')):
        #print 'AUTOPILOT'
        self.create_kpvs_at_ktis(ap.array, ra)


class TCASRATimeToAPDisengage(KeyPointValueNode):
    '''adapted from FDS 'TCAS RA To AP Disengaged Duration', but uses TCAS RA Start'''
    name = 'TCAS RA Time To AP Disengage'
    units = 's'
    def derive(self, ap_offs=KTI('AP Disengaged Selection'), ras=S('TCAS RA Sections') ):
        for ra_section in ras:
            ra = ra_section.slice
            ap_off = ap_offs.get_next(ra.start, within_slice=ra)
            if not ap_off:
                continue
            index = ap_off.index
            duration = (index - ra.start) / self.frequency
            self.create_kpv(index, duration)


### Section 3: pre-defined test sets
def tiny_test():
    '''quick test set'''
    input_dir  = settings.BASE_DATA_PATH + 'tiny_test/'
    print input_dir
    files_to_process = glob.glob(os.path.join(input_dir, '*.hdf5'))
    repo='keith PC'
    return repo, files_to_process


def ra_sfo_sweep():
    '''Compute all metrics for these, looking only at flights with an RA.
         These calculations may be expensive, so we want a small set of flights to deal with.
    '''
    repo = 'central'
    query="""select distinct f.file_path 
                from fds_flight_record f 
                 where  f.file_repository='REPO' 
                   and f.base_file_path is not null 
                   and f.start_month between to_date('2012-04-01','YYYY-MM-DD') and to_date('2012-06-30','YYYY-MM-DD')
                   and F.DEST_ICAO='KSFO' 
                """.replace('REPO',repo)
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return repo, files_to_process

def ra_all_sweep():
    '''check all flights for 'TCAS RA' to capture additional RAs    '''
    repo = 'central'
    query="""select distinct f.file_path 
                from fds_flight_record f 
                 where  f.file_repository='REPO' 
                   and f.base_file_path is not null 
                   and f.start_month between to_date('2012-04-01','YYYY-MM-DD') and to_date('2012-06-30','YYYY-MM-DD')
                """.replace('REPO',repo)
    files_to_process = fds_oracle.flight_record_filepaths(query)
    return repo, files_to_process

def ra_redo():
    '''update tcas_keith profile using new RA detection -- shortcut by using output from all_sweep'''
    repo = 'central'
    query="""select distinct f.file_path 
            from fds_flight_record f join fds_phase ph
              on ph.base_file_path=f.base_file_path
            where  f.file_repository='central'
                   and ph.profile='all_sweep-MM191123-PC'
                   and ph.name in ( 'TCAS RA Sections' )
                   and f.start_month >= to_date('2012-04-01','YYYY-MM-DD') 
                   and f.start_month <= to_date('2012-06-30','YYYY-MM-DD')
                   and ph.time_index<touchdown_min
                   and ph.time_index>liftoff_min
                   and ph.duration>2.5 and ph.duration<300
            group by f.file_path
            """
    files_to_process = fds_oracle.flight_record_filepaths(query)
    #files_to_process =  [ f for f in files_to_process if ('N563JB' in f)]
    return repo, files_to_process


if __name__=='__main__':
    ###CONFIGURATION options###################################################
    PROFILE_NAME = 'tcas_keith'  + '-'+ socket.gethostname()   
    FILE_REPOSITORY, FILES_TO_PROCESS = ra_redo() #ra_all_sweep() #ra_measure_set_central() #ra_measure_set_sfo() #tiny_test() #ra_measure_set(FILE_REPOSITORY) #test_ra_flights(FILE_REPOSITORY)  #test10() #tiny_test() 
    COMMENT   = 'recalc all using series TCAS RA instead of Combined Control'
    LOG_LEVEL = 'WARNING'   #'WARNING' shows less, 'INFO' moderate, 'DEBUG' shows most detail
    MAKE_KML_FILES=False    # Run times are much slower when KML is True
    ###########################################################################
    
    module_names = [ os.path.basename(__file__).replace('.py','') ] #helper.get_short_profile_name(__file__)   # profile name = the name of this file
    print 'profile', PROFILE_NAME 
    helper.run_profile(PROFILE_NAME , module_names, LOG_LEVEL, FILES_TO_PROCESS, COMMENT, MAKE_KML_FILES, FILE_REPOSITORY )

