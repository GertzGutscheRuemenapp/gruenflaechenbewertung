# -*- coding: utf-8 -*-
from builtins import str
import os
from PyQt5 import uic, QtCore, QtGui, QtWidgets
from qgis.gui import QgsMapLayerComboBox, QgsProjectionSelectionWidget
from qgis.core import QgsMapLayerProxyModel
import copy, os, re, sys, datetime
from sys import platform
from shutil import move
import re

from gruenflaechenotp.base.dialogs import Dialog, ProgressDialog
from gruenflaechenotp.base.project import settings, ProjectManager

XML_FILTER = u'XML-Dateien (*.xml)'
CSV_FILTER = u'Comma-seperated values (*.csv)'
JAR_FILTER = u'Java Archive (*.jar)'
ALL_FILE_FILTER = u'Java Executable (java.*)'

INFO_FORM_CLASS, _ = uic.loadUiType(os.path.join(
    settings.BASE_PATH, 'ui', 'info.ui'))
ROUTER_FORM_CLASS, _ = uic.loadUiType(os.path.join(
    settings.BASE_PATH, 'ui', 'router.ui'))
PROGRESS_FORM_CLASS, _ = uic.loadUiType(os.path.join(
    settings.BASE_PATH, 'ui', 'progress.ui'))

# WARNING: doesn't work in QGIS, because it doesn't support the QString module anymore (autocast to str)
try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

DEFAULT_STYLE = """
QProgressBar{
    border: 2px solid grey;
    border-radius: 5px;
    text-align: center
}

QProgressBar::chunk {
    background-color: lightblue;
    width: 10px;
    margin: 1px;
}
"""

FINISHED_STYLE = """
QProgressBar{
    border: 2px solid grey;
    border-radius: 5px;
    text-align: center
}

QProgressBar::chunk {
    background-color: green;
    width: 10px;
    margin: 1px;
}
"""

ABORTED_STYLE = """
QProgressBar{
    border: 2px solid red;
    border-radius: 5px;
    text-align: center
}

QProgressBar::chunk {
    background-color: red;
    width: 10px;
    margin: 1px;
}
"""

def parse_version(meta_file):
    regex = 'version=([0-9]+\.[0-9]+)'
    with open(meta_file, 'r') as f:
        lines = f.readlines()
    for line in lines:# Regex applied to each line
        match = re.search(regex, line)
        if match:
            return match.group(1)
    return 'not found'


class InfoDialog(QtWidgets.QDialog, INFO_FORM_CLASS):
    """
    Info Dialog
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent = parent
        self.setupUi(self)
        self.close_button.clicked.connect(self.close)
        wd = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        meta_file = os.path.join(wd, 'metadata.txt')
        if os.path.exists(meta_file):
            version = parse_version(meta_file)
        else:
            version = '-'
        self.version_label.setText('Version ' + version)


class NewProjectDialog(Dialog):
    '''
    dialog to select a layer and a name as inputs for creating a new project
    '''
    def __init__(self, placeholder='', excluded_names=[], **kwargs):
        self.placeholder = placeholder
        self.excluded_names = excluded_names
        super().__init__(**kwargs)

    def setupUi(self):
        '''
        set up the user interface
        '''
        self.setMinimumWidth(500)
        self.setWindowTitle('Neues Projekt erstellen')

        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel('Name des Projekts')
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setText(self.placeholder)
        self.name_edit.textChanged.connect(self.validate)
        layout.addWidget(self.label)
        layout.addWidget(self.name_edit)

        def toggle_check(enabled):
            settings.prefill_project = enabled
            settings.write()
        self.lichtenberg_check = QtWidgets.QCheckBox(
            'Das Projekt mit den Daten von Lichtenberg initialisieren')
        self.lichtenberg_check.setChecked(settings.prefill_project)
        self.lichtenberg_check.toggled.connect(toggle_check)
        layout.addWidget(self.lichtenberg_check)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        #spacer = QtWidgets.QSpacerItem(
            #20, 40, QtWidgets.QSizePolicy.Minimum,
            #QtWidgets.QSizePolicy.Expanding)
        #layout.addItem(spacer)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self)
        self.ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.validate()

    def validate(self):
        '''
        validate current input of name and layer, set the status label according
        to validation result
        '''
        name = str(self.name_edit.text())
        status_text = ''
        regexp = re.compile('[\\\/\:*?\"\'<>|]')
        error = False
        if name and regexp.search(name):
            status_text = ('Der Name darf keines der folgenden Zeichen '
                           'enthalten: \/:*?"\'<>|')
            error = True
        elif name in self.excluded_names:
            status_text = (
                f'Ein Projekt mit dem Namen {name} existiert bereits!\n'
                'Die Namen müssen einzigartig sein.')
            error = True

        self.status_label.setText(status_text)
        self.ok_button.setEnabled(not error and len(name) > 0)

    def show(self):
        '''
        show dialog and return selections made by user
        '''
        confirmed = self.exec_()
        if confirmed:
            return (confirmed, self.name_edit.text(),
                    self.lichtenberg_check.isChecked())
        return False, None, False


class NewRouterDialog(Dialog):
    def __init__(self, placeholder='', excluded_names=[], **kwargs):
        self.placeholder = placeholder
        self.excluded_names = excluded_names
        super().__init__(**kwargs)

    def setupUi(self):
        self.setMinimumSize(500, 200)
        self.setWindowTitle('Neuen Router erstellen')

        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel('Name des Routers')
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setText(self.placeholder)
        self.name_edit.textChanged.connect(self.validate)
        layout.addWidget(self.label)
        layout.addWidget(self.name_edit)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self)
        self.ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.validate()

    def validate(self):
        '''
        validate current input of name and layer, set the status label according
        to validation result
        '''
        name = str(self.name_edit.text())
        status_text = ''
        regexp = re.compile('[ äüöÄÜÖß\\\/\:*?\"\'<>|]')
        error = False
        if name and regexp.search(name):
            status_text = ('Der Name darf keine Freizeichen, keine Umlaute '
                           'und keines der folgenden Zeichen enthalten: '
                           '\/:*?"\'<>|')
            error = True
        elif name in self.excluded_names:
            status_text = (
                f'Ein Router mit dem Namen {name} existiert bereits!\n'
                'Die Namen müssen einzigartig sein.')
            error = True

        self.status_label.setText(status_text)
        self.ok_button.setEnabled(not error and len(name) > 0)

    def show(self):
        '''
        show dialog and return selections made by user
        '''
        confirmed = self.exec_()
        if confirmed:
            return (confirmed, self.name_edit.text())
        return False, None


class ImportLayerDialog(Dialog):

    def __init__(self, title='Layer importieren',
                 filter_class=QgsMapLayerProxyModel.VectorLayer,
                 help_text='', required_fields=[],
                 optional_fields=[], **kwargs):
        self.title = title
        self.filter_class = filter_class
        self.optional_fields = optional_fields
        self.required_fields = required_fields
        self.help_text = help_text
        self.project_manager = ProjectManager()
        super().__init__(**kwargs)

    def setupUi(self):
        '''
        set up the user interface
        '''
        self.setMinimumWidth(500)
        self.setMaximumWidth(500)
        self.setWindowTitle(self.title)

        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel('Zu importierender Layer')
        self.input_layer_combo = QgsMapLayerComboBox()
        self.input_layer_combo.setFilters(self.filter_class)
        self.input_layer_combo.layerChanged.connect(self.layer_changed)
        layout.addWidget(label)
        layout.addWidget(self.input_layer_combo)

        label = QtWidgets.QLabel('Ausgangsprojektion des zu importierenden Layers')
        self.projection_combo = QgsProjectionSelectionWidget()
        layout.addWidget(label)
        layout.addWidget(self.projection_combo)

        if self.optional_fields:
            spacer = QtWidgets.QSpacerItem(0, 20, QtWidgets.QSizePolicy.Fixed)
            layout.addItem(spacer)

        def add_input(label_text):
            label = QtWidgets.QLabel(label_text)
            combo = QtWidgets.QComboBox()
            layout.addWidget(label)
            layout.addWidget(combo)
            return combo

        self._required_inputs = []
        for field_name, field_label in self.required_fields:
            r_input = add_input(field_label)
            self._required_inputs.append(r_input)
            r_input.currentTextChanged.connect(self.validate)

        self._optional_inputs = []
        for field_name, field_label in self.optional_fields:
            self._optional_inputs.append(add_input(f'{field_label} (optional)'))

        if self.help_text:
            spacer = QtWidgets.QSpacerItem(0, 10, QtWidgets.QSizePolicy.Fixed)
            label = QtWidgets.QLabel(self.help_text)
            label.setWordWrap(True)
            layout.addItem(spacer)
            layout.addWidget(label)

        spacer = QtWidgets.QSpacerItem(0, 10, QtWidgets.QSizePolicy.Fixed)
        self.error_label = QtWidgets.QLabel()
        self.error_label.setStyleSheet('color: red')
        layout.addItem(spacer)
        layout.addWidget(self.error_label)

        spacer = QtWidgets.QSpacerItem(0, 10, QtWidgets.QSizePolicy.Minimum,
                                       QtWidgets.QSizePolicy.Expanding)
        layout.addItem(spacer)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self)
        self.ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.input_layer_combo.layerChanged.connect(self.validate)
        self.projection_combo.crsChanged.connect(self.validate)
        self.layer_changed(self.input_layer_combo.currentLayer())
        self.validate()

    def layer_changed(self, layer):
        if not layer:
            return
        field_names = ['-'] + [f.name() for f in layer.fields()]
        for _input in self._optional_inputs + self._required_inputs:
            _input.clear()
            _input.addItems(field_names)

        crs = layer.crs()
        self.projection_combo.setCrs(crs)

    def validate(self):
        error_message = None
        layer = self.input_layer_combo.currentLayer()
        project = self.project_manager.active_project
        if not layer:
            error_message = 'Kein Layer ausgewählt'
        elif not layer.isValid():
            error_message = 'Der gewählte Layer enthält Fehler'
        elif not self.projection_combo.crs().authid():
            error_message = 'Keine Projektion ausgewählt'
        elif project.data.base_path in layer.source():
            error_message = 'Der ausgewählte Layer darf nicht im aktiven Projekt liegen'
        if not error_message:
            for r_input in self._required_inputs:
                if r_input.currentText() == '-':
                    error_message = 'Benötigtes Eingabefeld nicht ausgewählt'
                    break

        self.error_label.setText(error_message)
        self.ok_button.setEnabled(not error_message)

    def show(self):
        '''
        show dialog and return selections made by user
        '''
        confirmed = self.exec_()
        if confirmed:
            layer = self.input_layer_combo.currentLayer()
            o_fields = [(f_in, f_out ) for f_in, f_out in zip(
                [i.currentText() for i in self._optional_inputs],
                [f[0] for f in self.optional_fields]) if f_in != '-']
            r_fields = list(zip([i.currentText() for i in self._required_inputs],
                                [f[0] for f in self.required_fields]))
            return confirmed, layer, self.projection_combo.crs(), o_fields + r_fields
        return False, None, None, None


class ExecOTPDialog(ProgressDialog):
    """
    ProgressDialog extented by an executable external process

    Parameters
    ----------
    n_iterations: number of iterations (like multiple time windows)
    n_points: number of points to calculate in one iteration
    points_per_tick: how many points are calculated before showing progress
    """
    def __init__(self, command, n_points=0, points_per_tick=50,
                 title='OTP Routing', **kwargs):
        super().__init__(None, title=title, **kwargs)

        # QProcess object for external app
        self.process = QtCore.QProcess(self)
        self.command = command
        self.success = False
        self.ticks = 0.

        # Just to prevent accidentally running multiple times
        # Disable the button when process starts, and enable it when it finishes
        self.process.finished.connect(self._success)

        # how often will the stdout-indicator written before reaching 100%
        n_ticks = float(n_points) / points_per_tick
        tick_indicator = 'Processing:'

        def show_progress():
            out = self.process.readAllStandardOutput()
            out = str(out.data(), encoding='utf-8')
            err = self.process.readAllStandardError()
            try:
                err = str(err.data(), encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    str(err.data(), encoding='ISO-8859-1')
                except:
                    err = ''
            if len(out):
                self.show_status(out)
                if tick_indicator in out and n_ticks:
                    self.ticks += 100 / n_ticks
                    self.progress_bar.setValue(min(100, int(self.ticks)))
            if len(err):
                self.on_error(err)

        self.process.readyReadStandardOutput.connect(show_progress)
        self.process.readyReadStandardError.connect(show_progress)
        def error(sth):
            self.error = True
        self.process.errorOccurred.connect(error)

    def run(self):
        super().run()
        self.ticks = 0
        self.show_status('<br><b>Routing mit dem OpenTripPlanner</b><br>')
        self.show_status('Script: <i>' + self.command + '</i>')
        self.process.start(self.command)

    def stop(self):
        self.process.kill()
        self.error = True
        self.success = False
        super().stop()


class ExecBuildRouterDialog(ProgressDialog):
    def __init__(self, folder, java_executable, otp_jar, memory=2, **kwargs):
        super().__init__(None, title='Router bauen', **kwargs)
        self.folder = folder
        self.command = f'''
        "{java_executable}" -Xmx{memory}G -jar "{otp_jar}"
        --build "{folder}"
        '''
        self.success = False
        self.process = QtCore.QProcess(self)
        self.process.finished.connect(self._success)

        def show_progress():
            out = self.process.readAllStandardOutput()
            out = str(out.data(), encoding='utf-8')
            err = self.process.readAllStandardError()
            err = str(err.data(), encoding='utf-8')
            if len(out):
                self.show_status(out)
            if len(err): self.show_status(err)

        self.process.readyReadStandardOutput.connect(show_progress)
        self.process.readyReadStandardError.connect(show_progress)
        def error(sth):
            self.error = True
        self.process.errorOccurred.connect(error)

    def run(self):
        super().run()
        self.show_status('<br><b>Bauen des Routers</b><br>')
        self.show_status('Entferne existierenden Graph...')
        graph_file = os.path.join(self.folder, 'Graph.obj')
        if os.path.exists(graph_file):
            os.remove(graph_file)
        self.show_status('Script: <i>' + self.command + '</i>')
        self.process.start(self.command)

    def stop(self):
        self.process.kill()
        self.error = True
        self.success = False
        super().stop()


class SettingsDialog(Dialog):
    ui_file = 'settings.ui'

    def setupUi(self):
        self.button_box.accepted.connect(self.save)
        self.button_box.accepted.connect(self.close)
        self.otp_jar_browse_button.clicked.connect(
            lambda: self.browse_jar(self.otp_jar_edit, 'OTP JAR wählen'))
        self.jython_browse_button.clicked.connect(
            lambda: self.browse_jar(self.jython_edit,
                                    'Jython Standalone JAR wählen'))
        self.graph_path_browse_button.clicked.connect(
            lambda: self.browse_path(self.graph_path_edit,
                                     'OTP Router Verzeichnis wählen'))
        self.project_path_browse_button.clicked.connect(
            lambda: self.browse_path(self.project_path_edit,
                                     'Projektverzeichnis wählen'))
        self.josm_jar_browse_button.clicked.connect(
            lambda: self.browse_jar(self.josm_jar_edit, 'JOSM JAR wählen'))
        self.java_browse_button.clicked.connect(self.browse_java)
        self.search_java_button.clicked.connect(self.auto_java)
        self.reset_button.clicked.connect(self.reset)
        self.load_settings()

    def load_settings(self):
        self.project_path_edit.setText(settings.project_path)
        self.graph_path_edit.setText(settings.graph_path)

        self.java_edit.setText(settings.system['java'])
        self.jython_edit.setText(settings.system['jython_jar_file'])
        self.otp_jar_edit.setText(settings.system['otp_jar_file'])
        self.josm_jar_edit.setText(settings.system['josm_jar_file'])
        self.cpu_edit.setValue(settings.system['n_threads'])
        self.memory_edit.setValue(settings.system['reserved'])

    def save(self):
        settings.project_path = self.project_path_edit.text()
        settings.graph_path = self.graph_path_edit.text()

        settings.system['java'] = self.java_edit.text()
        settings.system['jython_jar_file'] = self.jython_edit.text()
        settings.system['otp_jar_file'] = self.otp_jar_edit.text()
        settings.system['josm_jar_file'] = self.josm_jar_edit.text()
        settings.system['n_threads'] = self.cpu_edit.value()
        settings.system['reserved'] = self.memory_edit.value()

        settings.write()

    def reset(self):
        settings.reset_to_defaults()
        self.load_settings()

    def auto_java(self):
        '''
        you don't have access to the environment variables of the system,
        use some tricks depending on the system
        '''
        java_file = None
        if platform.startswith('win'):
            import winreg
            java_key = None
            try:
                #64 Bit
                java_key = winreg.OpenKey(
                    winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE),
                    'SOFTWARE\JavaSoft\Java Runtime Environment'
                )
            except WindowsError:
                try:
                    #32 Bit
                    java_key = winreg.OpenKey(
                        winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE),
                        'SOFTWARE\WOW6432Node\JavaSoft\Java Runtime Environment'
                    )
                except WindowsError:
                    pass
            if java_key:
                try:
                    ver_key = winreg.OpenKey(java_key, "1.8")
                    path = os.path.join(
                        winreg.QueryValueEx(ver_key, 'JavaHome')[0],
                        'bin', 'java.exe'
                    )
                    if os.path.exists(path):
                        java_file = path
                except WindowsError:
                    pass
        if platform.startswith('linux'):
            # that is just the default path
            path = '/usr/bin/java'
            # ToDo: find right version
            if os.path.exists(path):
                java_file = path
        if java_file:
            self.java_edit.setText(java_file)
        else:
            msg_box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning, "Fehler",
                u'Die automatische Suche nach Java 1.8 ist fehlgeschlagen. '
                'Bitte suchen Sie die ausführbare Datei manuell.')
            msg_box.exec_()


    def browse_java(self):
        java_file = browse_file(self.java_edit.text(),
                                'Java Version 1.8 wählen',
                                ALL_FILE_FILTER, save=False,
                                parent=self)
        if not java_file:
            return
        self.java_edit.setText(java_file)

    def browse_jar(self, edit, text):
        jar_file = browse_file(edit.text(),
                               text, JAR_FILTER,
                               save=False, parent=self)
        if not jar_file:
            return
        edit.setText(jar_file)

    def browse_path(self, edit, text):
        path = str(QtWidgets.QFileDialog.getExistingDirectory(
            self, text, edit.text()))
        if not path:
            return
        edit.setText(path)

def browse_file(file_preset, title, file_filter, save=True, parent=None):

    if save:
        browse_func = QtWidgets.QFileDialog.getSaveFileName
    else:
        browse_func = QtWidgets.QFileDialog.getOpenFileName

    filename = str(
        browse_func(
            parent=parent,
            caption=title,
            directory=file_preset,
            filter=file_filter
        )[0]
    )
    return filename
