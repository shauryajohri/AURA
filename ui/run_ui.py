import sys
from aura_ui.app_controller import AuraAppController
from PySide6.QtWidgets import QApplication
from aura_ui.app_controller import AuraAppController

app = QApplication(sys.argv)
controller = AuraAppController(app)
sys.exit(app.exec())