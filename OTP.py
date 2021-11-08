# -*- coding: utf-8 -*-
"""
/***************************************************************************
 OTP
                                 A QGIS plugin
 OTP Erreichbarkeitsanalyse
                              -------------------
        begin                : 2016-04-08
        git sha              : $Format:%H$
        author               : Christoph Franke
        copyright            : (C) 2016 by GGR
        email                : franke@ggr-planung.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from builtins import str
from builtins import range
from builtins import object
import os
from PyQt5.QtCore import (QSettings, QTranslator, qVersion,
                          QCoreApplication, QProcess, QDateTime,
                          QVariant, QLocale, QDate)
from PyQt5.QtWidgets import (QAction, QListWidgetItem, QCheckBox,
                             QMessageBox, QLabel, QDoubleSpinBox,
                             QFileDialog, QInputDialog, QLineEdit)
from PyQt5.QtGui import QIcon
from sys import platform

from .config import (AVAILABLE_TRAVERSE_MODES,
                     DATETIME_FORMAT, AGGREGATION_MODES, ACCUMULATION_MODES,
                     DEFAULT_FILE, CALC_REACHABILITY_MODE,
                     VM_MEMORY_RESERVED, Config, MANUAL_URL)
from .dialogs import (ExecOTPDialog, RouterDialog, InfoDialog, SettingsDialog,
                      OTPMainWindow)
from qgis._core import (QgsVectorLayer, QgsVectorLayerJoinInfo,
                        QgsCoordinateReferenceSystem, QgsField)
from qgis.core import QgsVectorFileWriter, QgsProject
import locale
import tempfile
import shutil
import getpass
import csv
import webbrowser

from datetime import datetime

TITLE = "OpenTripPlanner Plugin"

# result-modes
ORIGIN_DESTINATION = 0
AGGREGATION = 1
ACCUMULATION = 2
REACHABILITY = 3

# how many results are written while running batch script
PRINT_EVERY_N_LINES = 100

XML_FILTER = u'XML-Dateien (*.xml)'
CSV_FILTER = u'Comma-seperated values (*.csv)'
JAR_FILTER = u'Java Archive (*.jar)'
ALL_FILE_FILTER = u'Java Executable (java.*)'

config = Config()


class OTP(object):
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        QLocale.setDefault(QLocale('de'))
        loc = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'OTP_{}.qm'.format(loc))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.ui = OTPMainWindow()# on_close=self.save)
        self.ui.setWindowTitle(TITLE)

        # store last used directory for saving files (init with home dir)
        self.prev_directory = os.environ['HOME']

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&OpenTripPlanner')
        self.toolbar = self.iface.addToolBar(u'OpenTripPlanner')
        self.toolbar.setObjectName(u'OpenTripPlanner')

        config.read(do_create=True)
        self.config_control = ConfigurationControl(self.ui)

        self.setup_UI()

    def save(self):
        '''
        save config
        '''
        self.config_control.update()
        self.config_control.save()

    def setup_UI(self):
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
        #self.setup_projects()


    def setup_projects(self):
        '''
        fill project combobox with available projects
        '''
        self.project_manager.active_project = None

        self.ui.project_combo.blockSignals(True)
        self.ui.project_combo.clear()
        self.ui.project_combo.addItem('Projekt wählen')
        self.ui.project_combo.model().item(0).setEnabled(False)
        self.ui.domain_button.setEnabled(False)
        self.ui.definition_button.setEnabled(False)
        self.project_manager.reset_projects()
        for project in self.project_manager.projects:
            if project.name == '__test__':
                continue
            self.ui.project_combo.addItem(project.name, project)
        self.ui.project_combo.blockSignals(False)

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('OpenTripPlanner', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/OTP/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'OpenTripPlanner'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def create_project(self):
        pass

    def remove_project(self):
        pass

    def clone_project(self):
        pass

    def change_project(self):
        pass

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&OpenTripPlanner'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def set_date(self, time=None):
        date = self.ui.calendar_edit.selectedDate()
        # ToDo: if focus of user was on to_time, only change value in this one
        # but way below won't work, because focus changes, when calendar is
        # clicked
        #if self.dlg.to_time_edit.hasFocus():
            #self.dlg.to_time_edit.setDate(date)
        #else:
            #self.dlg.time_edit.setDate(date)
        self.ui.to_time_edit.setDate(date)
        self.ui.time_edit.setDate(date)
        if time:
            if isinstance(time, QDate):
                time = QDateTime(time).time()
            # QDate is lacking a time, so don't set it (only if QDateTime is)
            else:
                self.ui.time_edit.setTime(time)
            self.ui.to_time_edit.setTime(time)

    def toggle_arrival(self):
        '''
        enable/disable tabs, depending on whether arrival is checked or not
        '''
        is_arrival = self.ui.arrival_checkbox.checkState()
        acc_idx = self.ui.calculation_tabs.indexOf(self.ui.accumulation_tab)
        agg_idx = self.ui.calculation_tabs.indexOf(self.ui.aggregation_tab)
        reach_idx = self.ui.calculation_tabs.indexOf(self.ui.reachability_tab)
        acc_enabled = agg_enabled = reach_enabled = False

        if is_arrival:
            acc_enabled = True
            left_text = u'früheste Abfahrt'
            right_text = u'min vor Ankunftszeit'
        else:
            agg_enabled = reach_enabled = True
            left_text = u'späteste Ankunft'
            right_text = u'min nach Abfahrtszeit'

        self.ui.max_time_label_left.setText(left_text)
        self.ui.max_time_label_right.setText(right_text)

        self.ui.calculation_tabs.setTabEnabled(acc_idx, acc_enabled)
        self.ui.calculation_tabs.setTabEnabled(agg_idx, agg_enabled)
        self.ui.calculation_tabs.setTabEnabled(reach_idx, reach_enabled)

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

    def fill_layer_combos(self, layers=None):
        '''
        fill the combo boxes for selection of origin/destination layers with all
        available vector-layers.
        keep selections of previously selected layers, if possible
        '''
        if not layers:
            layers = [layer for layer in QgsProject.instance().mapLayers().values()]
        old_origin_layer = None
        old_destination_layer = None
        if len(self.layer_list) > 0:
            old_origin_layer = self.layer_list[
                self.ui.origins_combo.currentIndex()]
            old_destination_layer = self.layer_list[
                self.ui.destinations_combo.currentIndex()]

        self.layer_list = []
        self.ui.origins_combo.clear()
        self.ui.destinations_combo.clear()
        old_origin_idx = 0
        old_destination_idx = 0
        i = 0 # counter for QgsVectorLayers
        for layer in layers:
            if isinstance(layer, QgsVectorLayer):
                if layer == old_origin_layer:
                    old_origin_idx = i
                if layer == old_destination_layer:
                    old_destination_idx = i
                self.layer_list.append(layer)
                self.ui.origins_combo.addItem(layer.name())
                self.ui.destinations_combo.addItem(layer.name())
                i += 1

        # select active layer in comboboxes
        self.ui.origins_combo.setCurrentIndex(old_origin_idx)
        self.ui.destinations_combo.setCurrentIndex(old_destination_idx)

        # fill ids although there is already a signal/slot connection
        # (in __init__) to do this,
        # but if index doesn't change (idx == 0), signal doesn't fire (
        # so it maybe is done twice, but this is not performance-relevant)
        self.fill_id_combo(self.ui.origins_combo, self.ui.origins_id_combo)
        self.fill_id_combo(
            self.ui.destinations_combo, self.ui.destinations_id_combo)

        self.layers = layers

    def fill_id_combo(self, layer_combo, id_combo):
        '''
        fill a combo box (id_combo) with all fields of the currently selected
        layer in the given layer_combo.
        tries to keep same field as selected before
        WARNING: does not keep same field selected if layers are changed and
        rerun
        '''
        old_id_field = id_combo.currentText()
        id_combo.clear()
        if (len(self.layer_list) == 0 or
            (layer_combo.currentIndex() >= len(self.layer_list))):
            return
        layer = self.layer_list[layer_combo.currentIndex()]
        fields = layer.fields()
        old_idx = 0
        for i, field in enumerate(fields):
            if field.name() == old_id_field:
                old_idx = i
            id_combo.addItem(field.name())
        id_combo.setCurrentIndex(old_idx)

    def get_widget_values(self, layout):
        '''
        returns all currently set values in child widgets of given layout
        '''
        params = []
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, QDoubleSpinBox):
                params.append(str(widget.value()))
        return params

    def run(self):
        '''
        called every time, the plugin is (re)started (so don't connect slots
        to signals here, otherwise they may be connected multiple times)
        '''

        ## reload layer combos, if layers changed on rerun
        #layers = [layer for layer in QgsProject.instance().mapLayers().values()]
        #if layers != self.layers:
            #self.fill_layer_combos()

        ## reload routers on every run (they might be changed outside)
        #self.fill_router_combo()

        # show the dialog
        self.ui.show()

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
        now_string = datetime.now().strftime(DATETIME_FORMAT)

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


class ConfigurationControl(object):

    def __init__(self, ui):
        self.ui = ui

    def reset_to_default(self):
        '''
        reset Config.settings to default
        '''
        config.reset()
        self.apply()

    def apply(self):
        '''
        change state of UI (checkboxes, comboboxes) according to the Config.settings
        '''
        # ORIGIN
        origin_config = config.settings['origin']
        layer_idx = self.ui.origins_combo.findText(origin_config['layer'])
        # layer found
        if layer_idx >= 0:
            self.ui.origins_combo.setCurrentIndex(layer_idx)
            # if id is not found (returns -1) take first one (0)
            id_idx = max(self.ui.origins_id_combo.findText(origin_config['id_field']), 0)
            self.ui.origins_id_combo.setCurrentIndex(id_idx)
        # layer not found -> take first one
        else:
            self.ui.origins_combo.setCurrentIndex(0)

        # DESTINATION
        dest_config = config.settings['destination']
        layer_idx = self.ui.destinations_combo.findText(dest_config['layer'])
        # layer found
        if layer_idx >= 0:
            self.ui.destinations_combo.setCurrentIndex(layer_idx)
            # if id is not found (returns -1) take first one (0)
            id_idx = max(self.ui.destinations_id_combo.findText(dest_config['id_field']), 0)
            self.ui.destinations_id_combo.setCurrentIndex(id_idx)
        # layer not found -> take first one
        else:
            self.ui.destinations_combo.setCurrentIndex(0)

        # ROUTER
        graph_path = config.settings['router_config']['path']
        self.ui.graph_path_edit.setText(graph_path)

        router_config = config.settings['router_config']
        router = router_config['router']

        # if router is not found (returns -1) take first one (0)
        idx = max(self.ui.router_combo.findText(router), 0)

        items = [self.ui.router_combo.itemText(i) for i in range(self.ui.router_combo.count())]

        self.ui.router_combo.setCurrentIndex(idx)

        self.ui.max_time_edit.setValue(int(router_config['max_time_min']))
        self.ui.max_walk_dist_edit.setValue(int(router_config['max_walk_distance']))
        self.ui.walk_speed_edit.setValue(float(router_config['walk_speed']))
        self.ui.bike_speed_edit.setValue(float(router_config['bike_speed']))
        self.ui.clamp_edit.setValue(int(router_config['clamp_initial_wait_min']))
        self.ui.transfers_edit.setValue(int(router_config['max_transfers']))
        self.ui.pre_transit_edit.setValue(int(router_config['pre_transit_time_min']))
        wheelchair = router_config['wheel_chair_accessible'] in ['True', True]
        self.ui.wheelchair_check.setChecked(wheelchair)
        self.ui.max_slope_edit.setValue(float(router_config['max_slope']))

        # TRAVERSE MODES
        modes = router_config['traverse_modes']
        for index in range(self.ui.mode_list_view.count()):
            checkbox = self.ui.mode_list_view.itemWidget(self.ui.mode_list_view.item(index))
            if str(checkbox.text()) in modes :
                checkbox.setChecked(True)
            else:
                checkbox.setChecked(False)

        # TIMES
        times = config.settings['time']

        if times['datetime']:
            dt = datetime.strptime(times['datetime'], DATETIME_FORMAT)
        else:
            dt = datetime.now()
        self.ui.time_edit.setDateTime(dt)
        self.ui.calendar_edit.setSelectedDate(dt.date())

        time_batch = times['time_batch']

        smart_search = False #time_batch['smart_search'] in ['True', True]
        self.ui.smart_search_checkbox.setChecked(True)

        if time_batch['datetime_end']:
            dt = datetime.strptime(time_batch['datetime_end'], DATETIME_FORMAT)
        self.ui.to_time_edit.setDateTime(dt)
        active = time_batch['active'] in ['True', True]
        self.ui.time_batch_checkbox.setChecked(active)
        if time_batch['time_step']:
            self.ui.time_step_edit.setValue(int(time_batch['time_step']))

        arrive_by = times['arrive_by'] in ['True', True]
        self.ui.arrival_checkbox.setChecked(arrive_by)

        # SYSTEM SETTINGS
        sys_settings = config.settings['system']
        n_threads = int(sys_settings['n_threads'])
        memory = int(sys_settings['reserved'])
        otp_jar = sys_settings['otp_jar_file']
        jython_jar = sys_settings['jython_jar_file']
        java = sys_settings['java']
        self.ui.otp_jar_edit.setText(otp_jar)
        self.ui.jython_edit.setText(jython_jar)
        self.ui.java_edit.setText(java)
        self.ui.cpu_edit.setValue(n_threads)
        self.ui.memory_edit.setValue(memory)

    def update(self):
        '''
        update Config.settings according to the current state of the UI (checkboxes etc.)
        post processing not included! only written to config before calling otp (in call_otp()),
        because not relevant for UI (meaning it is set to default on startup)
        '''

        # LAYERS
        origin_config = config.settings['origin']
        origin_config['layer'] = self.ui.origins_combo.currentText()
        origin_config['id_field'] = self.ui.origins_id_combo.currentText()
        dest_config = config.settings['destination']
        dest_config['layer'] = self.ui.destinations_combo.currentText()
        dest_config['id_field'] = self.ui.destinations_id_combo.currentText()

        # ROUTER
        router_config = config.settings['router_config']
        router_config['router'] = self.ui.router_combo.currentText()
        router_config['max_time_min'] = self.ui.max_time_edit.value()
        router_config['max_walk_distance'] = self.ui.max_walk_dist_edit.value()
        router_config['walk_speed'] = self.ui.walk_speed_edit.value()
        router_config['bike_speed'] = self.ui.bike_speed_edit.value()
        router_config['max_transfers'] = self.ui.transfers_edit.value()
        router_config['pre_transit_time_min'] = self.ui.pre_transit_edit.value()
        router_config['wheel_chair_accessible'] = self.ui.wheelchair_check.isChecked()
        router_config['max_slope'] = self.ui.max_slope_edit.value()
        router_config['clamp_initial_wait_min'] = self.ui.clamp_edit.value()

        # TRAVERSE MODES
        selected_modes = []
        for index in range(self.ui.mode_list_view.count()):
            checkbox = self.ui.mode_list_view.itemWidget(self.ui.mode_list_view.item(index))
            if checkbox.isChecked():
                selected_modes.append(str(checkbox.text()))
        router_config['traverse_modes'] = selected_modes

        # TIMES
        times = config.settings['time']
        dt = self.ui.time_edit.dateTime()
        times['datetime'] = dt.toPyDateTime().strftime(DATETIME_FORMAT)
        time_batch = times['time_batch']

        smart_search = self.ui.smart_search_checkbox.isChecked()
        time_batch['smart_search'] = smart_search

        active = self.ui.time_batch_checkbox.isChecked()
        time_batch['active'] = active
        end = step = ''
        if active:
            dt = self.ui.to_time_edit.dateTime()
            end = dt.toPyDateTime().strftime(DATETIME_FORMAT)
            step = self.ui.time_step_edit.value()
        time_batch['datetime_end'] = end
        time_batch['time_step'] = step

        is_arrival = self.ui.arrival_checkbox.isChecked()
        times['arrive_by'] = is_arrival

        # SYSTEM SETTINGS
        sys_settings = config.settings['system']
        n_threads = self.ui.cpu_edit.value()
        memory = self.ui.memory_edit.value()
        otp_jar = self.ui.otp_jar_edit.text()
        jython_jar = self.ui.jython_edit.text()
        java = self.ui.java_edit.text()
        graph_path = self.ui.graph_path_edit.text()
        sys_settings['n_threads'] = n_threads
        sys_settings['reserved'] = memory
        sys_settings['otp_jar_file'] = otp_jar
        sys_settings['jython_jar_file'] = jython_jar
        sys_settings['java'] = java
        config.settings['router_config']['path'] = graph_path

    def save(self):
        config.write()

    def save_as(self):
        '''
        save config in selectable file
        '''
        filename = browse_file('', 'Einstellungen speichern unter', XML_FILTER)
        if filename:
            self.update()
            config.write(filename)

    def read(self):
        '''
        read config from selectable file
        '''
        filename = browse_file('', 'Einstellungen aus Datei laden',
                               XML_FILTER, save=False)
        if filename:
            config.read(filename)
            self.apply()

def browse_file(file_preset, title, file_filter, save=True, parent=None):

    if save:
        browse_func = QFileDialog.getSaveFileName
    else:
        browse_func = QFileDialog.getOpenFileName

    filename = str(
        browse_func(
            parent=parent,
            caption=title,
            directory=file_preset,
            filter=file_filter
        )[0]
    )
    return filename

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

