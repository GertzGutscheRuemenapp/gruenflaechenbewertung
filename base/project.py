# -*- coding: utf-8 -*-
'''
***************************************************************************
    project.py
    ---------------------
    Date                 : July 2019
    Copyright            : (C) 2019 by Christoph Franke
    Email                : franke at ggr-planung dot de
***************************************************************************
*                                                                         *
*   This program is free software: you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************

organization of data in projects
'''

__author__ = 'Christoph Franke'
__date__ = '16/07/2019'

import os
from glob import glob
import sys
import json
import shutil
import sys
from collections import OrderedDict
from operator import itemgetter
from typing import Tuple, List, Union
from qgis.core import QgsVectorLayer, QgsLayerTreeGroup

from projektcheck.utils.singleton import Singleton
from projektcheck.utils.connection import Request
from .database import Field, Table, FeatureCollection, Workspace
from .geopackage import Geopackage
from .layers import Layer, TileLayer

if sys.platform in ['win32', 'win64']:
    p = os.getenv('LOCALAPPDATA')
# Mac OS and Linux
else:
    # ToDo: is there a env. path to the documents folder?
    p = os.path.expanduser('~')# , 'Library/Application Support/')

BASE_PATH = os.path.realpath(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
APPDATA_PATH = os.path.join(p, 'Gruenflaechenbewertung')

JAVA_DEFAULT = ''

DEFAULT_OTP_JAR = os.path.join(BASE_PATH, 'lib', 'otp-ggr-stable.jar')
DEFAULT_JYTHON_PATH = os.path.join(BASE_PATH, 'lib',
                                   'jython-standalone-2.7.0.jar')
DEFAULT_GRAPH_PATH = os.path.join(APPDATA_PATH, 'otp_graphs')

DEFAULT_SETTINGS = {
    'active_project': u'',
    'project_path': os.path.join(APPDATA_PATH, 'Projekte'),
    'graph_path': os.path.join(APPDATA_PATH, 'Router'),
    'system': {
        'otp_jar_file': DEFAULT_OTP_JAR,
        'reserved': 2,
        'n_threads': 2,
        'jython_jar_file': DEFAULT_JYTHON_PATH,
        'java': JAVA_DEFAULT,
    }
}


class Settings(metaclass=Singleton):
    BASE_PATH = BASE_PATH
    UI_PATH = os.path.join(BASE_PATH, 'ui')
    LATITUDE_COLUMN = 'Y' # field-name used for storing lat values in csv files
    LONGITUDE_COLUMN = 'X' # field-name used for storing lon values in csv files
    ID_COLUMN = 'id' # field-name used for storing the ids in csv files
    VM_MEMORY_RESERVED = 3 # max. memory the virtual machine running OTP can allocate
    DATETIME_FORMAT = "%d/%m/%Y-%H:%M:%S" # format of time stored in xml files

    OUTPUT_DATE_FORMAT = 'dd.MM.yyyy HH:mm:ss' # format of the time in the results
    CALC_REACHABILITY_MODE = "THRESHOLD_SUM_AGGREGATOR" # agg. mode that is used to calculate number of reachable destinations (note: threshold is taken from set max travel time)
    INFINITE = 2147483647 # represents indefinite values in the UI, pyqt spin boxes are limited to max int32

    EPSG = 25832

    '''
    singleton for accessing and storing global settings in files
    '''
    _settings = {}
    # write changed config instantly to file
    _write_instantly = True

    def __init__(self, filename: str = 'config.txt',
                 defaults: dict = DEFAULT_SETTINGS):
        '''
        Parameters
        ----------
        filename : str, optional
            name of file in APPDATA path to store settings in
            by default 'projektcheck-config.txt'
        '''
        self.defaults = defaults
        if not os.path.exists(APPDATA_PATH):
            os.mkdir(APPDATA_PATH)

        self.config_file = os.path.join(APPDATA_PATH, filename)
        self._callbacks = {}
        self.active_coord = (0, 0)
        if os.path.exists(self.config_file):
            self.read()
            # add missing Parameters
            changed = False
            for k, v in defaults.items():
                if k not in self._settings:
                    self._settings[k] = v
                    changed = True
            if changed:
                self.write()

        # write default config, if file doesn't exist yet
        else:
            self._settings = defaults.copy()
            self.write()

    def read(self, config_file: str = None):
        '''
        read settings from file

        Parameters
        ----------
        config_file : str, optional
            path to file with settings, self.config_file used if None,
            by default None

        Raises
        ----------
        Exception
            file could not be read (e.g. wrong format, not existing)
        '''
        if config_file is None:
            config_file = self.config_file
        try:
            with open(config_file, 'r') as f:
                self._settings = json.load(f)
        except:
            self._settings = DEFAULT_SETTINGS.copy()
            print('Error while loading config. Using default values.')

    def write(self, config_file: str = None):
        '''
        write current settings to file

        Parameters
        ----------
        config_file : str, optional
            path to file with settings, self.config_file used if None,
            by default None
        '''
        if config_file is None:
            config_file = self.config_file

        with open(config_file, 'w') as f:
            config_copy = self._settings.copy()
            # pretty print to file
            json.dump(config_copy, f, indent=4, separators=(',', ': '))

    def reset_to_defaults(self):
        self._settings = self.defaults.copy()

    # access stored config entries like fields
    def __getattr__(self, name: str):
        if name in self.__dict__:
            return self.__dict__[name]
        elif name in self._settings:
            return self._settings[name]
        raise AttributeError

    def __setattr__(self, name: str, value: object):
        if name in self._settings:
            self._settings[name] = value
            if self._write_instantly:
                self.write()
            if name in self._callbacks:
                for callback in self._callbacks[name]:
                    callback(value)
        else:
            self.__dict__[name] = value
        #if name in self._callbacks:
            #for callback in self._callbacks[name]:
                #callback(value)

    def __repr__(self):
        ret = ['{} - {}'.format(k, str(v)) for k, v in self.__dict__.items()
               if not callable(v) and not k.startswith('_')]
        ret.extend([f'{v} - {k}' for k, v in self._settings.items()])
        return '\n'.join(ret)

    def __contains__(self, item: str):
        return item in self.__dict__ or item in self._settings

    def on_change(self, attribute: str, callback: object):
        '''
        register callback function to be called on configuration
        attribute change

        Parameters
        ----------
        attribute : str
            name of the attribute
        callback : function
            function to call if value of attribute has changed,
            function should expect the value as a parameter
        '''
        if attribute not in self._callbacks:
            self._callbacks[attribute] = []
        self._callbacks[attribute].append(callback)

    def remove_listeners(self, attribute: str):
        '''
        remove all callback functions of an configuration attribute

        Parameters
        ----------
        attribute : str
            name of the attribute
        '''
        if attribute in self._callbacks:
            self._callbacks.pop(attribute)

settings = Settings()

class Project:
    '''
    single project holding paths to base and project data

    Attributes
    ----------
    path : str
        the full path to the local project folder containing the project data
    '''
    settings = settings


    def __init__(self, name: str, path: str = ''):
        '''
        Parameters
        ----------
        name : str
            name of the project, equals the name of folder so make sure
            it only contains characters supported by the OS for folders
        path : str, optional
            the path to the project, the full path will be path + name, defaults
            to the project path in the settings
        '''
        self.name = name
        self.groupname = f'Projekt "{self.name}" (Grünflächenbewertung)'
        path = path or settings.project_path
        self.path = os.path.join(path, name)
        self.data = Geopackage(base_path=self.path, read_only=False)

    @property
    def basedata(self):
        '''
        the base data (same for all projects)
        '''
        return ProjectManager().basedata

    def remove(self):
        '''
        remove the project and its folder
        '''
        self.close()
        if os.path.exists(self.path):
            shutil.rmtree(self.path)

    def close(self):
        '''
        close the project
        '''
        self.data.close()

    def __repr__(self):
        return f'Project {self.name}'


class ProjectManager(metaclass=Singleton):
    '''
    singleton for accessing/changing projects and their data

    Attributes
    ----------
    projects : list
        available projects
    active_project: Project
        active project
    '''
    _projects = {}
    settings = settings

    def __init__(self):
        self.load()

    def load(self):
        '''
        load settings and list of projects
        '''
        if self.settings.project_path:
            project_path = self.settings.project_path
            if project_path and not os.path.exists(project_path):
                try:
                    os.makedirs(project_path)
                except:
                    pass
            if not os.path.exists(project_path):
                self.settings.project_path = project_path = ''
        self.reset_projects()

    def create_project(self, name: str, create_folder: bool = True):
        '''
        create a new project

        Parameters
        ----------
        name : str
            name of the project
        create_folder : bool, optional
            create a folder for the project data if True, defaults to creating
            a folder
        '''
        if not self.settings.project_path:
            return
        target_folder = os.path.join(self.settings.project_path, name)
        project = Project(name)
        self._projects[project.name] = project
        #shutil.copytree(os.path.join(settings.TEMPLATE_PATH, 'project'),
                        #target_folder)
        if create_folder and not os.path.exists(target_folder):
            os.mkdir(target_folder)
        return project

    def remove_project(self, project: Union[Project, str]):
        '''
        remove a project physically
        '''
        #self.active_project = None
        if isinstance(project, str):
            project = self._projects[project]
        project.remove()
        if project.name in self._projects:
            del(self._projects[project.name])

    def _get_projects(self) -> str:
        '''
        get list of project names in project path
        '''
        base_path = self.settings.project_path
        if not os.path.exists(base_path):
            return []
        project_folders = [f for f in os.listdir(base_path)
                           if os.path.isdir(os.path.join(base_path, f))]
        return sorted(project_folders)

    @property
    def projects(self) -> List[Project]:
        '''
        list of available projects
        '''
        return list(self._projects.values())

    def reset_projects(self):
        '''
        reloads the project list in currently set project folder
        '''
        self._projects = {}
        for name in self._get_projects():
            project = Project(name)
            self._projects[project.name] = project

    @property
    def active_project(self):
        '''
        active project, if not defined else, all read/write access of project
        data will be done in this project
        '''
        if self.settings.active_project:
            return self._projects.get(self.settings.active_project, None)
        return None

    @active_project.setter
    def active_project(self, project):
        if project and project.name not in self._projects:
            self._projects[project.name] = project
        self.settings.active_project = project.name if project else ''


class ProjectTable:
    '''
    manages project-related database tables (django-style),
    Tables defined this way will be automatically created with defined fields
    (defined by class attributes), ids are created automatically

    possible meta data (defined by Meta class):
        workspace - name of the workspace, defaults to 'default'
        name      - name of the table, defaults to class name in lower case
        database  - type of database, defaults to Geopackage
        geom      - geometry type (wkb geometry type string e.g. Polygon,
                    LineString), defaults to unspecified (decided when
                    saving geometries)

    e.g.

    class Example(ProjectTable):
        name = Field(str, 0)
        number = Field()

        class Meta:
            name = 'example name'
            workspace = 'examples'
            geom = 'Point'
    '''

    @classmethod
    def get_table(cls, project: Project = None, create: bool = False) -> Table:
        '''
        get a table defined in the ProjectTable style

        Parameters
        ----------
        project : Project, optional
            the project the table belongs to, defaults to the active project
        create : bool, optional
            create the table if not existing, defaults to not creating the table
            but raising an error if not found

        Returns
        ----------
        Table
            the table matching project and definition resp. the newly created
            table (create == True)

        Raises
        ----------
        FileNotFoundError
            table not found (create == False)
        '''
        project = project or ProjectManager().active_project
        #Database = getattr(cls.Meta, 'database', Geopackage)
        workspace_name = getattr(cls.Meta, 'workspace', 'default')
        table_name = getattr(cls.Meta, 'name', cls.__name__.lower())
        geometry_type = getattr(cls.Meta, 'geom', None)
        database = project.data
        workspace = database.get_or_create_workspace(workspace_name)
        try:
            fields, defaults = cls._fields()
            table = workspace.get_table(table_name, field_names=fields.keys())
            table_fields = [f.name for f in table.fields()]
            for field_name, typ in fields.items():
                if field_name not in table_fields:
                    table.add_field(Field(typ, name=field_name,
                                          default=defaults.get(field_name)))
        except FileNotFoundError as e:
            if not create:
                raise e
            table = cls._create(table_name, workspace,
                                geometry_type=geometry_type)
        return table
    @staticmethod
    def _where(kwargs):
        pass

    @classmethod
    def features(cls, project: Project = None, create: bool = False
                 ) -> FeatureCollection:
        '''
        get rows of the table as feature collection

        Parameters
        ----------
        project : Project, optional
            the project the table belongs to, defaults to active project
        create : bool, optional
            create the table if not existing, defaults to not creating the table
        '''
        return cls.get_table(project=project, create=create).features()

    @classmethod
    def _fields(cls) -> Tuple[dict, dict]:
        '''
        datatypes and default values of fields
        '''
        cls.extra()
        types = OrderedDict()
        defaults = OrderedDict()
        for k, v in cls.__dict__.items():
            if not isinstance(v, Field):
                continue
            name = k if not v.name else v.name
            if name == 'id':
                raise ValueError("keyword 'id' is reserved and can't be "
                                 "used as a field name")
            types[k] = v.datatype
            defaults[k] = v.default
        return types, defaults

    @classmethod
    def _create(cls, name: str, workspace: Workspace,
                geometry_type: str = None):
        '''
        create a table with field defined by class attributes
        '''
        types, defaults = cls._fields()
        return workspace.create_table(name, fields=types,
                                      defaults=defaults,
                                      geometry_type=geometry_type,
                                      epsg=settings.EPSG)

    @classmethod
    def extra(cls):
        '''
        override to add extra fields on runtime
        '''
        pass

    class Meta:
        '''
        metadata of table

        workspace - name of the workspace, defaults to 'default'
        name      - name of the table, defaults to class name in lower case
        database  - type of database, defaults to Geopackage
        geom      - geometry type (wkb geometry type string e.g. Polygon,
                    LineString), defaults to unspecified (decided when
                    saving geometries)
        '''


class ProjectLayer(Layer):
    '''
    wrapper of a vector layer in the QGIS layer tree belonging to a specific
    project. Projects are organized in seperate groups in the layer tree
    '''
    def __init__(self, layername: str, data_path: str, groupname: str = '',
                 project: Project = None, prepend: bool = True):
        '''
        Parameters
        ----------
        layername : str
            name the layer gets inside the layer tree
        data_path : str
            path to the data source of the layer
        groupname : str, optional
            name of the parent group the layer will be added to, will be created
            if not existing, can be nested by joining groups with '/',
            defaults to add layer to the root of the project group inside
            the layer tree
        prepend : bool
            prepend the group of the layer if True (prepends each group if
            nested), append if False, defaults to prepending the group
        '''
        self.project = project or ProjectManager().active_project
        self.label = ''
        groupname = f'{self.project.groupname}/{groupname}' if groupname \
            else self.project.groupname
        super().__init__(layername, data_path, prepend=prepend,
                         groupname=groupname)
        self.parent.setItemVisibilityChecked(True)

    @classmethod
    def find_group(cls, groupname) -> QgsLayerTreeGroup:
        '''
        find a group in the project group inside the layer tree by name

        Parameters
        ----------
        groupname : str
            name of the group to search, can be nested by joining groups with
            '/'
        '''
        project = ProjectManager().active_project
        if not project:
            return
        groupname = f'{project.groupname}/{groupname}' if groupname \
            else project.groupname if project else None
        return super().find_group(groupname)

    @classmethod
    def add_group(cls, groupname, project=None, prepend=True
                  ) -> QgsLayerTreeGroup:
        '''
        add a group to the layer tree

        Parameters
        ----------
        groupname : str
            name of the group that will be created inside the project group,
            can be nested by joining groups with '/'
        prepend : bool, optional
            prepend the group if True (prepends each group if nested),
            append if False, defaults to prepending the group

        Returns
        ----------
        QgsLayerTreeGroup
            the created group (the deepest one in hierarchy if nested)
        '''
        project = project or ProjectManager().active_project
        groupname = f'{project.groupname}/{groupname}'
        return Layer.add_group(groupname, prepend=prepend)

    def draw(self, style_file: str = None, label: str = '', redraw: str = True,
             checked: bool = True, filter: str = None, expanded: bool = True,
             read_only: bool = True, prepend: bool = False,
             toggle_if_exists=False, uncheck_siblings: bool = False,
             ) -> QgsVectorLayer:
        '''
        load the data into a vector layer, draw it and add it to the layer tree

        Parameters
        ----------
        label : str, optional
            label of the layer, defaults to layer name this is initialized with
        style_file : str, optional
            a QGIS style (.qml) can be applied to the layer, the path can either
            be a full path or the name of a file that will be looked for in the
            default style path, defaults to no style applied
        redraw : bool, optional
            replace old layer with same name in same group if True,
            only create if not existing if set to False, else it is refreshed,
            defaults to redrawing the layer
        checked: bool, optional
            set check state of layer in layer tree, defaults to being checked
        filter: str, optional
            QGIS filter expression to filter the layer, defaults to no filtering
        expanded: str, optional
            sets the legend to expanded or not, defaults to an expanded legend
        prepend: bool, optional
            prepend the layer to the other layers in its group if True,
            append it if False, defaults to appending the layer
        uncheck_siblings: bool, optional
            uncheck other layers in same group, defaults to leave their
            check-state as is
        read_only: bool, optional
            layer can not be altered by the user if True, defaults to read only
        toggle_if_exists: bool, optional
            toggle visibility if layer is already in layer tree, overrides
            "checked" parameter, ignored when redraw is True, defaults to set
            visibility according to given  "checked" parameter

        Returns
        ----------
        QgsVectorLayer
            the created, replaced or refreshed vector layer
        '''
        style_path = os.path.join(settings.TEMPLATE_PATH, 'styles', style_file)\
            if style_file else None

        layer = super().draw(style_path=style_path, label=label,
                             checked=checked, filter=filter, redraw=redraw,
                             prepend=prepend, expanded=expanded,
                             uncheck_siblings=uncheck_siblings,
                             toggle_if_exists=toggle_if_exists,
                             epsg=settings.EPSG # workaround for unrecognized OGR SRS
                             )
        layer.setReadOnly(read_only)
        return layer

    @classmethod
    def from_table(cls, table: Table, groupname: str = '', prepend: bool = True
                   ) -> 'ProjectLayer':
        '''
        create a layer with table data as a source

        Parameters
        ----------
        table : Table
            the table whose source will serve as a data source to the layer
        groupname : str, optional
            name of the parent group the layer will be added to, will be created
            if not existing, can be nested by joining groups with '/',
            defaults to add layer to the root of the project group inside
            the layer tree
        prepend : bool
            prepend the group of the layer if True (prepends each group if
            nested), append if False, defaults to prepending the group

        Returns
        ----------
        ProjectLayer
            the created project layer
        '''
        data_path = f'{table.workspace.path}|layername={table.name}'
        return ProjectLayer(table.name, data_path=data_path,
                            groupname=groupname, prepend=prepend)


class OSMBackgroundLayer(TileLayer):
    '''
    colored background tile-layer with OSM map data
    provided by openstreetmap.org (openstreetmap.org/copyright)
    '''

    def __init__(self, groupname: str = '', prepend: bool = False):
        url = ('type=xyz&url=https://a.tile.openstreetmap.org//{z}/{x}/{y}.png'
               f'&crs=EPSG{settings.EPSG}')
        super().__init__(url, groupname=groupname, prepend=prepend)

    def draw(self, checked=True):
        super().draw('OpenStreetMap © OpenStreetMap-Mitwirkende',
                     checked=checked)
        self.layer.setTitle(
            'Karte openstreetmap.org CC-BY-SA (openstreetmap.org/'
            'copyright), Kartendaten Openstreetmap ODbL')


class TerrestrisBackgroundLayer(TileLayer):
    '''
    grey background WMS-layer with OSM map data
    provided by terrestris.de (openstreetmap.org/copyright)
    '''

    def __init__(self, groupname: str = '', prepend: bool = False):

        url = (f'crs=EPSG:{settings.EPSG}&dpiMode=7&format=image/png'
               '&layers=OSM-WMS&styles=&url=http://ows.terrestris.de/osm-gray/'
               'service')
        super().__init__(url, groupname=groupname, prepend=prepend)

    def draw(self, checked=True):
        super().draw('Terrestris © OpenStreetMap-Mitwirkende',
                     checked=checked, expanded=False)
        self.layer.setTitle(
            'Karte terrestris.de CC-BY-SA (openstreetmap.org/copyright), '
            'Kartendaten Openstreetmap ODbL')
