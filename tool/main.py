from builtins import str
from builtins import range
from builtins import object
import os
from PyQt5 import uic
from PyQt5.QtCore import (QSettings, QTranslator, qVersion,
                          QCoreApplication, QProcess, QDateTime,
                          QVariant, QLocale, QDate, QObject)
from PyQt5.QtWidgets import (QAction, QListWidgetItem, QCheckBox,
                             QMessageBox, QLabel, QDoubleSpinBox, QMainWindow,
                             QFileDialog, QInputDialog, QLineEdit)
from PyQt5.QtGui import QIcon
from sys import platform

from gruenflaechenotp.tool.base.project import (ProjectManager, settings)
from gruenflaechenotp.tool.dialogs import (ExecOTPDialog, RouterDialog, InfoDialog,
                                           SettingsDialog, NewProjectDialog)
from gruenflaechenotp.tool.base.database import Workspace
from qgis._core import (QgsVectorLayer, QgsVectorLayerJoinInfo,
                        QgsCoordinateReferenceSystem, QgsField)
from qgis.core import QgsVectorFileWriter, QgsProject
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


class OTPMainWindow(QObject):
    def __init__(self, on_close=None, parent=None):
        """Constructor."""
        super().__init__(parent)

        self.ui = QMainWindow()
        uic.loadUi(main_form, self.ui)
        self.project_manager = ProjectManager()
        graph_path = self.project_manager.settings.graph_path
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

        # router
        #self.fill_router_combo()
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
            self.project_manager.active_project = project
            self.ui.project_combo.addItem(project.name, project)
            self.ui.project_combo.setCurrentIndex(
                self.ui.project_combo.count() - 1)

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
            return
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
        reply = QMessageBox.question(
            self.ui, 'Projekt entfernen',
            f'Soll das Projekt "{project.name}" entfernt werden?\n'
            '(alle Projektdaten werden gelöscht)',
             QMessageBox.Yes, QMessageBox.No)
        if reply == QMessageBox.Yes:
            idx = self.ui.project_combo.currentIndex()
            if self.active_dockwidget:
                self.active_dockwidget.close()
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
                self.project_manager.remove_project(project)
                self.project_manager.active_project = None
                self.canvas.mapCanvasRefreshed.disconnect(on_refresh)
            self.canvas.mapCanvasRefreshed.connect(on_refresh)
            self.canvas.refreshAllLayers()

    def change_project(self, project):
        self.project_manager.active_project = project
        self.ui.tabWidget.setEnabled(True)
        # ToDo: load layers and settings
        pass

    def fill_router_combo(self):
        # try to keep old router selected
        saved_router = config.settings['router_config']['router']
        self.ui.router_combo.clear()
        idx = 0
        graph_path = self.ui.graph_path_edit.text()
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
        java_executable = self.ui.java_edit.text()
        otp_jar=self.ui.otp_jar_edit.text()
        if not os.path.exists(otp_jar):
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Die angegebene OTP JAR Datei existiert nicht!')
            msg_box.exec_()
            return
        if not os.path.exists(java_executable):
            msg_box = QMessageBox(
                QMessageBox.Warning, "Fehler",
                u'Der angegebene Java-Pfad existiert nicht!')
            msg_box.exec_()
            return
        graph_path = self.ui.graph_path_edit.text()
        memory = self.ui.memory_edit.value()
        diag = RouterDialog(graph_path, java_executable, otp_jar,
                            memory=memory,
                            parent=self.ui)
        diag.exec_()
        self.fill_router_combo()

    def show_info(self):
        diag = InfoDialog(parent=self.ui)
        diag.exec_()

    def show_settings(self):
        diag = SettingsDialog(parent=self.ui)
        diag.exec_()

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