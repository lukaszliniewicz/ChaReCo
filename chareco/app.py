import sys
from PyQt6.QtWidgets import QApplication
from chareco.gui import App

def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("ChaReCo")
    app.setApplicationName("ChaReCo")
    window = App()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

#
