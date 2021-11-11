# -*- coding: utf-8 -*-

from collections import OrderedDict
import os
from tool.base.project import Settings, APPDATA_PATH

path, f = os.path.split(os.path.realpath(__file__))

DEFAULT_OTP_JAR = os.path.join(path, 'otp-ggr-stable.jar')
DEFAULT_JYTHON_PATH = os.path.join(path, 'jython-standalone-2.7.0.jar')
DEFAULT_GRAPH_PATH = os.path.join(APPDATA_PATH, 'otp_graphs')
JAVA_DEFAULT = ''
LATITUDE_COLUMN = 'Y' # field-name used for storing lat values in csv files
LONGITUDE_COLUMN = 'X' # field-name used for storing lon values in csv files
ID_COLUMN = 'id' # field-name used for storing the ids in csv files
VM_MEMORY_RESERVED = 3 # max. memory the virtual machine running OTP can allocate
DATETIME_FORMAT = "%d/%m/%Y-%H:%M:%S" # format of time stored in xml files

OUTPUT_DATE_FORMAT = 'dd.MM.yyyy HH:mm:ss' # format of the time in the results
CALC_REACHABILITY_MODE = "THRESHOLD_SUM_AGGREGATOR" # agg. mode that is used to calculate number of reachable destinations (note: threshold is taken from set max travel time)
INFINITE = 2147483647 # represents indefinite values in the UI, pyqt spin boxes are limited to max int32

# structure of config-object, composition of xml is the same
# contains the DEFAULT values as presets for the UI
setting_struct = OrderedDict([
    ('origin', {
        'layer': '',
        'id_field': ''
    }),
    ('destination', {
        'layer': '',
        'id_field': ''
    }),
    ('system', {
        'otp_jar_file': DEFAULT_OTP_JAR,
        'reserved': 2,
        'n_threads': 1,
        'jython_jar_file': DEFAULT_JYTHON_PATH,
        'java': JAVA_DEFAULT,
    }),
    ('router_config', {
        'path': DEFAULT_GRAPH_PATH,
        'router': '',
        'traverse_modes': [
            'WALK'
        ],
        'max_walk_distance': 500,
        'walk_speed': 1.33,
        'wheel_chair_accessible': False,
        'max_slope': 0.083333
    })
])

config = Settings(default=setting_struct)