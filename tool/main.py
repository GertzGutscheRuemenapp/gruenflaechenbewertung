import os
from PyQt5 import uic,  QtCore, QtWidgets

from qgis import utils
from qgis._core import (QgsVectorLayer, QgsVectorLayerJoinInfo,
                        QgsCoordinateReferenceSystem)
from qgis.core import QgsVectorFileWriter, QgsProject, QgsMapLayerProxyModel

from gruenflaechenotp.base.project import (ProjectManager, settings,
                                                ProjectLayer, OSMBackgroundLayer)
from gruenflaechenotp.tool.dialogs import (ExecOTPDialog, RouterDialog, InfoDialog,
                                           SettingsDialog, NewProjectDialog,
                                           ImportLayerDialog)
from gruenflaechenotp.base.database import Workspace
from gruenflaechenotp.tool.tables import (ProjectSettings, Projektgebiet,
                                          Adressen, Baubloecke, Gruenflaechen,
                                          GruenflaechenEingaenge)
from gruenflaechenotp.base.dialogs import ProgressDialog
from gruenflaechenotp.tool.jobs import CloneProject, ImportLayer

import tempfile
import shutil
import getpass
import csv
import webbrowser

from datetime import datetime

TITLE = "Grünflächenbewertung"

# how many results are written while running batch script
PRINT_EVERY_N_LINES = 100
main_form = os.path.join(settings.UI_PATH, 'OTP_main_window.ui')


class OTPMainWindow(QtCore.QObject):
    def __init__(self, on_close=None, parent=None):
        """Constructor."""
        super().__init__(parent)

        self.ui = QtWidgets.QMainWindow()
        uic.loadUi(main_form, self.ui)
        self.project_manager = ProjectManager()
        self.project_settings = None
        graph_path = self.project_manager.settings.graph_path
        self.canvas = utils.iface.mapCanvas()
        if graph_path and not os.path.exists(graph_path):
            try:
                os.makedirs(graph_path)
            except:
                pass
        self.on_close = on_close
        self.ui.setWindowTitle(TITLE)
        self.setupUi()

    def closeEvent(self, evnt):
        if self.on_close:
            self.on_close()

    def setupUi(self):
        '''
        prefill UI-elements and connect slots and signals
        '''
        self.ui.create_project_button.clicked.connect(self.create_project)
        self.ui.remove_project_button.clicked.connect(self.remove_project)
        self.ui.clone_project_button.clicked.connect(self.clone_project)

        self.ui.project_combo.currentIndexChanged.connect(
            lambda index: self.change_project(
                self.ui.project_combo.itemData(index)))

        # connect menu actions
        self.ui.info_action.triggered.connect(self.show_info)

        # connect menu actions
        self.ui.settings_action.triggered.connect(self.show_settings)

        def save_project_setting(attr, value):
            self.project_settings[attr] = value
            self.project_settings.save()

        self.ui.required_green_edit.valueChanged.connect(
            lambda x: save_project_setting('required_green', x))
        self.ui.max_walk_dist_edit.valueChanged.connect(
            lambda x: save_project_setting('max_walk_dist', x))
        self.ui.project_buffer_edit.valueChanged.connect(
            lambda x: save_project_setting('project_buffer', x))

        ##self.router_combo.setValue(project_settings.router)
        self.ui.walk_speed_edit.valueChanged.connect(
            lambda x: save_project_setting('walk_speed', x))
        self.ui.wheelchair_check.stateChanged.connect(
            lambda: save_project_setting('wheelchair',
                                         self.ui.wheelchair_check.isChecked()))
        self.ui.max_slope_edit.valueChanged.connect(
            lambda x: save_project_setting('max_slope', x))

        self.ui.create_router_button.clicked.connect(self.create_router)

        self.ui.import_project_area_button.clicked.connect(
            self.import_project_area)
        self.ui.import_green_spaces_button.clicked.connect(
            self.import_green_spaces)
        self.ui.import_green_entrances_button.clicked.connect(
            self.import_green_entrances)
        self.ui.import_blocks_button.clicked.connect(self.import_blocks)
        self.ui.import_addresses_button.clicked.connect(self.import_addresses)

        # router
        self.setup_projects()

    def setup_projects(self):
        '''
        fill project combobox with available projects
        '''
        self.ui.tabWidget.setEnabled(False)
        self.ui.start_calculation_button.setEnabled(False)

        self.project_manager.active_project = None

        self.ui.project_combo.blockSignals(True)
        self.ui.project_combo.clear()
        self.ui.project_combo.addItem('Projekt wählen')
        self.ui.project_combo.model().item(0).setEnabled(False)
        self.project_manager.reset_projects()
        for project in self.project_manager.projects:
            if project.name == '__test__':
                continue
            self.ui.project_combo.addItem(project.name, project)
        self.ui.project_combo.blockSignals(False)

    def create_project(self):
        '''
        Open a dialog for setting up a new project and create the project
        based on this setup. Automatically set the new project as active project
        if successfully created
        '''
        dialog = NewProjectDialog()
        ok, project_name = dialog.show()

        if ok:
            project = self.project_manager.create_project(project_name)
            project_settings = ProjectSettings.features(project=project,
                                                        create=True)
            project_settings.add()
            self.project_manager.active_project = project
            self.ui.project_combo.addItem(project.name, project)
            self.ui.project_combo.setCurrentIndex(
                self.ui.project_combo.count() - 1)

    def import_project_area(self):
        table = Projektgebiet.get_table(create=True)
        dialog = ImportLayerDialog(
            title='Projektgebiet importieren',
            filter_class=QgsMapLayerProxyModel.PolygonLayer)
        ok, layer, crs, fields = dialog.show()
        if ok:
            job = ImportLayer(table, layer, crs, fields=fields, parent=self.ui)
            dialog = ProgressDialog(
                job, parent=self.ui,
                on_success=lambda x: self.pa_output.draw(redraw=False))
            dialog.show()

    def import_green_spaces(self):
        table = Gruenflaechen.get_table(create=True)
        dialog = ImportLayerDialog(
            title='Grünflächen importieren',
            filter_class=QgsMapLayerProxyModel.PolygonLayer)
        ok, layer, crs, fields = dialog.show()
        if ok:
            job = ImportLayer(table, layer, crs, fields=fields, parent=self.ui)
            dialog = ProgressDialog(
                job, parent=self.ui,
                on_success=lambda x: self.green_output.draw(redraw=False))
            dialog.show()

    def import_blocks(self):
        table = Baubloecke.get_table(create=True)
        dialog = ImportLayerDialog(
            title='Baublöcke importieren',
            required_fields=[('einwohner', 'Anzahl Einwohner')],
            filter_class=QgsMapLayerProxyModel.PolygonLayer)
        ok, layer, crs, fields = dialog.show()
        if ok:
            job = ImportLayer(table, layer, crs, fields=fields, parent=self.ui)
            dialog = ProgressDialog(
                job, parent=self.ui,
                on_success=lambda x: self.blocks_output.draw(redraw=False))
            dialog.show()

    def import_addresses(self):
        table = Adressen.get_table(create=True)
        dialog = ImportLayerDialog(
            title='Adressen importieren',
            optional_fields=[
                ('strasse', 'Straße'), ('hausnummer', 'Hausnummer'),
                ('ort', 'Ort'), ('beschreibung', 'Beschreibung')],
            help_text='Die Angabe der Felder ist optional und dient nur der '
            'besseren manuellen Zuordenbarkeit. Die Felder haben weder '
            'Einfluss auf die Ergebnisse noch auf die Ergebnisdarstellung.',
            filter_class=QgsMapLayerProxyModel.PointLayer)
        ok, layer, crs, fields = dialog.show()
        if ok:
            job = ImportLayer(table, layer, crs, fields=fields, parent=self.ui)
            dialog = ProgressDialog(
                job, parent=self.ui,
                on_success=lambda x: self.addr_output.draw(redraw=False))
            dialog.show()

    def import_green_entrances(self):
        table = GruenflaechenEingaenge.get_table(create=True)
        dialog = ImportLayerDialog(
            title='Grünflächeneingänge importieren',
            filter_class=QgsMapLayerProxyModel.PointLayer)
        ok, layer, crs, fields = dialog.show()
        if ok:
            job = ImportLayer(table, layer, crs, fields=fields, parent=self.ui)
            dialog = ProgressDialog(
                job, parent=self.ui,
                on_success=lambda x: self.green_e_output.draw(redraw=False))
            dialog.show()

    def clone_project(self):
        '''
        clone the currently selected project
        '''
        project = self.project_manager.active_project
        if not project:
            return
        dialog = NewProjectDialog(placeholder=f'{project.name}_kopie')
        ok, project_name = dialog.show()

        if ok:
            job = CloneProject(name, project, parent=self.ui)
            def on_success(project):
                self.ui.project_combo.addItem(project.name, project)
                self.ui.project_combo.setCurrentIndex(
                    self.ui.project_combo.count() - 1)
                self.project_manager.active_project = project
            dialog = ProgressDialog(job, parent=self.ui,
                                    on_success=on_success)
            dialog.show()

    def remove_project(self):
        '''
        remove the currently selected project
        '''
        project = self.project_manager.active_project
        if not project:
            return
        reply = QtWidgets.QMessageBox.question(
            self.ui, 'Projekt entfernen',
            f'Soll das Projekt "{project.name}" entfernt werden?\n'
            '(alle Projektdaten werden gelöscht)',
             QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            idx = self.ui.project_combo.currentIndex()
            self.ui.project_combo.setCurrentIndex(0)
            self.ui.project_combo.removeItem(idx)
            instances = list(Workspace.get_instances())
            for ws in instances:
                # close all writable workspaces (read_only indicate the
                # base data)
                # ToDo: adress project workspaces somehow else
                if not ws.database.read_only:
                    ws.close()
            # close and remove layers in project group (in TOC)
            qgisproject = QgsProject.instance()
            root = qgisproject.layerTreeRoot()
            project_group = root.findGroup(project.groupname)
            if project_group:
                for layer in project_group.findLayers():
                    qgisproject.removeMapLayer(layer.layerId())
                project_group.removeAllChildren()
                root.removeChildNode(project_group)
            # wait for canvas to refresh because it blocks the datasources for
            # the layers as long they are visible
            def on_refresh():
                try:
                    self.project_manager.remove_project(project)
                except:
                    # ToDo: catch properly
                    pass
                self.project_manager.active_project = None
                self.canvas.mapCanvasRefreshed.disconnect(on_refresh)
            self.canvas.mapCanvasRefreshed.connect(on_refresh)
            self.canvas.mapCanvasRefreshed
            self.canvas.refreshAllLayers()

    def change_project(self, project):
        if not project:
            self.ui.tabWidget.setEnabled(False)
            return
        self.project_manager.active_project = project
        self.project_settings = ProjectSettings.features(project=project)[0]
        # ToDo: load layers and settings
        try:
            self.apply_project_settings(project)
        except FileNotFoundError:
            return
        self.ui.tabWidget.setEnabled(True)

        # check active project, uncheck other projects
        layer_root = QgsProject.instance().layerTreeRoot()
        for p in self.project_manager.projects:
            group = layer_root.findGroup(p.groupname)
            if group:
                group.setItemVisibilityChecked(
                    p.groupname==project.groupname)

        self.add_input_layers()

        backgroundOSM = OSMBackgroundLayer(groupname='Hintergrundkarten')
        backgroundOSM.draw()

    def add_input_layers(self):
        groupname = 'Eingangsdaten'

        addresses = Adressen.get_table(create=True)
        self.addr_output = ProjectLayer.from_table(
            addresses, groupname=groupname)
        self.addr_output.draw(
            label='Adressen',
            style_file='adressen.qml',
            redraw=False)

        green_entrances = GruenflaechenEingaenge.get_table(create=True)
        self.green_e_output = ProjectLayer.from_table(
            green_entrances, groupname=groupname)
        self.green_e_output.draw(
            label='Grünflächen Eingänge',
            style_file='gruen_eingaenge.qml',
            redraw=False)

        green = Gruenflaechen.get_table(create=True)
        self.green_output = ProjectLayer.from_table(
            green, groupname=groupname)
        self.green_output.draw(
            label='Grünflächen',
            style_file='gruenflaechen.qml',
            redraw=False)

        blocks = Baubloecke.get_table(create=True)
        self.blocks_output = ProjectLayer.from_table(
            blocks, groupname=groupname)
        self.blocks_output.draw(label='Baublöcke',
            style_file='bloecke.qml',
            redraw=False)

        project_area = Projektgebiet.get_table(create=True)
        self.pa_output = ProjectLayer.from_table(
            project_area, groupname=groupname)
        self.pa_output.draw(label='Projektgebiet',
            style_file='projektgebiet.qml',
            redraw=False)
        self.pa_output.zoom_to()

    def apply_project_settings(self, project):
        self.ui.required_green_edit.setValue(self.project_settings.required_green)
        self.ui.max_walk_dist_edit.setValue(self.project_settings.max_walk_dist)
        self.ui.project_buffer_edit.setValue(self.project_settings.project_buffer)

        #self.router_combo.setValue(project_settings.router)
        self.ui.walk_speed_edit.setValue(self.project_settings.walk_speed)
        self.ui.wheelchair_check.setChecked(self.project_settings.wheelchair)
        self.ui.max_slope_edit.setValue(self.project_settings.max_slope)

        self.setup_routers()

    def setup_routers(self):
        # try to keep old router selected
        saved_router = self.project_settings.router
        self.ui.router_combo.clear()
        idx = 0
        graph_path = settings.graph_path
        if not os.path.exists(graph_path):
            self.ui.router_combo.addItem(
                'Verzeichnis mit Routern nicht gefunden')
            self.ui.router_combo.setEnabled(False)
            self.ui.create_router_button.setEnabled(False)
        else:
            # subdirectories in graph-dir are treated as routers by OTP
            for i, subdir in enumerate(os.listdir(graph_path)):
                path = os.path.join(graph_path, subdir)
                if os.path.isdir(path):
                    graph_file = os.path.join(path, 'Graph.obj')
                    if os.path.exists(graph_file):
                        self.ui.router_combo.addItem(subdir)
                        if saved_router == subdir:
                            idx = i
            self.ui.router_combo.setEnabled(True)
            self.ui.create_router_button.setEnabled(True)
        self.ui.router_combo.setCurrentIndex(idx)

    def start_origin_destination(self):
        if not self.ui.router_combo.isEnabled():
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Es ist kein gültiger Router eingestellt')
            msg_box.exec_()
            return

        # update postprocessing settings
        postproc = config.settings['post_processing']
        agg_acc = postproc['aggregation_accumulation']
        agg_acc['active'] = False
        best_of = ''
        if self.ui.bestof_check.isChecked():
            best_of = self.ui.bestof_edit.value()
        postproc['best_of'] = best_of
        details = self.ui.details_check.isChecked()
        postproc['details'] = details
        dest_data = self.ui.dest_data_check.isChecked()
        postproc['dest_data'] = dest_data
        if self.ui.orig_dest_csv_check.checkState():
            file_preset = '{}-{}-{}.csv'.format(
                self.ui.router_combo.currentText(),
                self.ui.origins_combo.currentText(),
                self.ui.destinations_combo.currentText()
                )

            file_preset = os.path.join(self.prev_directory, file_preset)
            target_file = browse_file(file_preset,
                                      u'Ergebnisse speichern unter',
                                      CSV_FILTER, parent=self.ui)
            if not target_file:
                return
            self.prev_directory = os.path.split(target_file)[0]
        else:
            target_file = None
        add_results = self.ui.orig_dest_add_check.isChecked()
        result_layer_name = None
        if add_results:
            preset = 'results-{}-{}'.format(
                self.ui.router_combo.currentText(),
                self.ui.origins_combo.currentText())
            result_layer_name, ok = QInputDialog.getText(
                None, 'Layer benennen',
                'Name der zu erzeugenden Ergebnistabelle:',
                QLineEdit.Normal,
                preset)
            if not ok:
                return
        self.call(target_file=target_file, add_results=add_results,
                  result_layer_name=result_layer_name)

    def call(self, target_file=None, origin_layer=None, destination_layer=None,
             add_results=False, join_results=False, result_layer_name=None):
        now_string = datetime.now().strftime(settings.DATETIME_FORMAT)

        # update settings and save them
        self.save()

        # LAYERS
        if origin_layer is None:
            origin_layer = self.layer_list[
                self.ui.origins_combo.currentIndex()]
        if destination_layer is None:
            destination_layer = self.layer_list[
                self.ui.destinations_combo.currentIndex()]

        if origin_layer==destination_layer:
            msg_box = QMessageBox()
            reply = msg_box.question(
                self.ui,
                'Hinweis',
                'Die Layer mit Origins und Destinations sind identisch.\n'+
                'Soll die Berechnung trotzdem gestartet werden?',
                QMessageBox.Ok, QMessageBox.Cancel)
            if reply == QMessageBox.Cancel:
                return

        working_dir = os.path.dirname(__file__)

        # write config to temporary directory with additional meta infos
        tmp_dir = tempfile.mkdtemp()
        config_xml = os.path.join(tmp_dir, 'config.xml')
        meta = {
            'date_of_calculation': now_string,
            'user': getpass.getuser()
        }
        config.write(config_xml, hide_inactive=True, meta=meta)

        # convert layers to csv and write them to temporary directory
        orig_tmp_filename = os.path.join(tmp_dir, 'origins.csv')
        dest_tmp_filename = os.path.join(tmp_dir, 'destinations.csv')

        wgs84 = QgsCoordinateReferenceSystem(4326)
        non_geom_fields = get_non_geom_indices(origin_layer)
        selected_only = (self.ui.selected_only_check.isChecked() and
                         origin_layer.selectedFeatureCount() > 0)
        QgsVectorFileWriter.writeAsVectorFormat(
            origin_layer,
            orig_tmp_filename,
            "utf-8",
            wgs84,
            "CSV",
            onlySelected=selected_only,
            attributes=non_geom_fields,
            layerOptions=["GEOMETRY=AS_YX"])

        non_geom_fields = get_non_geom_indices(destination_layer)
        selected_only = (self.ui.selected_only_check.isChecked() and
                         destination_layer.selectedFeatureCount() > 0)
        QgsVectorFileWriter.writeAsVectorFormat(
            destination_layer,
            dest_tmp_filename,
            "utf-8",
            wgs84,
            "CSV",
            onlySelected=selected_only,
            attributes=non_geom_fields,
            layerOptions=["GEOMETRY=AS_YX"])

        print('wrote origins and destinations to temporary folder "{}"'.format(
            tmp_dir))

        if target_file is not None:
            # copy config to file with similar name as results file
            dst_config = os.path.splitext(target_file)[0] + '-config.xml'
            shutil.copy(config_xml, dst_config)
        else:
            target_file = os.path.join(tmp_dir, 'results.csv')

        target_path = os.path.dirname(target_file)

        if not os.path.exists(target_path):
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Sie haben keinen gültigen Dateipfad angegeben.')
            msg_box.exec_()
            return
        elif not os.access(target_path, os.W_OK):
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Sie benötigen Schreibrechte im Dateipfad {}!'
                .format(target_path))
            msg_box.exec_()
            return

        otp_jar=self.ui.otp_jar_edit.text()
        if not os.path.exists(otp_jar):
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Die angegebene OTP Datei existiert nicht!')
            msg_box.exec_()
            return
        jython_jar=self.ui.jython_edit.text()
        if not os.path.exists(jython_jar):
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Der angegebene Jython Interpreter existiert nicht!')
            msg_box.exec_()
            return
        java_executable = self.ui.java_edit.text()
        memory = self.ui.memory_edit.value()
        if not os.path.exists(java_executable):
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Der angegebene Java-Pfad existiert nicht!')
            msg_box.exec_()
            return
        # ToDo: add parameter after java, causes errors atm
        # basic cmd is same for all evaluations
        cmd = '''"{java_executable}" -Xmx{ram_GB}G -jar "{jython_jar}"
        -Dpython.path="{otp_jar}"
        {wd}/otp_batch.py
        --config "{config_xml}"
        --origins "{origins}" --destinations "{destinations}"
        --target "{target}" --nlines {nlines}'''

        cmd = cmd.format(
            java_executable=java_executable,
            jython_jar=jython_jar,
            otp_jar=otp_jar,
            wd=working_dir,
            ram_GB=memory,
            config_xml = config_xml,
            origins=orig_tmp_filename,
            destinations=dest_tmp_filename,
            target=target_file,
            nlines=PRINT_EVERY_N_LINES
        )

        times = config.settings['time']
        arrive_by = times['arrive_by']
        if arrive_by == True or arrive_by == 'True':
            n_points = destination_layer.featureCount()
        else:
            n_points = origin_layer.featureCount()

        time_batch = times['time_batch']
        batch_active = time_batch['active']
        if batch_active == 'True' or batch_active == True:
            dt_begin = datetime.strptime(times['datetime'], DATETIME_FORMAT)
            dt_end = datetime.strptime(time_batch['datetime_end'],
                                       DATETIME_FORMAT)
            n_iterations = ((dt_end - dt_begin).total_seconds() /
                            (int(time_batch['time_step']) * 60) + 1)
        else:
            n_iterations = 1

        diag = ExecOTPDialog(cmd,
                             parent=self.ui,
                             auto_start=True,
                             n_points=n_points,
                             n_iterations=n_iterations,
                             points_per_tick=PRINT_EVERY_N_LINES)
        diag.exec_()

        # not successful or no need to add layers to QGIS ->
        # just remove temporary files
        if not diag.success or (not add_results and not join_results):
            shutil.rmtree(tmp_dir)
            return

        ### add/join layers in QGIS after OTP is done ###

        if result_layer_name is None:
            result_layer_name = 'results-{}-{}'.format(
                self.ui.router_combo.currentText(),
                self.ui.origins_combo.currentText())
            result_layer_name += '-' + now_string
        # WARNING: csv layer is only link to file,
        # if temporary is removed you won't see anything later
        #result_layer = self.iface.addVectorLayer(target_file,
                                                 #result_layer_name,
                                                 #'delimitedtext')
        uri = 'file:///' + target_file + '?type=csv&delimiter=;'
        result_layer = QgsVectorLayer(uri, result_layer_name, 'delimitedtext')
        QgsProject.instance().addMapLayer(result_layer)

        if join_results:
            join = QgsVectorLayerJoinInfo()
            join.setJoinLayerId(result_layer.id())
            join.setJoinFieldName('origin id')
            join.setTargetFieldName(config.settings['origin']['id_field'])
            join.setUsingMemoryCache(True)
            join.setJoinLayer(result_layer)
            origin_layer.addJoin(join)

    def create_router(self):
        java_executable = settings.system['java']
        otp_jar = settings.system['otp_jar_file']
        if not os.path.exists(otp_jar):
            msg_box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning, "Fehler",
                'Die angegebene OTP JAR Datei existiert nicht!')
            msg_box.exec_()
            return
        if not os.path.exists(java_executable):
            msg_box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning, "Fehler",
                'Der angegebene Java-Pfad existiert nicht!')
            msg_box.exec_()
            return
        graph_path = settings.graph_path
        memory = settings.system['reserved']
        diag = RouterDialog(graph_path, java_executable, otp_jar,
                            memory=memory, parent=self.ui)
        diag.exec_()
        self.setup_routers()

    def show_info(self):
        diag = InfoDialog(parent=self.ui)
        diag.exec_()

    def show_settings(self):
        diag = SettingsDialog(parent=self.ui)
        ok = diag.show()
        if ok:
            self.setup_projects()

    def open_manual(self):
        webbrowser.open_new(MANUAL_URL)

    def close(self):
        '''
        override, set inactive on close
        '''
        try:
            self.ui.close()
        # ui might already be deleted by QGIS
        except RuntimeError:
            pass

    def show(self):
        '''
        show the widget inside QGIS
        '''
        self.ui.show()


def get_geometry_fields(layer):
    '''return the names of the geometry fields of a given layer'''
    geoms = []
    for field in layer.fields():
        if field.typeName() == 'geometry':
            geoms.append(field.name())
    return geoms

def get_non_geom_indices(layer):
    '''return the indices of all fields of a given layer except the geometry fields'''
    indices = []
    for i, field in enumerate(layer.fields()):
        if field.typeName() != 'geometry':
            indices.append(i)
    return indices

def csv_remove_columns(csv_filename, columns):
    '''remove the given columns from a csv file with header'''
    tmp_fn = csv_filename + 'tmp'
    os.rename(csv_filename, tmp_fn)
    with open(csv_filename, 'a') as csv_file, open(tmp_fn, 'r') as tmp_csv_file:
        reader = csv.DictReader(tmp_csv_file)
        fieldnames = reader.fieldnames[:]
        for column in columns:
            if column in fieldnames:
                fieldnames.remove(column)
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            for column in columns:
                del row[column]
            writer.writerow(row)

    os.remove(tmp_fn)