import os
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction
from gruenflaechenotp.tool.main import OTPMainWindow
from gruenflaechenotp.base.project import settings

# Initialize Qt resources from file resources.py
#from gruenflaechenotp import resources

# how many results are written while running batch script
PRINT_EVERY_N_LINES = 100

XML_FILTER = u'XML-Dateien (*.xml)'
CSV_FILTER = u'Comma-seperated values (*.csv)'
JAR_FILTER = u'Java Archive (*.jar)'
ALL_FILE_FILTER = u'Java Executable (java.*)'

PLUGIN_TITLE = 'Grünflächenbewertung'


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

        # Declare instance attributes
        self.menu = PLUGIN_TITLE
        self.toolbar = self.iface.addToolBar(PLUGIN_TITLE)
        self.toolbar.setObjectName(PLUGIN_TITLE)
        self.main_window = None

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = os.path.join(os.path.join(
            settings.BASE_PATH, 'ui', 'icon.png'))
        icon = QIcon(icon_path)
        self.action = QAction(icon, PLUGIN_TITLE,
                              self.iface.mainWindow())
        self.action.triggered.connect(lambda: self.run())
        self.toolbar.addAction(self.action)
        self.iface.addPluginToMenu(PLUGIN_TITLE, self.action)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        self.iface.removePluginMenu(PLUGIN_TITLE, self.action)
        self.iface.removeToolBarIcon(self.action)
        # remove the toolbar
        del self.toolbar
        if self.main_window:
            self.main_window.close()

    def run(self):
        '''
        open the plugin UI
        '''
        # initialize and show main window
        if not self.main_window:
            self.main_window = OTPMainWindow()

        self.main_window.show()
        # bring window on top
        self.main_window.ui.activateWindow()


