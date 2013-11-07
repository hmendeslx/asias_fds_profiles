.. foqa_test documentation master file, created by
   sphinx-quickstart on Mon Nov  4 14:49:56 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to asias_fds_profile documentation
==========================================
'asias_fds_profiles' are a set of Python modules intended for use with 
Flight Data Services FlightDataAnalyzer.

Each module defines a themed set of measures, some of which correspond to
ASIAS benchmarks.

As of Fall 2013, the profiles have been used in evaluation and testing against a
limited
set of test flights, and should not be regarded as fully mature.

Contents:

.. toctree::
   :maxdepth: 2

example_profile
===============
.. automodule:: example_profile


.. autoclass:: SimpleAttribute

.. autoclass:: FileAttribute

.. autoclass:: MydictAttribute

.. autoclass:: SimpleKTI

.. autoclass:: SimplerKTI

.. autoclass:: SimpleKPV

.. autoclass:: SimplerKPV

.. autoclass:: TCASRAStart

.. autoclass:: InitialApproach

.. autoclass:: DistanceTravelledInAir


tcas_profile
============
.. automodule:: tcas_profile

TCAS Event Identification
-------------------------
.. autoclass:: TCASRASections

.. autoclass:: TCASRAStart

.. autoclass:: TCASCtlSections


Event Review and Diagnosis
--------------------------
.. autoclass:: TCASRAResponsePlot

.. autoclass:: TCASCombinedControl

.. autoclass:: TCASUpAdvisory

.. autoclass:: TCASDownAdvisory

.. autoclass:: TCASVerticalControl

.. autoclass:: TCASSensitivity


Measures at start of TCAS RA
----------------------------
.. autoclass:: TCASSensitivityAtTCASRAStart

.. autoclass:: VerticalSpeedAtTCASRAStart

.. autoclass:: AltitudeQNHAtTCASRAStart

.. autoclass:: PitchAtTCASRAStart

.. autoclass:: RollAtTCASRAStart

.. autoclass:: AirspeedAtTCASRAStart

.. autoclass:: AutopilotAtTCASRAStart


Pilot Response
--------------
.. autoclass:: TCASRATimeToAPDisengage

.. autoclass:: TCASAltitudeExceedance

.. autoclass:: TCASRAStandardResponse




ua_profile
==========
.. automodule:: UA_profile

Derived Parameters
------------------
.. autoclass:: AirspeedReferenceVref

ILS Approaches
--------------
.. autoclass:: GlideslopeDeviation5Sec1000To500FtMax

.. autoclass:: GlideslopeDeviation5Sec500To200FtMax

.. autoclass:: GlideslopeDeviation5Sec1000To500FtMin

.. autoclass:: GlideslopeDeviation5Sec500To200FtMin

.. autoclass:: LocalizerDeviation5Sec1000To500FtMax

.. autoclass:: LocalizerDeviation5Sec500To50FtMax

Speeds
------
.. autoclass:: AirspeedRelativeMax3Sec1000to500ftHAT

.. autoclass:: AirspeedRelativeMax3Sec500to50ftHAT

.. autoclass:: AirspeedRelativeMin3Sec1000to500ftHAT

.. autoclass:: AirspeedRelativeMin3Sec500to50ftHAT

Vertical Speed
--------------
.. autoclass:: RateOfDescent3Sec1000To500FtMax

.. autoclass:: RateOfDescent3Sec500To50FtMax

Engine Speed
------------
.. autoclass:: EngN15Sec1000To500FtMin

.. autoclass:: EngN15Sec500To50FtMin

Configuration
-------------
Flap position change is embedded in FDS' base kpv values, named "AltitudeAtLastFlapChangeBeforeTouchdown"

.. autoclass:: AltitudeAtLastGearDownBeforeTouchdown

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

