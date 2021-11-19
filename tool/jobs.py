import shutil
import math
import os
from qgis.core import (QgsCoordinateTransform, QgsGeometry, QgsSpatialIndex,
                       QgsCoordinateReferenceSystem, QgsProject,
                       QgsVectorFileWriter)
from qgis.PyQt.QtCore import QVariant, QProcess
import pandas as pd
import numpy as np
import tempfile
import time

from gruenflaechenotp.base.worker import Worker
from gruenflaechenotp.base.project import ProjectManager, settings
from gruenflaechenotp.batch.config import Config as OTPConfig
from gruenflaechenotp.tool.tables import (GruenflaechenEingaenge, Projektgebiet,
                                          Adressen, Baubloecke, ProjectSettings)
from gruenflaechenotp.tool.dialogs import ExecOTPDialog
from gruenflaechenotp.base.spatial import intersect, create_layer


class CloneProject(Worker):
    '''
    worker for cloning a project
    '''
    def __init__(self, project_name, project, parent=None):
        super().__init__(parent=parent)
        self.project_name = project_name
        self.origin_project = project
        self.project_manager = ProjectManager()

    def work(self):

        cloned_project = self.project_manager.create_project(
            self.project_name, create_folder=False)
        self.log('Kopiere Projektordner...')

        # copy template folder
        try:
            shutil.copytree(self.origin_project.path, cloned_project.path)
        except Exception as e:
            self.error.emit(str(e))
            self.project_manager.remove_project(self.project_name)
            return
        self.log('Neues Projekt erfolgreich angelegt '
                 f'unter {cloned_project.path}')
        return cloned_project


class ImportLayer(Worker):
    '''
    worker for importing data into project tables
    '''
    def __init__(self, table, layer, layer_crs, fields=[], parent=None):
        super().__init__(parent=parent)
        self.layer = layer
        self.layer_crs = layer_crs
        self.fields = fields
        self.table = table

    def work(self):
        self.log('Lösche vorhandene Features...')
        self.table.delete_rows()
        self.set_progress(30)

        tr = QgsCoordinateTransform(
            self.layer_crs,
            QgsCoordinateReferenceSystem(f'epsg:{settings.EPSG}'),
            QgsProject.instance()
        )

        self.log('Importiere Features...')
        n_broken_geometries = 0
        repaired = 0
        for feature in self.layer.getFeatures():
            geom = feature.geometry()
            if geom.isEmpty():
                n_broken_geometries += 1
            else:
                error = False
                if not geom.isGeosValid():
                    error = True
                    try:
                        geom = geom.makeValid()
                        geom.transform(tr)
                    except:
                        pass
                    # still not valid -> add empty geometry instead
                    if not geom.isGeosValid():
                        geom = QgsGeometry()
                    else:
                        repaired += 1
                else:
                    geom = QgsGeometry(geom)
                    # infinite coordinates are considered valid but fail to transform
                    # -> add empty geometry
                    try:
                        geom.transform(tr)
                    except:
                        geom = QgsGeometry()
                        error = True
                if error:
                    n_broken_geometries += 1

            attrs = {}
            for f_in, f_out in self.fields:
                attr = feature.attribute(f_in)
                if isinstance(attr, QVariant) and attr.isNull():
                    continue
                attrs[f_out] = attr
            self.table.add(geom=geom, **attrs)

        self.log(f'{self.layer.featureCount()} Features erfolgreich importiert')
        not_repaired = n_broken_geometries - repaired
        if n_broken_geometries:
            self.log(f'{n_broken_geometries} Features hatten keine oder defekte '
                     f'Geometrien. {repaired} davon konnten repariert werden.')
        if not_repaired:
            self.log(f'{not_repaired} Features wurde ohne Geometrie in das '
                     'Projekt übernommen', warning=True)


class ResetLayers(Worker):
    '''
    worker for resetting project tables to defaults
    '''
    def __init__(self, tables, parent=None):
        super().__init__(parent=parent)
        self.tables = tables
        self.project_manager = ProjectManager()

    def work(self):
        for i, table in enumerate(self.tables):
            self.log(f'<b>Zurücksetzung der Tabelle "{table.name}"...</b>')
            table.delete_rows()
            self.log('Importiere Standard-Features...')
            base_table = self.project_manager.basedata.get_table(
                table.name, workspace='project')
            fields = table.fields()
            for feat in base_table.features():
                attrs = dict((f.name, feat[f.name]) for f in fields)
                table.add(geom=feat.geom, **attrs)
            self.set_progress((i+1) / len(self.tables) * 100)


class AnalyseRouting(Worker):
    def __init__(self, results_file, green_spaces, parent=None):
        super().__init__(parent=parent)
        self.results_file = results_file
        self.green_spaces = green_spaces

    def work(self):
        self.log('')
        self.log('<br><b>Analyse der Ergebnisse</b><br>')
        project_settings = ProjectSettings.features()[0]
        # for some reason pandas automatically replaces underscores in header
        # with spaces, no possibility to turn that off
        df_results = pd.read_csv(
            self.results_file, delimiter=';',
            usecols= ['origin id','destination id', 'walk/bike distance (m)'])
        df_results = df_results.rename(
            columns={'origin id': 'entrance_id',
                     'destination id': 'address_id',
                     'walk/bike distance (m)': 'distance'}
        )

        self.log('Ordne Adressen den Baublöcken zu...')
        df_results = df_results[df_results['distance'] <=
                                project_settings.max_walk_dist]
        addresses = Adressen.features()
        intersection = intersect(Adressen.features(),
                                 Baubloecke.features(),
                                 input_fields={'id': 'address_id'},
                                 output_fields={'id': 'block_id',
                                                'einwohner': 'ew'},
                                 epsg=settings.EPSG)
        data = [list(f.values()) for f in intersection]
        df_addr_blocks = pd.DataFrame(columns=['address_id', 'block_id', 'ew'],
                                      data=data)
        # duplicates occur if there are blocks on top of each other
        # keep only first match
        df_addr_blocks = df_addr_blocks.drop_duplicates(subset=['address_id'])
        df_addr_blocks['block_count'] = (
            df_addr_blocks.groupby('block_id')['block_id'].transform('count'))
        df_addr_blocks['ew_addr'] = (df_addr_blocks['ew'].astype(float) /
                                     df_addr_blocks['block_count'])
        df_addr_blocks['address_id'] = df_addr_blocks['address_id'].astype(np.int64)
        missing = len(addresses) - len(df_addr_blocks)
        if missing:
            self.log(f'{missing} Adressen konnten keinem Baublock '
                     'zugeordnet werden.', warning=True)
        self.set_progress(40)

        self.log('Ordne Eingänge den Grünflächen zu...')
        entrances = GruenflaechenEingaenge.features()
        green_index = QgsSpatialIndex()
        area_data = []
        for feat in self.green_spaces:
            area_data.append((feat.id(), feat.geometry().area()))
            green_index.insertFeature(feat)
        df_areas = pd.DataFrame(columns=['green_id', 'area'], data=area_data)
        data = []
        missing = 0
        max_ent_dist = 100
        for feat in entrances:
            nearest = green_index.nearestNeighbor(feat.geom, 1,
                                                  maxDistance=max_ent_dist)
            if nearest:
                data.append((feat.id, nearest[0]))
            else:
                missing += 1
        df_entrances = pd.DataFrame(columns=['entrance_id', 'green_id'],
                                    data=data)
        df_entrances = df_entrances.merge(df_areas, how='left', on='green_id')
        if missing:
            self.log(f'{missing} Eingänge konnten im Umkreis von '
                     f'{max_ent_dist}m keiner Grünfläche zugeordnet werden.',
                     warning=True)
        self.set_progress(60)

        self.log('Analysiere Grünflächennutzung...')
        df_merged = df_results.merge(df_addr_blocks, how='left', on='address_id')
        df_merged = df_merged.merge(df_entrances, how='left', on='entrance_id')
        df_merged = df_merged[df_merged['block_id'].notna() &
                              df_merged['green_id'].notna()]
        print()



class PrepareRouting(Worker):
    def work(self):
        self.log('<b>Vorbereitung des Routings</b><br>')
        origin_layer = GruenflaechenEingaenge.as_layer()
        destination_layer = Adressen.as_layer()
        project_layer = Projektgebiet.as_layer()
        #origin_layer = ProjectLayer.from_table(Adressen.get_table())
        #project_layer = create_layer(Projektgebiet.features(),
                                     #Projektgebiet.Meta.geom)
        #destination_layer = create_layer(Adressen.features(),
                                         #Adressen.Meta.geom)
        #parameters = {'INPUT': origin_layer,
                      #'OVERLAY': project_layer,
                      #'OVERLAY_FIELDS': [],
                      #'OUTPUT':'memory:'}
        #o_clipped = processing.run(
            #'native:clip', parameters)['OUTPUT']

        #project_layer = self.project_area_output.layer
        #parameters = {'INPUT': address_layer,
                      #'OVERLAY': project_layer,
                      #'OUTPUT':'memory:'}
        #destination_layer = processing.run(
            #'native:intersection', parameters)['OUTPUT']

        return origin_layer, destination_layer
