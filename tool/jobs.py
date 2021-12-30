import shutil
from qgis.core import (QgsCoordinateTransform, QgsGeometry, QgsSpatialIndex,
                       QgsCoordinateReferenceSystem, QgsProject)
from qgis.PyQt.QtCore import QVariant, QProcess
import pandas as pd
import numpy as np
import processing
import os

from gruenflaechenotp.base.worker import Worker
from gruenflaechenotp.base.project import ProjectManager, settings
from gruenflaechenotp.tool.tables import (GruenflaechenEingaenge, Projektgebiet,
                                          AdressenProcessed, Baubloecke,
                                          ProjectSettings, Adressen,
                                          ProjektgebietProcessed, Gruenflaechen,
                                          GruenflaechenEingaengeProcessed,
                                          BaublockErgebnisse, AdressErgebnisse)

DEBUG = False
EXPONENTIAL_FACTOR = -0.003

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
                    # infinite coordinates are considered valid but fail
                    # to transform -> add empty geometry
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
            self.log(f'{n_broken_geometries} Features hatten keine oder defekte'
                     f' Geometrien. {repaired} davon konnten repariert werden.')
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
            table._layer.StartTransaction()
            for feat in base_table.features():
                attrs = dict((f.name, feat[f.name]) for f in fields)
                table.add(geom=feat.geom, **attrs)
            table._layer.CommitTransaction()
            self.set_progress((i+1) / len(self.tables) * 100)


class AnalyseRouting(Worker):
    def __init__(self, results_file, green_spaces, parent=None):
        super().__init__(parent=parent)
        self.results_file = results_file
        self.green_spaces = green_spaces

    def work(self):
        self.log('<br><b>Analyse der Ergebnisse des Routings</b><br>')

        self.log('Lese Eingangsdaten...')

        project_settings = ProjectSettings.features()[0]
        df_addresses = AdressenProcessed.features().to_pandas()
        df_addresses = df_addresses.rename(columns={'einwohner': 'ew_addr'})
        df_blocks = Baubloecke.features().to_pandas()
        df_addr_blocks = df_addresses.merge(df_blocks, how='left',
                                            left_on='baublock', right_on='fid')

        green_spaces = Gruenflaechen.features()
        area_data = []
        for feat in green_spaces:
            area_data.append((feat.id, feat.geom.area()))
        df_areas = pd.DataFrame(
            columns=['gruenflaeche', 'area'], data=area_data)
        df_entrances = GruenflaechenEingaengeProcessed.features().to_pandas()
        df_entrances = df_entrances.merge(
            df_areas, how='left', on='gruenflaeche')

        # for some reason pandas automatically replaces underscores in header
        # with spaces, no possibility to turn that off
        df_routing = pd.read_csv(
            self.results_file, delimiter=';',
            usecols= ['origin id','destination id', 'walk/bike distance (m)'])
        df_routing = df_routing.rename(
            columns={'origin id': 'eingang',
                     'destination id': 'adresse',
                     'walk/bike distance (m)': 'distance'}
        )
        df_routing = df_routing[df_routing['distance'] <=
                                project_settings.max_walk_dist]
        self.set_progress(35)

        self.log('Analysiere Grünflächennutzung...')

        df_merged = df_routing.merge(df_addr_blocks, how='left', on='adresse')
        df_merged = df_merged.merge(df_entrances, how='left', on='eingang')
        df_merged = df_merged[df_merged['baublock'].notna() &
                              df_merged['gruenflaeche'].notna()]

        df_merged['weighted_dist'] = df_merged['distance'].apply(
            lambda x: np.exp(EXPONENTIAL_FACTOR * x))
        df_merged['attractivity'] = (df_merged['weighted_dist'] *
                                     df_merged['area'])
        df_merged['attractivity_sum'] = df_merged.groupby(
            'adresse')['attractivity'].transform('sum')
        df_merged['addr_visit_prob'] = (df_merged['attractivity'] /
                                   df_merged['attractivity_sum'])
        df_merged['addr_visits'] = (df_merged['addr_visit_prob'] *
                                    df_merged['ew_addr'])
        df_merged['total_area_visits'] = df_merged.groupby(
            'gruenflaeche')['addr_visits'].transform('sum')
        df_merged['space_per_visitor'] = (df_merged['area'] /
                                          df_merged['total_area_visits'])
        df_merged['space_per_vis_weighted'] = (df_merged['space_per_visitor'] *
                                               df_merged['addr_visit_prob'])

        if DEBUG:
            df_merged = df_merged.drop(columns=['fid_x', 'fid_y', 'geom_x',
                                                'geom_y', 'fid', 'geom'])
            ppath = ProjectManager().active_project.path
            df_merged.to_csv(os.path.join(ppath, 'schritt_8.csv'), sep=';')

        df_results_addr = df_merged.groupby(
            ['adresse', 'ew_addr']).sum().reset_index()
        df_results_addr['space_used_addr'] = (
            df_results_addr['space_per_vis_weighted'] *
            df_results_addr['ew_addr'])
        df_results_addr = df_results_addr.reset_index()[
            ['adresse','space_used_addr', 'ew_addr', 'space_per_vis_weighted',
             'in_projektgebiet']]

        if DEBUG:
            df_results_addr.to_csv(os.path.join(ppath, 'schritt_11.csv'),
                                   sep=';')

        df_results_block = df_results_addr.merge(
            df_addresses, how='left', on='adresse')
        df_results_block = df_results_block.drop(columns=['fid'])
        df_results_block = df_results_block.groupby(
            'baublock').sum().reset_index()

        df_results_block = df_blocks.merge(df_results_block, how='left',
                                           left_on='fid', right_on='baublock')
        df_results_block['space_per_inh'] = (
            df_results_block['space_used_addr'] / df_results_block['einwohner'])
        df_results_block = df_results_block.fillna(0)

        if DEBUG:
            df_out = df_results_block[
                ['fid', 'space_per_inh', 'space_used_addr' , 'einwohner']]
            df_out.to_csv(os.path.join(ppath, 'schritt_13+.csv'), sep=';')

        df_results_block = df_results_block[
            ['fid', 'space_per_inh', 'geom', 'einwohner']]
        self.set_progress(60)

        self.log('Schreibe Ergebnisse...')

        df_addresses_in_project = df_addresses[
            df_addresses['in_projektgebiet'] == True]

        AdressErgebnisse.remove()
        results_addr = AdressErgebnisse.features(create=True)
        df_results_addr = df_results_addr.drop(columns=['ew_addr'])
        df_results_addr = df_addresses_in_project.merge(
            df_results_addr, how='left', on='adresse')
        df_results_addr = df_results_addr.fillna(0)

        results_addr.table._layer.StartTransaction()
        for index, row in df_results_addr.iterrows():
            results_addr.add(adresse=row['adresse'], einwohner=row['ew_addr'],
                             gruenflaeche_je_einwohner=
                             row['space_per_vis_weighted'], geom=row['geom'])
        results_addr.table._layer.CommitTransaction()

        BaublockErgebnisse.remove()
        blocks_in_pa = df_addresses_in_project['baublock'].unique()
        df_results_block_in_pa = df_results_block[
            df_results_block['fid'].isin(blocks_in_pa)]
        results_block = BaublockErgebnisse.features(create=True)
        results_block.table._layer.StartTransaction()
        for index, row in df_results_block_in_pa.iterrows():
            results_block.add(baublock=row['fid'], einwohner=row['einwohner'],
                              gruenflaeche_je_einwohner=row['space_per_inh'],
                              geom=row['geom'])
        results_block.table._layer.CommitTransaction()


class PrepareRouting(Worker):
    def work(self):
        self.log('<b>Vorbereitung des Routings</b><br>')
        project_settings = ProjectSettings.features()[0]
        entrances_layer = GruenflaechenEingaenge.as_layer()
        address_layer = Adressen.as_layer()
        block_layer = Baubloecke.as_layer()
        df_blocks = Baubloecke.features().to_pandas(columns=['fid', 'einwohner'])
        green_spaces_layer = Gruenflaechen.as_layer()
        AdressenProcessed.remove()
        GruenflaechenEingaengeProcessed.remove()
        ProjektgebietProcessed.remove()

        buffer = project_settings.project_buffer
        self.log('Verschneide Adressen und Grünflächeingänge '
                 f'mit dem Projektgebiet inkl. Buffer ({buffer}m) ')
        proc_pa = ProjektgebietProcessed.features(create=True)
        for feat in Projektgebiet.features():
            proc_pa.add(geom=feat.geom.buffer(buffer, 10))

        project_layer_buffered = ProjektgebietProcessed.as_layer()

        parameters = {'INPUT': address_layer,
                      'INPUT_FIELDS': ['fid'],
                      'OVERLAY': project_layer_buffered,
                      'OUTPUT':'memory:'}
        addr_in_buffer_layer = processing.run(
            'native:intersection', parameters)['OUTPUT']

        parameters = {'INPUT': address_layer,
                      'INPUT_FIELDS': ['fid'],
                      'OVERLAY': Projektgebiet.as_layer(),
                      'OUTPUT':'memory:'}
        addr_in_project_layer = processing.run(
            'native:intersection', parameters)['OUTPUT']

        parameters = {'INPUT': entrances_layer,
                      'OVERLAY': project_layer_buffered,
                      'OVERLAY_FIELDS_PREFIX': 'green_',
                      'OUTPUT':'memory:'}
        ent_in_buffer_layer = processing.run(
            'native:intersection', parameters)['OUTPUT']
        self.set_progress(15)

        self.log('Ordne Adressen den Baublöcken zu...')

        parameters = {'INPUT': addr_in_buffer_layer,
                      'INPUT_FIELDS': ['fid'],
                      'OVERLAY': block_layer,
                      'OVERLAY_FIELDS_PREFIX': 'block_',
                      'OUTPUT':'memory:'}

        addr_block_layer = processing.run(
            'native:intersection', parameters)['OUTPUT']
        self.set_progress(30)

        in_project = []
        for feat in addr_in_project_layer.getFeatures():
            in_project.append(feat.attribute('fid'))

        rows = []
        for feat in addr_block_layer.getFeatures():
            # intersection turns the points into multipoints whyever
            geom = feat.geometry().asGeometryCollection()[0]
            rows.append(
                [feat.attribute('fid'), feat.attribute('block_fid'), geom])

        df_blocks = df_blocks.rename(columns={'einwohner': 'einwohner_block'})
        df_addresses = pd.DataFrame(
            data=rows, columns=['adresse', 'baublock', 'geom'])
        df_addresses = df_addresses.merge(
            df_blocks, left_on='baublock', right_on='fid')
        df_addresses['in_projektgebiet'] = False
        df_addresses['in_projektgebiet'][
            df_addresses['adresse'].isin(in_project)] = True

        df_addresses['block_count'] = (
            df_addresses.groupby('baublock')['baublock'].transform('count'))
        df_addresses['einwohner'] = (df_addresses['einwohner_block'].astype(float) /
                                     df_addresses['block_count'])
        df_addresses.drop(columns=['fid'], inplace=True)
        proc_addresses = AdressenProcessed.features(create=True)
        proc_addresses.update_pandas(df_addresses)

        missing = (addr_in_buffer_layer.featureCount() -
                   addr_block_layer.featureCount())
        if missing:
            self.log(f'{missing} Adressen konnten keinem Baublock '
                     'zugeordnet werden.', warning=True)
        self.set_progress(70)

        self.log('Ordne Eingänge den Grünflächen zu...')

        green_index = QgsSpatialIndex()
        for feat in green_spaces_layer.getFeatures():
            green_index.insertFeature(feat)
        missing = 0
        max_ent_dist = 100
        proc_entrances = GruenflaechenEingaengeProcessed.features(create=True)
        for feat in ent_in_buffer_layer.getFeatures():
            # multipoint to point
            geom = feat.geometry().asGeometryCollection()[0]
            nearest = green_index.nearestNeighbor(geom, 1,
                                                  maxDistance=max_ent_dist)
            if nearest:
                proc_entrances.add(eingang=feat.attribute('fid'), geom=geom,
                                   gruenflaeche=nearest[0])
            else:
                missing += 1
        if missing:
            self.log(f'{missing} Eingänge konnten im Umkreis von '
                     f'{max_ent_dist}m keiner Grünfläche zugeordnet werden.',
                     warning=True)

