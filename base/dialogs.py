from qgis.PyQt import uic, QtWidgets, QtGui
from qgis.PyQt.QtCore import QObject, QTimer, QVariant, Qt
from typing import Union
import os
import datetime

from .project import settings
from .worker import Worker


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


class ProgressDialog(Dialog):
    '''
    Dialog showing progress in textfield and a progress bar after starting a
    certain task with run(). Contains a log section and a timer

    Attributes
    ----------
    success : bool
        indicates if the task was run successfully without errors
    error : bool
        indicates if an error occured while running the task
    '''
    ui_file = 'progress.ui'

    def __init__(self, worker: Worker, parent: QObject = None,
                 auto_close: bool = False, auto_run: bool = True,
                 hide_auto_close: bool = False, title=None, start_elapsed=0,
                 on_success: object = None, on_close: object = None,
                 logs=[]):
        '''
        Parameters
        ----------
        worker : Worker
            Worker object holding the task to do
        parent : QObject, optional
            parent ui element of the dialog, defaults to no parent
        auto_close : bool, optional
            close dialog automatically after task is done, defaults to automatic
            close
        auto_run : bool, optional
            start task automatically when showing the dialog, otherwise the user
            has to start it by pressing the start-button, defaults to automatic
            start
        on_success : object, optional
            function to call on successful run of task, function has to expect
            the result of the task as an argument, defaults to no callback on
            success
        on_close : object, optional
            function to call when closing the dialog, defaults to no callback on
            closing
        '''
        # parent = parent or iface.mainWindow()
        super().__init__(self.ui_file, title=title,
                         modal=True, parent=parent)
        self.parent = parent
        self.logs = logs
        self.elapsed_time = start_elapsed
        self.setupUi()
        self.result = None
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.progress_bar.setValue(0)
        self.stop_button.setVisible(False)
        self.close_button.setVisible(False)
        self.auto_close_check.setChecked(auto_close)
        self.auto_close_check.setVisible(not hide_auto_close)
        self.auto_run = auto_run
        # ToDo: use signals instead of callbacks
        self.on_success = on_success
        self.on_close = on_close
        self.success = False
        self.error = False

        self.worker = worker
        if self.worker:
            self.worker.finished.connect(self._success)
            self.worker.error.connect(self.on_error)
            self.worker.warning.connect(self.on_warning)
            self.worker.message.connect(self.show_status)
            self.worker.progress.connect(self.progress)

        self.start_button.clicked.connect(self.run)
        self.stop_button.clicked.connect(self.stop)
        self.close_button.clicked.connect(self.close)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_timer)

        for log in logs:
            self.log_edit.appendHtml(log)

    def show(self):
        '''
        show the dialog
        '''
        QtWidgets.QDialog.show(self)
        if self.auto_run:
            self.run()

    def _success(self, result: object = None):
        '''
        handle successful run
        '''
        self.progress(100)
        self.show_status('<br><b>fertig</b>')
        self.result = result
        if not self.error:
            self.success = True
            if self.on_success:
                self.on_success(result)
        self._finished()

    def _finished(self):
        '''
        handle finished run
        '''
        #self.worker.deleteLater()
        self.timer.stop()
        self.close_button.setVisible(True)
        self.close_button.setEnabled(True)
        self.stop_button.setVisible(False)
        if self.auto_close_check.isChecked() and not self.error:
            self.close()

    def close(self):
        '''
        close the dialog
        '''
        if self.worker and self.worker.isRunning:
            self.worker.terminate()
        super().close()
        if self.on_close:
            self.on_close()

    def on_error(self, message: str):
        '''
        call this if error occurs while running task

        Parameters
        ----------
        message : str
            error message to show
        '''
        self.show_status( f'<span style="color:red;">Fehler: {message}</span>')
        self.progress_bar.setStyleSheet(
            'QProgressBar::chunk { background-color: red; }')
        self.error = True
        self._finished()

    def on_warning(self, message: str):
        '''
        write warning message into the log section

        Parameters
        ----------
        text : str
            message to show
        '''
        self.show_status( f'<span style="color:orange;">Warnung: {message}</span>')

    def show_status(self, text: str):
        '''
        write message into the log section

        Parameters
        ----------
        text : str
            message to show
        '''
        self.log_edit.appendHtml(text)
        self.logs.append(text)
        #self.log_edit.moveCursor(QTextCursor.Down)
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum());

    def progress(self, progress: Union[int, QVariant]):
        '''
        set progress of task

        Parameters
        ----------
        progress : int or QVariant
            progress in percent [0..100]
        '''
        if isinstance(progress, QVariant):
            progress = progress.toInt()[0]
        self.progress_bar.setValue(int(progress))

    def start_timer(self):
        '''
        start the timer
        '''
        self.start_time = (datetime.datetime.now() -
                           datetime.timedelta(seconds=self.elapsed_time))
        self.timer.start(1000)

    def run(self):
        '''
        run the task
        '''
        self.error = False
        self.start_timer()
        self.stop_button.setVisible(True)
        self.start_button.setVisible(False)
        self.close_button.setVisible(True)
        self.close_button.setEnabled(False)
        if self.worker:
            self.worker.start()

    def stop(self):
        '''
        cancel the task
        '''
        self.timer.stop()
        if self.worker:
            self.worker.terminate()
        text = '<b> Vorgang abgebrochen </b> <br>'
        self.log_edit.appendHtml(text)
        self.logs.append(text)
        self.log_edit.moveCursor(QtGui.QTextCursor.End)
        self._finished()

    def _update_timer(self):
        '''
        update the timer
        '''
        delta = datetime.datetime.now() - self.start_time
        self.elapsed_time = delta.seconds
        h, remainder = divmod(self.elapsed_time, 3600)
        m, s = divmod(remainder, 60)
        timer_text = '{:02d}:{:02d}:{:02d}'.format(h, m, s)
        self.elapsed_time_label.setText(timer_text)

