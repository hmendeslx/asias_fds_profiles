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

As of Fall 2013, the profiles have been used in evaluation and testing against a limited
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

.. autoclass:: TCASRASections

.. autoclass:: TCASRAStart

.. autoclass:: TCASCtlSections

.. autoclass:: TCASRAResponsePlot

.. autoclass:: TCASAltitudeExceedance

.. autoclass:: TCASRAStandardResponse

.. autoclass:: TCASCombinedControl

.. autoclass:: TCASUpAdvisory

.. autoclass:: TCASDownAdvisory

.. autoclass:: TCASVerticalControl

.. autoclass:: TCASSensitivityAtTCASRAStart

.. autoclass:: TCASSensitivity

.. autoclass:: VerticalSpeedAtTCASRAStart

.. autoclass:: AltitudeQNHAtTCASRAStart

.. autoclass:: PitchAtTCASRAStart

.. autoclass:: RollAtTCASRAStart

.. autoclass:: AirspeedAtTCASRAStart

.. autoclass:: AutopilotAtTCASRAStart

.. autoclass:: TCASRATimeToAPDisengage


ua_profile
==========
TBD

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

