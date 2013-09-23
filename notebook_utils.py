"""
notebook_utils.py  -- import notebook_utils as nb
interactive utilities for profile development using ipython notebook
Created on Thu Aug 15 08:13:59 2013

@author: KEITHC
"""
from __future__ import division
import types
import inspect
import logging
import datetime, time, calendar

import numpy  as np
from numpy import NaN
import pandas as pd
import pylab
import networkx as nx

import analysis_engine
import analysis_engine.node as node
import hdfaccess.file
from analysis_engine import settings

import analyser_custom_settings
import staged_helper  as helper  
from staged_helper import Flight, get_deps_series

FFD_DIR=analyser_custom_settings.FFD_PATH
ffd_master = pd.read_csv(FFD_DIR+'FFDparameters.txt',sep='\t')
ffd_master.index = ffd_master['DISPLAY_NAME']


def derive_many(flight, myvars, precomputed={}):
    '''simplified signature for deriving all nodes in a profile
        flt is an object of class Flight
        myvars normally=vars()
        precomputed is a dict of previously computed nodes
    '''
    node_mgr = get_profile_nodemanager(flight, myvars)
    process_order, graph = helper.dependency_order(node_mgr, draw=False)
    res, params = helper.derive_parameters_series(flight, node_mgr, process_order, precomputed={})
    return params
    

def derive_one(flight, parameter_class, precomputed={}):
    '''Pass in a single profile parameter node class to derive
       sample call:  node_graph(SimpleKPV)'''
    single_request = {parameter_class.__name__: parameter_class }
    
    # full set of computable nodes
    base_nodes = helper.get_derived_nodes(settings.NODE_MODULES)
    all_nodes = base_nodes.copy()
    for k,v in single_request.items():
        all_nodes[k]=v
    for k,v in flight.series.items():  #flight.series.items():
        all_nodes[k]=v
    
    single_mgr = node.NodeManager( flight.start_datetime, 
                        flight.duration, 
                        flight.series.keys(),  
                        single_request.keys(), 
                        all_nodes, 
                        flight.aircraft_info,
                        achieved_flight_record={'Myfile': flight.filepath, 'Mydict':dict()}
                      )
    single_order, single_graph = helper.dependency_order(single_mgr, draw=False)
    res, params= helper.derive_parameters_series(flight, single_mgr, single_order, precomputed={})    
    return params


def get_profile_nodes(myvars):
    ''' returns a dictionary of node classnames and class objects
        eg get_profile_nodes(vars())
    '''
    derived_nodes = {}
    nodelist =[(k,v) for (k,v) in myvars.items() if inspect.isclass(v) and issubclass(v,node.Node) and v.__module__ != 'analysis_engine.node']
    for k,v in nodelist:
        derived_nodes[k] = v
    return derived_nodes


def get_profile_nodemanager(flt, myvars):
    '''return a NodeManager for the current flight and profile definition
         normally myvars will be set myvars=vars() from a notebook    
    '''
    # full set of computable nodes
    requested_nodes = get_profile_nodes(myvars)  # get Nodes defined in the current namespace
    all_nodes = helper.get_derived_nodes(settings.NODE_MODULES)  #all the FDS derived nodes
    for k,v in requested_nodes.items():  # nodes in this profile
        all_nodes[k]=v
    for k,v in flt.series.items():  #hdf5 series
        all_nodes[k]=v
        
    node_mgr = node.NodeManager( flt.start_datetime, 
                        flt.duration, 
                        flt.series.keys(), #ff.valid_param_names(),  
                        requested_nodes.keys(), 
                        all_nodes, # computable
                        flt.aircraft_info,
                        achieved_flight_record={'Myfile':flt.filepath, 'Mydict':dict()}
                      )
    return node_mgr
    

def get_base_nodemanager(flt):
    '''return a NodeManager for the current Flight object and profile definition
         normally myvars will be set myvars=vars() from a notebook    
    '''
    # full set of computable nodes
    all_nodes = helper.get_derived_nodes(settings.NODE_MODULES)  #all the FDS derived nodes
    requested_nodes = all_nodes.copy()  # get Nodes defined in the current namespace
    if requested_nodes.get('Configuration'):
        del requested_nodes['Configuration']
    for k,v in flt.series.items():  #hdf5 series
        all_nodes[k]=v
        
    node_mgr = node.NodeManager( flt.start_datetime, 
                        flt.duration, 
                        flt.series.keys(), #ff.valid_param_names(),  
                        requested_nodes.keys(), 
                        all_nodes, # computable
                        flt.aircraft_info,
                        achieved_flight_record={'Myfile':flt.filepath, 'Mydict':dict()}
                      )
    return node_mgr


def graph_show(graph, font_size=12):
    pylab.rcParams['figure.figsize'] = (16.0, 12.0)
    try:
        nx.draw_networkx(graph,pos=nx.spring_layout(graph), node_size=6, alpha=0.1, font_size=font_size)
    except:
        print 'umm'
    pylab.rcParams['figure.figsize'] = (10.0, 4.0)
    
    
def graph_many_nodes(flt, myvars, font_size=12):
    node_mgr = get_profile_nodemanager(flt, myvars)
    process_order, graph = helper.dependency_order(node_mgr, draw=False)   
    graph_show(graph, font_size=12)
    

def graph_one_node(parameter_class, flight):
    '''Pass in a profile parameter node class to view its dependency graph
       sample call:  node_graph(SimpleKPV)'''
    single_request = {parameter_class.__name__: parameter_class }
    
    # full set of computable nodes
    base_nodes = helper.get_derived_nodes(settings.NODE_MODULES)
    all_nodes = base_nodes.copy()
    for k,v in single_request.items():
        all_nodes[k]=v
    for k,v in flight.series.items():
        all_nodes[k]=v
        
    single_mgr = node.NodeManager( flight.start_datetime, 
                        flight.duration, 
                        flight.series.keys(),  
                        single_request.keys(), 
                        all_nodes, 
                        flight.aircraft_info,
                        achieved_flight_record={'Myfile':flight.filepath, 'Mydict':dict()}
                      )
    single_order, single_graph = helper.dependency_order(single_mgr, draw=False)
    graph_show(single_graph, font_size=12) 
  

def initialize_logger(LOG_LEVEL, filename='log_messages.txt'):
    '''all stages use this common logger setup'''
    logger = logging.getLogger()
    #logger = initialize_logger(LOG_LEVEL)
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(logging.FileHandler(filename=filename)) #send to file 
    logger.addHandler(logging.StreamHandler())                #tee to screen
    return logger
    
        
def module_functions(mymodule):
    '''list non-private functions in a module'''
    return  [a for a in dir(mymodule) if isinstance(mymodule.__dict__.get(a), types.FunctionType) and a[0]!='_']


def _HDF2Series(par):
    '''convert a parameter array into a Pandas series indexed on flight seconds
		e.g. AG = par2series(ff['Gear On Ground']
    '''
    p2=np.where(par.array.mask, np.nan, par.array.data)
    return pd.Series( p2, index=ts_index(par))


def node_type(base_nodes, nm):
    '''pretty version of node type for tabular display'''
    nodestr = repr(base_nodes.get(nm))
    if nodestr.find('key_point_values')>0: 
        ntype='KPV'
    elif nodestr.find('_phase')>0:
        ntype='phase'
    elif nodestr.find('_time_')>0:
        ntype='KTI'
    elif nodestr.find('_param')>0:
        ntype='parameter'
    else:
        ntype=nodestr        
    return ntype
    

def search_node(node_dict, search_term):
    '''search over a dict(name:node) of measurement nodes. partial matches ok; not case sensitive'
	  e.g. node_search(bn, 'flap')
    '''
    matching_names= [k for k in node_dict.keys() if k.upper().find(search_term.upper())>=0]
    df = pd.DataFrame({'name': matching_names })
    df['type']= [node_type(node_dict, nm) for nm in matching_names]
    #df.index = df['name']
    return df	
    
    
def _node_typestr(node):
    '''prettier version of node class type'''
    return str(node.node_type).replace("<class 'analysis_engine.node.",'').replace("'>",'')

def _param_val(param_node):
    '''prepare parameter values for nicer display '''
    if param_node.node_type is node.FlightAttributeNode:
        return str(param_node.value)
    elif issubclass(param_node.node_type, node.SectionNode):
        if len(param_node.get_slices())==0:
            return '[]'    
        else:
            return ' '.join([ str(sl) for sl in param_node.get_slices() ]).replace('slice','')
    else: 
        return str(param_node)
    

def plot_hdf(hdf_series, label=None, kind='line', use_index=True, rot=None, xticks=None, yticks=None, xlim=None, ylim=None, ax=None, style=None, grid=None, legend=False, logx=False, logy=False):
    '''plot an hdf series with seconds on the x axis'''
    HS = _HDF2Series(hdf_series)
    HS.plot(label=label, kind=kind, use_index=use_index, rot=rot, xticks=xticks, yticks=yticks, xlim=xlim, ylim=ylim, ax=ax, style=style, grid=grid, legend=legend, logx=logx, logy=logy)


def search_ffd(ffd_pmeta, term):
    '''search through list of parameters in the parameter meta-data for an FFD file, return partial matches
        ffd_pmeta = ffd parameter metadata for a flight (a DataFrame)    
        ffd_master = master list of ffd parameters
    '''
    matching_names =  [p for p in ffd_pmeta.index if str(p).upper().find(term.upper())>=0]
    df = pd.DataFrame({'FFD Name': matching_names })
    df['FFD DATA_TYPE'] = [ ffd_pmeta.ix[nm]['DATA_TYPE'] for nm in matching_names]
    df['STATES'] = [ ffd_master.ix[nm]['STATES'] if nm in ffd_master.index else 'not in master' for nm in matching_names]
    df['FFD UNITS'] = [ ffd_master.ix[nm]['UNITS']  if nm in ffd_master.index  else 'not in master' for nm in matching_names]
    df['dtype'] = [ ffd_pmeta.ix[nm]['dtype']  if nm in ffd_master.index  else 'not in master' for nm in matching_names]
    return df


def search_ffd_master(term):
    '''search through list of parameters in the parameter meta-data for an FFD file, return partial matches
        ffd_master = master list of ffd parameters
    '''
    matching_names =  [p for p in ffd_master.index if str(p).upper().find(term.upper())>=0]
    df = pd.DataFrame({'FFD Name': matching_names })
    df['FFD TYPE'] = [ ffd_master.ix[nm]['TYPE'] for nm in matching_names]
    df['STATES'] = [ ffd_master.ix[nm]['STATES'] if nm in ffd_master.index else 'not in master' for nm in matching_names]
    df['FFD UNITS'] = [ ffd_master.ix[nm]['UNITS'] if nm in ffd_master.index else 'not in master' for nm in matching_names]
    return df

         
# add info: lfl flag, type, frequency, valid, count, mask count
def search_hdf(myhdf5, search_term):
    '''search over Series in an hdf5 file = hdfaccess/ Parameter
       Partial matches ok; not case sensitive. 
	  e.g. param_search(ff, 'Accel')
    '''
    series = myhdf5.series
    matching_names= [k for k in series.keys() if k.upper().find(search_term.upper())>=0]
    df = pd.DataFrame({'FDS name': matching_names })
    #df['recorded']= [ ('T' if myhdf5.get(nm).lfl else 'F') for nm in matching_names]
    df['lfl_param']= [ (nm in myhdf5.lfl_params) for nm in matching_names]
    df['frequency']= [ series.get(nm).frequency for nm in matching_names]
    df['data_type']= [ series.get(nm).data_type for nm in matching_names]    
    df['units']= [ (series.get(nm).units if series.get(nm).units else '') for nm in matching_names]
    
    values = []
    for nm in matching_names:
        mapping = series[nm].values_mapping if series[nm].values_mapping is not None else 'n/a'
        values.append(mapping)
    df['FDS values']= values
    return df

 
def tabulate_derived(param_nodes):
    '''load derived parameters into a DataFrame for nice display'''
    outdf = pd.DataFrame({'name': [v for v in param_nodes.keys()]})
    outdf['node_type']= [_node_typestr(nd) for nd in param_nodes.values()] #outdf['node_type']
    outdf['val'] = [ _param_val(v) for v in param_nodes.values()]
    return outdf


def timestamp():
    '''use to include a timestamp in a notebook'''
    n=datetime.datetime.now()
    return n.strftime('%Y/%m/%d %H:%M')

    
def ts_index(par):
    '''given a parameter, construct a time array to serve as Series index
        e.g. ts_index(ff['Acceleration Normal'])
    '''
    return np.arange(par.offset, len(par.array)/par.frequency+par.offset,step=1/par.frequency)


if __name__=='__main__':
    initialize_logger('DEBUG')
    print module_functions(inspect)

    base_nodes = helper.get_derived_nodes(settings.NODE_MODULES)
    print node_search(base_nodes, 'flap')
    
    print 'master gear', ffd_master.get('Landing Gear Locked Down N')
    
    print 'master head', ffd_master.head()
    print search_ffd_master('flap')
    #hdf_plot(series['Vertical Speed'])
    from collections import OrderedDict
    from analysis_engine.node import ( A,   FlightAttributeNode,               # one of these per flight. mostly arrival and departure stuff
                                   App, ApproachNode,                      # per approach
                                   P,   DerivedParameterNode,              # time series with continuous values 
                                   M,   MultistateDerivedParameterNode,    # time series with discrete values
                                   KTI, KeyTimeInstanceNode,               # a list of time points meeting some criteria
                                   KPV, KeyPointValueNode,                 # a list of measures meeting some criteria; multiples are allowed and common 
                                   S,   SectionNode,  FlightPhaseNode,      # Sections=Phases
                                   KeyPointValue, KeyTimeInstance, Section  # data records, a list of which goes into the corresponding node
                                 )
                                 
    class SimplerKPV(KeyPointValueNode):
        '''just build it manually'''
        units='deg'
        def derive(self, start_datetime=A('Start Datetime')):
            self.append(KeyPointValue(index=42.5, value=666.6,name='My Simpler KPV'))

    
    k = SimplerKPV()
    k.derive( A('Start Datetime',666) )
    print 'kpv', k

    sk= OrderedDict()
    sk['SimplerKPV'] = k
    print derived_table(sk)

    print 'done'    