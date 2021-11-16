import shutil
from qgis.core import (QgsCoordinateTransform, QgsGeometry,
                       QgsCoordinateReferenceSystem, QgsProject)
from qgis.PyQt.QtCore import QVariant

from gruenflaechenotp.base.worker import Worker
from gruenflaechenotp.base.project import ProjectManager, settings


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
    worker for cloning a project
    '''
    def __init__(self, table, layer, layer_crs, fields=[], parent=None):
        super().__init__(parent=parent)
        self.layer = layer
        self.layer_crs = layer_crs
        self.fields = fields
        self.table = table
        self.project_manager = ProjectManager()

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
        for feature in self.layer.getFeatures():
            geom = feature.geometry()
            valid = geom.isGeosValid()
            if valid:
                geom = QgsGeometry(geom)
                try:
                    geom.transform(tr)
                # infinite coordinates are considered valid but fail to transform
                except:
                    valid = False
            if not valid:
                geom = QgsGeometry()
                n_broken_geometries += 1
            attrs = {}
            for f_in, f_out in self.fields:
                attr = feature.attribute(f_in)
                if isinstance(attr, QVariant) and attr.isNull():
                    continue
                attrs[f_out] = attr
            self.table.add(geom=geom, **attrs)

        self.log(f'{self.layer.featureCount()} Features erfolgreich importiert')

        if n_broken_geometries > 0:
            self.log(f'{n_broken_geometries} Features haben keine oder defekte '
                     'Geometrien. Sie wurden ohne Geometrie in das Projekt '
                     'übernommen', warning=True)