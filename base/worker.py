from qgis.PyQt.QtCore import pyqtSignal, QObject, QThread


class Worker(QThread):
    '''
    abstract worker

    Attributes
    ----------
    finished : pyqtSignal
        emitted when all tasks are finished, success True/False
    error : pyqtSignal
        emitted on error while working, error message text
    message : pyqtSignal
        emitted when a message is send, message text
    progress : pyqtSignal
        emitted on progress, progress in percent
    '''

    # available signals to be used in the concrete worker
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    warning = pyqtSignal(str)
    message = pyqtSignal(str)
    progress = pyqtSignal(float)

    def __init__(self, parent: QObject = None):
        '''
        Parameters
        ----------
        parent : QObject, optional
            parent object of thread, defaults to no parent (global)
        '''
        #parent = parent or utils.iface.mainWindow()
        super().__init__(parent=parent)

    def run(self, on_success: object = None):
        '''
        runs code defined in self.work
        emits self.finished on success and self.error on exception
        override this function if you make asynchronous calls

        Parameters
        ----------
        on_success : function
            function to execute on success
        '''
        try:
            result = self.work()
            self.finished.emit(result)
            if on_success:
                on_success()
        except Exception as e:
            self.error.emit(str(e))

    def work(self) -> object:
        '''
        override
        code to be executed when running worker

        Returns
        -------
        result : object
            result of work, emitted when code was run succesfully
        '''
        raise NotImplementedError

    def log(self, message, warning=False):
        '''
        emits message

        Parameters
        ----------
        message : str
        '''
        if warning:
            self.warning.emit(str(message))
        else:
            self.message.emit(str(message))

    def set_progress(self, progress: int):
        '''
        emits progress

        Parameters
        ----------
        progress : int
            progress in percent, value in range [0, 100]
        '''
        self.progress.emit(progress)

