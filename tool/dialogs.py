# -*- coding: utf-8 -*-
from builtins import str
import os
from PyQt5 import uic, QtCore, QtGui, QtWidgets
from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsMapLayerProxyModel
import copy, os, re, sys, datetime
from sys import platform
from shutil import move
import re

# Initialize Qt resources from file resources.py
from gruenflaechenotp import resources
from gruenflaechenotp.tool.base.project import settings, ProjectManager
from gruenflaechenotp.tool.tables import ProjectArea

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


class Dialog(QtWidgets.QDialog):
    '''
    Dialog
    '''
    ui_file = ''
    def __init__(self, ui_file: str = None, modal: bool = True,
                 parent: QtWidgets.QWidget = None, title: str = None):
        '''
        Parameters
        ----------
        ui_file : str, optional
            path to QT-Designer xml file to load UI of dialog from,
            if only filename is given, the file is looked for in the standard
            folder (UI_PATH), defaults to not using ui file
        modal : bool, optional
            set dialog to modal if True, not modal if False, defaults to modal
        parent: QWidget, optional
            parent widget, defaults to None
        title: str, optional
            replaces title of dialog if given, defaults to preset title
        '''

        super().__init__(parent=parent)
        ui_file = ui_file or self.ui_file
        if ui_file:
            # look for file ui folder if not found
            ui_file = ui_file if os.path.exists(ui_file) \
                else os.path.join(settings.UI_PATH, ui_file)
            uic.loadUi(ui_file, self)
        if title:
            self.setWindowTitle(title)
        self.setModal(modal)
        self.setupUi()

    def setupUi(self):
        '''
        override this to set up the user interface
        '''
        pass

    def show(self):
        '''
        override, show the dialog
        '''
        return self.exec_()


class InfoDialog(QtWidgets.QDialog, INFO_FORM_CLASS):
    """
    Info Dialog
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent = parent
        self.setupUi(self)
        self.close_button.clicked.connect(self.close)
        wd = os.path.dirname(os.path.realpath(__file__))
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
    def __init__(self, placeholder='', **kwargs):
        self.placeholder = placeholder
        super().__init__(**kwargs)

    def setupUi(self):
        '''
        set up the user interface
        '''
        self.setMinimumWidth(500)
        self.setWindowTitle('Neues Projekt erstellen')

        project_manager = ProjectManager()
        self.project_names = [p.name for p in project_manager.projects]

        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel('Name des Projekts')
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setText(self.placeholder)
        self.name_edit.textChanged.connect(self.validate)
        layout.addWidget(label)
        layout.addWidget(self.name_edit)

        self.status_label = QtWidgets.QLabel()
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
            status_text = ('Der Projektname darf keines der folgenden Zeichen '
                           'enthalten: \/:*?"\'<>|')
            error = True
        elif name in self.project_names:
            status_text = (
                f'Ein Projekt mit dem Namen {name} existiert bereits!\n'
                'Projektnamen müssen einzigartig sein.')
            error = True

        self.status_label.setText(status_text)

        self.ok_button.setEnabled(not error and len(name) > 0)

    def show(self):
        '''
        show dialog and return selections made by user
        '''
        confirmed = self.exec_()
        if confirmed:
            return confirmed, self.name_edit.text()
        return False, None


class ImportLayerDialog(Dialog):

    def __init__(self, table, title='Layer importieren',
                 filter_class=QgsMapLayerProxyModel.VectorLayer,
                 help_text='',
                 optional_fields=[], **kwargs):
        self.table = table
        self.title = title
        self.filter_class = filter_class
        self.optional_fields = optional_fields
        self.help_text = help_text
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
        layout.addWidget(label)
        layout.addWidget(self.input_layer_combo)

        if self.optional_fields:
            spacer = QtWidgets.QSpacerItem(
                0, 20, QtWidgets.QSizePolicy.Fixed)
            layout.addItem(spacer)

        self._optional_inputs = []
        for field_name, field_label in self.optional_fields:
            label = QtWidgets.QLabel(f'{field_label} (optional)')
            o_input = QtWidgets.QComboBox()
            self._optional_inputs.append(o_input)
            layout.addWidget(label)
            layout.addWidget(o_input)

        if self.help_text:
            spacer = QtWidgets.QSpacerItem(
                0, 10, QtWidgets.QSizePolicy.Fixed)
            label = QtWidgets.QLabel(self.help_text)
            label.setWordWrap(True)
            layout.addItem(spacer)
            layout.addWidget(label)


        spacer = QSpacerItem(
            0, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout.addItem(spacer)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self)
        self.ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


    def accept(self):
        layer = self.input_layer_combo.currentLayer()
        # ToDo: transform
        if not layer or not layer.isValid():
            return
        self.table.delete_rows()
        for feature in layer.getFeatures():
            self.table.add(geom=feature.geometry())


class ProgressDialog(QtWidgets.QDialog, PROGRESS_FORM_CLASS):
    """
    Dialog showing progress in textfield and bar after starting a certain task with run()
    """
    def __init__(self, parent=None, auto_close=False):
        super().__init__(parent=parent)
        self.parent = parent
        self.setupUi(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.progress_bar.setStyleSheet(DEFAULT_STYLE)
        self.progress_bar.setValue(0)
        self.cancelButton.clicked.connect(self.close)
        self.startButton.clicked.connect(self.run)
        self.auto_close = auto_close

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_timer)


    def running(self):
        self.startButton.setEnabled(False)
        self.cancelButton.setText('Stoppen')
        self.cancelButton.clicked.disconnect(self.close)

    def stopped(self):
        self.timer.stop()
        self.startButton.setEnabled(True)
        self.cancelButton.setText('Beenden')
        self.cancelButton.clicked.connect(self.close)
        if self.auto_close:
            self.close()

    def show_status(self, text, progress=None):
        #if hasattr(text, 'toLocal8Bit'):
            #text = str(text.toLocal8Bit())
        #else:
            #text = _fromUtf8(text)
        self.log_edit.insertHtml(text + '<br>')
        self.log_edit.moveCursor(QtGui.QTextCursor.End)
        if progress:
            if isinstance(progress, QtCore.QVariant):
                progress = progress.toInt()[0]
            self.progress_bar.setValue(progress)

    # task needs to be overridden
    def run(self):
        self.start_time = datetime.datetime.now()
        self.timer.start(1000)

    def update_timer(self):
        delta = datetime.datetime.now() - self.start_time
        h, remainder = divmod(delta.seconds, 3600)
        m, s = divmod(remainder, 60)
        timer_text = '{:02d}:{:02d}:{:02d}'.format(h, m, s)
        self.elapsed_time_label.setText(timer_text)


class ExecOTPDialog(ProgressDialog):
    """
    ProgressDialog extented by an executable external process

    Parameters
    ----------
    n_iterations: number of iterations (like multiple time windows)
    n_points: number of points to calculate in one iteration
    points_per_tick: how many points are calculated before showing progress
    """
    def __init__(self, command, parent=None, auto_close=False, auto_start=False, n_iterations=1, n_points=0, points_per_tick=50):
        super().__init__(parent=parent, auto_close=auto_close)

        # QProcess object for external app
        self.process = QtCore.QProcess(self)
        self.auto_close = auto_close
        self.command = command
        self.start_time = 0

        self.success = False

        # aux. variable to determine if process was killed, because exit code of killed process can't be distinguished from normal exit in linux
        self.killed = False

        self.ticks = 0.
        self.iterations = 0

        # Just to prevent accidentally running multiple times
        # Disable the button when process starts, and enable it when it finishes
        self.process.started.connect(self.running)
        self.process.finished.connect(self.finished)

        # how often will the stdout-indicator written before reaching 100%
        n_ticks = float(n_points) / points_per_tick
        n_ticks *= n_iterations
        tick_indicator = 'Processing:'
        iteration_finished_indicator = 'A total of'

        # leave some space for post processing
        max_progress = 98.

        def show_progress():
            out = self.process.readAllStandardOutput()
            out = str(out.data(), encoding='utf-8')
            err = self.process.readAllStandardError()
            err = str(err.data(), encoding='utf-8')
            if len(out):
                self.show_status(out)
                if tick_indicator in out and n_ticks:
                    self.ticks += max_progress / n_ticks
                    self.progress_bar.setValue(min(max_progress, int(self.ticks)))
                elif iteration_finished_indicator in out:
                    self.iterations += 1
                    self.progress_bar.setValue(self.iterations * max_progress / n_iterations)

                '''  this approach shows progress more accurately, but may cause extreme lags -> deactivated (alternative: thread this)
                if out.startswith(progress_indicator):
                    # sometimes the stdout comes in too fast, you have to split it (don't split other than progress messages, warnings tend to be very long with multiple breaks, bad performance)
                    for out_split in out.split("\n"):
                        if (len(out_split) == 0):
                            continue
                        self.show_status(out_split)
                        if(total_ticks and out_split.startswith(progress_indicator)):
                            self.ticks += 100. / total_ticks
                            self.progress_bar.setValue(min(100, int(self.ticks)))
                else:
                    self.show_status(out)
                '''
            if len(err): self.show_status(err)

        self.process.readyReadStandardOutput.connect(show_progress)
        self.process.readyReadStandardError.connect(show_progress)
        def error(sth):
            self.kill()
        self.process.errorOccurred.connect(error)
        if auto_start:
            self.startButton.clicked.emit(True)

    def running(self):
        self.cancelButton.clicked.connect(self.kill)
        super().running()

    def stopped(self):
        self.cancelButton.clicked.disconnect(self.kill)
        super().stopped()

    def finished(self):
        self.startButton.setText('Neustart')
        self.timer.stop()
        if self.process.exitCode() == QtCore.QProcess.NormalExit and not self.killed:
            self.progress_bar.setValue(100)
            self.progress_bar.setStyleSheet(FINISHED_STYLE)
            self.success = True
        else:
            self.progress_bar.setStyleSheet(ABORTED_STYLE)
            self.success = False
        self.stopped()

    def kill(self):
        self.timer.stop()
        self.killed = True
        self.process.kill()
        self.log_edit.insertHtml('<b> Vorgang abgebrochen </b> <br>')
        self.log_edit.moveCursor(QtGui.QTextCursor.End)
        self.success = False

    def run(self):
        self.killed = False
        self.ticks = 0
        self.progress_bar.setStyleSheet(DEFAULT_STYLE)
        self.progress_bar.setValue(0)
        self.show_status('<br>Starte Script: <i>' + self.command + '</i><br>')
        self.process.start(self.command)
        self.start_time = datetime.datetime.now()
        self.timer.start(1000)


class ExecCreateRouterDialog(ProgressDialog):
    def __init__(self, source_folder, target_folder,
                 java_executable, otp_jar, memory=2,
                 parent=None):
        super().__init__(parent=parent)
        self.target_folder = target_folder
        self.source_folder = source_folder
        self.command = '''
        "{javacmd}" -Xmx{ram_GB}G -jar "{otp_jar}"
        --build "{folder}"
        '''.format(javacmd=java_executable,
                   ram_GB=memory,
                   otp_jar=otp_jar,
                   folder=source_folder)
        self.process = QtCore.QProcess(self)
        self.process.started.connect(self.running)
        self.process.finished.connect(self.finished)
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
        self.startButton.clicked.emit(True)  #auto start

    def run(self):
        self.killed = False
        self.progress_bar.setStyleSheet(DEFAULT_STYLE)
        self.progress_bar.setValue(0)
        self.process.start(self.command)

    def running(self):
        self.cancelButton.clicked.connect(self.kill)
        super().running()

    def stopped(self):
        self.cancelButton.clicked.disconnect(self.kill)
        super().stopped()

    def finished(self):
        self.startButton.setText('Neustart')
        self.timer.stop()
        if self.process.exitCode() == QtCore.QProcess.NormalExit and not self.killed:
            self.show_status("graph created...")
            self.progress_bar.setValue(100)
            self.progress_bar.setStyleSheet(FINISHED_STYLE)
            graph_file = os.path.join(self.source_folder, "Graph.obj")
            dst_file = os.path.join(self.target_folder, "Graph.obj")
            if not os.path.exists(self.target_folder):
                self.show_status("creating target folder in router directory...")
                os.makedirs(self.target_folder)
            if graph_file != dst_file:
                if os.path.exists(dst_file):
                    self.show_status("overwriting old graph...")
                    os.remove(dst_file)
                self.show_status("moving graph to target location...")
                move(graph_file, dst_file)
            self.show_status("done")
        else:
            self.progress_bar.setStyleSheet(ABORTED_STYLE)
        self.stopped()

    def kill(self):
        self.timer.stop()
        self.killed = True
        self.process.kill()
        self.log_edit.insertHtml('<b> Vorgang abgebrochen </b> <br>')
        self.log_edit.moveCursor(QtGui.QTextCursor.End)


class RouterDialog(QtWidgets.QDialog, ROUTER_FORM_CLASS):
    def __init__(self, graph_path, java_executable, otp_jar, memory=2, parent=None):
        super().__init__(parent=parent)
        self.graph_path = graph_path
        self.java_executable = java_executable
        self.otp_jar = otp_jar
        self.memory = memory
        self.setupUi(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.close_button.clicked.connect(self.close)
        self.source_browse_button.clicked.connect(self.browse_source_path)

        # name has to start with letter, no spaces or special characters
        regex = QtCore.QRegExp("[A-Za-z][A-Za-z0-9_]*")
        validator = QtGui.QRegExpValidator(regex, self)
        self.router_name_edit.setValidator(validator)

        self.create_button.clicked.connect(self.run)

    def browse_source_path(self):
        path = str(
            QtWidgets.QFileDialog.getExistingDirectory(
                self,
                u'Verzeichnis mit Eingangsdaten wählen',
                self.source_edit.text()
            )
        )
        if not path:
            return
        self.source_edit.setText(path)

    def run(self):
        name = self.router_name_edit.text()
        path = self.source_edit.text()
        if not name:
            return
        target_folder = os.path.join(self.graph_path, name)
        diag = ExecCreateRouterDialog(path, target_folder,
                                      self.java_executable, self.otp_jar,
                                      memory=self.memory, parent=self)
        diag.exec_()


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
        self.cpu_edit.setValue(settings.system['n_threads'])
        self.memory_edit.setValue(settings.system['reserved'])

    def save(self):
        settings.project_path = self.project_path_edit.text()
        settings.graph_path = self.graph_path_edit.text()

        settings.system['java'] = self.java_edit.text()
        settings.system['jython_jar_file'] = self.jython_edit.text()
        settings.system['otp_jar_file'] = self.otp_jar_edit.text()
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
