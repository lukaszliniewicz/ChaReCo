#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    from PyQt6.QtWidgets import QApplication
    from chareco.gui import App
    
    def main():
        app = QApplication(sys.argv)
        window = App()
        window.show()
        sys.exit(app.exec())
    
    main()
