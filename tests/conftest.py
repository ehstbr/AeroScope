"""Run legacy UI and METAR regression expectations in their original language.

The application itself always defaults to en_US. A separate test exercises
both languages in fresh processes so its result cannot depend on import order.
"""
import os
os.environ.setdefault('AEROSCOPE_LANGUAGE', 'pt_BR')
