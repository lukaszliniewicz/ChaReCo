import os
import logging
import re
from collections import deque
from threading import Event
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

import tiktoken
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, QLineEdit,
    QCheckBox, QVBoxLayout, QHBoxLayout, QFileDialog, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QSplitter, QProgressDialog, QRadioButton,
    QButtonGroup, QFrame, QToolButton, QProgressBar, QScrollArea, QMenu,
    QPlainTextEdit
)
from PyQt6.QtCore import (
    Qt, QThread, QSize, QTimer, QThreadPool, QSettings
)
from PyQt6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QIcon, QFont, QBrush, QTextDocument, QAction
)

from chareco import __version__
from chareco.core.analysis import AnalysisThread
from chareco.core.models import AnalysisOptions, AnalysisResult
from chareco.core.search import SearchWorker
from chareco.core.utils import convert_notebook_to_markdown, read_text_file

class App(QMainWindow):
    def __init__(self):
        super().__init__()

        # Main window configuration
        self.setWindowTitle("ChaReCo")
        self.setAcceptDrops(True)
        
        # Create a size that works for most screens
        self.resize(1400, 900)
        
        # Central widget and main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Create scrollable left panel for controls
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(10, 10, 10, 10)
        self.left_layout.setSpacing(5)  # Reduce spacing for shorter screens
        
        self.scroll_area.setWidget(self.left_panel)

        # Create right panel (will contain splitter for tree and text)
        self.right_panel = QWidget()
        self.right_layout = QHBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        # Add panels to main layout
        self.main_layout.addWidget(self.scroll_area, 0)
        self.main_layout.addWidget(self.right_panel, 1)

        # Setup the left panel contents
        self.setup_left_panel()

        # Setup the right panel contents
        self.setup_right_panel()

        # Initialize state variables
        self.file_positions = {}
        self.file_contents = {}
        self.file_token_counts = {}
        self.current_result = None
        self.current_options = None
        self.pending_options = None
        self.folder_structure = ""
        self.progress_dialog = None
        self.analysis_thread = None
        self.local_folder_path = None
        self.search_results = []
        self.search_errors = []
        self.current_search_index = -1
        self.is_searching = False
        self.search_progress_bar = None
        self.search_workers = []
        self.search_errors = []
        self.search_job_id = 0
        self.search_cancel_event = None
        self.search_pending_workers = 0
        self.search_completed_files = 0
        self.search_total_files = 0
        self.thread_pool = QThreadPool(self)
        self.paths_to_restore = None
        self.path_to_item_map = {}
        self.repo_history = []
        self.local_history = []
        self.settings = QSettings("ChaReCo", "ChaReCo")
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("splitter_state")
        if splitter_state is not None:
            self.splitter.restoreState(splitter_state)

        # A local, bounded pool avoids starving the GUI or unrelated Qt users.
        self.max_threads = min(8, max(1, QThread.idealThreadCount()))
        self.thread_pool.setMaxThreadCount(self.max_threads)

        try:
            self._token_encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._token_encoding = None
        self._counts_timer = QTimer(self)
        self._counts_timer.setSingleShot(True)
        self._counts_timer.timeout.connect(self._recalculate_counts)
        self._selected_counts_timer = QTimer(self)
        self._selected_counts_timer.setSingleShot(True)
        self._selected_counts_timer.timeout.connect(self._recalculate_selected_counts)

        # Setup dark theme
        self.setup_dark_theme()
        
        self.load_history()
        
        # Default settings
        self.only_show_structure = False  # Default is to show content

    def setup_dark_theme(self):
        # Set dark theme using Qt stylesheets
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: Arial, sans-serif;
            }
            QPushButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 0px;
                padding: 8px 16px;
                font-size: 14px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
            QPushButton:pressed {
                background-color: #7D3C98;
            }
            QToolButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 0px;
                padding: 5px;
                min-height: 24px;
                min-width: 24px;
            }
            QToolButton:hover {
                background-color: #9B59B6;
            }
            QToolButton:pressed {
                background-color: #7D3C98;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 0px;
                padding: 6px;
                color: white;
                min-height: 25px;
            }
            QTextEdit, QPlainTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 0px;
                color: white;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                padding: 5px;
                selection-background-color: #1f538d;
            }
            QTreeWidget {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 0px;
                color: white;
                selection-background-color: #1f538d;
                alternate-background-color: #333333;
                outline: none;
            }
            QTreeWidget::item {
                min-height: 25px;
                border-bottom: 1px solid #444444;
            }
            QTreeWidget::item:selected {
                background-color: #1f538d;
            }
            QTreeWidget::indicator {
                width: 16px;
                height: 16px;
            }
            QTreeWidget::indicator:checked {
                image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>');
                background-color: #8E44AD;
                border: 1px solid #8E44AD;
                border-radius: 0px;
            }
            QTreeWidget::indicator:unchecked {
                background-color: #444444;
                border: 1px solid #555555;
                border-radius: 0px;
            }
            QLabel {
                font-size: 14px;
                background-color: transparent;
            }
            QCheckBox, QRadioButton {
                spacing: 8px;
                min-height: 25px;
                background-color: transparent;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #555555;
                border-radius: 0px;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background-color: #8E44AD;
                border: 2px solid #8E44AD;
            }
            QCheckBox::indicator:checked {
                image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>');
            }
            QRadioButton::indicator {
                border-radius: 9px;
            }
            QRadioButton::indicator:checked {
                image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="white"></svg>');
            }
            QCheckBox::indicator:unchecked:hover, QRadioButton::indicator:unchecked:hover {
                border-color: #9B59B6;
            }
            QSplitter::handle {
                background-color: #2b2b2b;
                width: 2px;
            }
            QScrollBar:vertical {
                border: none;
                background: #2b2b2b;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #8E44AD;
                border-radius: 0px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                border: none;
                background: #2b2b2b;
                height: 8px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #8E44AD;
                border-radius: 0px;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QProgressDialog {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                border-radius: 0px;
            }
            QProgressDialog QProgressBar {
                border: 1px solid #555555;
                border-radius: 0px;
                background-color: #2b2b2b;
                text-align: center;
                color: white;
            }
            QProgressDialog QProgressBar::chunk {
                background-color: #8E44AD;
                width: 20px;
            }
            QProgressDialog QPushButton {
                min-width: 80px;
                min-height: 30px;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                border-radius: 0px;
                background-color: #2b2b2b;
            }
            QTabWidget::tab-bar {
                alignment: left;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                border-radius: 0px;
                padding: 8px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #8E44AD;
                border: 1px solid #8E44AD;
            }
            QTabBar::tab:hover:!selected {
                background-color: #444444;
            }
            QFrame[frameShape="4"] { /* HLine */
                background-color: #555555;
                max-height: 1px;
                border: none;
            }
            .ButtonGroup {
                background-color: transparent;
                border-radius: 0px;
                padding: 2px;
            }
            QToolBar {
                background-color: #2b2b2b;
                border: none;
            }
            QStatusBar {
                background-color: #2b2b2b;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 0px;
                background-color: #2b2b2b;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #8E44AD;
            }
            QScrollArea {
                border: none;
                background-color: #2b2b2b;
            }
        """)

    def setup_left_panel(self):
        # Application title
        title_label = QLabel("ChaReCo - Chat Repo Context")
        title_label.setStyleSheet("font-size: 16px; font-weight: normal; color: #8E44AD; padding: 5px 0;")
        self.left_layout.addWidget(title_label)
        self.left_layout.addSpacing(5)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        self.left_layout.addWidget(separator)
        self.left_layout.addSpacing(5)

        # Source selection section
        source_label = QLabel("Source:")
        source_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.left_layout.addWidget(source_label)

        # Radio buttons for source selection
        self.source_group = QButtonGroup(self)

        self.repo_radio = QRadioButton("Remote Repository")
        self.repo_radio.setChecked(True)
        self.repo_radio.toggled.connect(self.toggle_source_input)
        self.left_layout.addWidget(self.repo_radio)
        self.source_group.addButton(self.repo_radio)

        self.local_radio = QRadioButton("Local Folder")
        self.local_radio.toggled.connect(self.toggle_source_input)
        self.left_layout.addWidget(self.local_radio)
        self.source_group.addButton(self.local_radio)
        self.left_layout.addSpacing(5)

        # Source input container (will contain either repo URL or local folder path)
        self.source_container = QWidget()
        self.source_layout = QVBoxLayout(self.source_container)
        self.source_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.addWidget(self.source_container)

        # Repository address (default view)
        self.repo_input_widget = QWidget()
        self.repo_input_layout = QVBoxLayout(self.repo_input_widget)
        self.repo_input_layout.setContentsMargins(0, 0, 0, 0)
        self.repo_label = QLabel("Repository URL:")
        self.repo_input_layout.addWidget(self.repo_label)

        self.repo_entry = QLineEdit()
        self.repo_entry.setPlaceholderText("Enter GitHub repo URL")
        self.repo_input_layout.addWidget(self.repo_entry)

        self.branch_entry = QLineEdit()
        self.branch_entry.setPlaceholderText("Branch or tag (optional; default branch if empty)")
        self.repo_input_layout.addWidget(self.branch_entry)

        self.repo_history_button = QPushButton("Load from History")
        self.repo_history_button.setToolTip("Select a repository from history")
        self.repo_history_button.clicked.connect(self.show_repo_history_menu)
        self.repo_input_layout.addWidget(self.repo_history_button)

        # Add checkbox for PAT
        self.use_pat_checkbox = QCheckBox("Use a GitHub Personal Access Token")
        self.use_pat_checkbox.toggled.connect(self.toggle_pat_visibility)

        # PAT container
        self.pat_container = QWidget()
        self.pat_container_layout = QVBoxLayout(self.pat_container)
        self.pat_container_layout.setContentsMargins(0, 0, 0, 0)
        self.pat_container.hide()  # Initially hidden

        self.pat_label = QLabel("Personal Access Token (never stored):")
        self.pat_entry = QLineEdit()
        self.pat_entry.setPlaceholderText("For private repositories")
        self.pat_entry.setEchoMode(QLineEdit.EchoMode.Password)

        self.pat_container_layout.addWidget(self.pat_label)
        self.pat_container_layout.addWidget(self.pat_entry)

        self.repo_input_layout.addWidget(self.use_pat_checkbox)
        self.repo_input_layout.addWidget(self.pat_container)

        # Local folder selection
        self.local_input_widget = QWidget()
        self.local_input_layout = QVBoxLayout(self.local_input_widget)
        self.local_input_layout.setContentsMargins(0, 0, 0, 0)

        self.local_path_label = QLabel("Local folder path:")
        self.local_input_layout.addWidget(self.local_path_label)

        self.local_path_display = QLineEdit()
        self.local_path_display.setReadOnly(True)
        self.local_path_display.setPlaceholderText("No folder selected")
        self.local_input_layout.addWidget(self.local_path_display)

        self.local_history_button = QPushButton("Load from History")
        self.local_history_button.setToolTip("Select a local folder from history")
        self.local_history_button.clicked.connect(self.show_local_history_menu)
        self.local_input_layout.addWidget(self.local_history_button)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_local_folder)
        self.local_input_layout.addWidget(self.browse_button)

        self.copy_local_folder_checkbox = QCheckBox("Copy local folder to temporary location (safer)")
        self.local_input_layout.addWidget(self.copy_local_folder_checkbox)

        # Add repository input to source container (default view)
        self.source_layout.addWidget(self.repo_input_widget)
        self.local_input_widget.hide()  # Initially hide the local input widget

        self.left_layout.addSpacing(5)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        self.left_layout.addWidget(separator2)
        self.left_layout.addSpacing(5)

        # Analysis Options section
        self.options_label = QLabel("Analysis Options:")
        self.options_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.left_layout.addWidget(self.options_label)
        self.left_layout.addSpacing(5)

        self.only_structure_checkbox = QCheckBox("Only show structure, don't concatenate")
        self.only_structure_checkbox.toggled.connect(self.toggle_structure_only)
        self.left_layout.addWidget(self.only_structure_checkbox)

        self.line_numbers_checkbox = QCheckBox("Add line numbers to copied files")
        self.left_layout.addWidget(self.line_numbers_checkbox)
        self.left_layout.addSpacing(5)

        # Separator
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.HLine)
        self.left_layout.addWidget(separator3)
        self.left_layout.addSpacing(5)

        # Include Rules section
        self.rules_label = QLabel("Include Rules:")
        self.rules_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.left_layout.addWidget(self.rules_label)
        self.left_layout.addSpacing(5)
        
        self.ignore_git_checkbox = QCheckBox("Ignore .git related files")
        self.ignore_git_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_git_checkbox)

        self.ignore_readme_checkbox = QCheckBox("Ignore README files")
        self.left_layout.addWidget(self.ignore_readme_checkbox)

        self.ignore_license_checkbox = QCheckBox("Ignore LICENSE files")
        self.ignore_license_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_license_checkbox)

        self.ignore_pycache_checkbox = QCheckBox("Ignore Python cache (__pycache__, *.pyc)")
        self.ignore_pycache_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_pycache_checkbox)

        self.ignore_node_modules_checkbox = QCheckBox("Ignore node_modules")
        self.ignore_node_modules_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_node_modules_checkbox)

        self.ignore_lock_files_checkbox = QCheckBox("Ignore package lock files (e.g. package-lock.json)")
        self.ignore_lock_files_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_lock_files_checkbox)

        self.ignore_build_checkbox = QCheckBox("Ignore build outputs (build/, dist/)")
        self.ignore_build_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_build_checkbox)

        self.ignore_ide_checkbox = QCheckBox("Ignore IDE metadata (.vscode/, .idea/)")
        self.ignore_ide_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_ide_checkbox)

        self.ignore_log_files_checkbox = QCheckBox("Ignore log files (*.log)")
        self.ignore_log_files_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_log_files_checkbox)

        self.ignore_secret_files_checkbox = QCheckBox("Ignore likely secret files (.env, keys, credentials)")
        self.ignore_secret_files_checkbox.setChecked(True)
        self.left_layout.addWidget(self.ignore_secret_files_checkbox)
        self.left_layout.addSpacing(5)

        # Include file types
        self.include_label = QLabel("Include ONLY extensions:")
        self.left_layout.addWidget(self.include_label)
        self.include_entry = QLineEdit()
        self.include_entry.setPlaceholderText("e.g. .py .js .java")
        self.left_layout.addWidget(self.include_entry)
        self.left_layout.addSpacing(5)

        # Exclude file types
        self.exclude_label = QLabel("Exclude extensions:")
        self.left_layout.addWidget(self.exclude_label)
        self.exclude_entry = QLineEdit()
        self.exclude_entry.setPlaceholderText("e.g. .log .tmp .bak")
        self.left_layout.addWidget(self.exclude_entry)
        self.left_layout.addSpacing(5)

        # Exclude folder patterns
        self.exclude_folders_label = QLabel("Exclude folders/files (glob patterns):")
        self.left_layout.addWidget(self.exclude_folders_label)
        self.exclude_folders_entry = QLineEdit()
        self.exclude_folders_entry.setPlaceholderText("e.g. */temp/*, *.log, build")
        self.left_layout.addWidget(self.exclude_folders_entry)

        self.max_file_size_entry = QLineEdit("1")
        self.max_file_size_entry.setPlaceholderText("Maximum file size in MiB")
        self.left_layout.addWidget(QLabel("Maximum file size (MiB):"))
        self.left_layout.addWidget(self.max_file_size_entry)

        self.max_output_size_entry = QLineEdit("20")
        self.max_output_size_entry.setPlaceholderText("Maximum total output in MiB")
        self.left_layout.addWidget(QLabel("Maximum output size (MiB):"))
        self.left_layout.addWidget(self.max_output_size_entry)

        self.left_layout.addSpacing(10)

        # Action buttons layout
        self.action_buttons_layout = QHBoxLayout()
        
        # Analyze button
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 10px;
                background-color: #8E44AD;
                font-size: 15px;
            }
        """)
        self.analyze_button.clicked.connect(self.analyze_source)
        self.action_buttons_layout.addWidget(self.analyze_button)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 10px;
                background-color: #1f538d;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: #2a75bb;
            }
            QPushButton:pressed {
                background-color: #1a4a75;
            }
        """)
        self.refresh_button.clicked.connect(self.refresh_local_folder)
        self.refresh_button.hide()
        self.action_buttons_layout.addWidget(self.refresh_button)

        self.left_layout.addLayout(self.action_buttons_layout)

        # Add spacer to push everything to the top
        self.left_layout.addStretch()

        # Add a version label at the bottom
        version_label = QLabel(f"v{__version__}")
        version_label.setStyleSheet("color: #777777; font-size: 12px;")
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.left_layout.addWidget(version_label)

    def toggle_structure_only(self, checked):
        """Toggle between showing only structure or including concatenated content."""
        self.only_show_structure = checked

    def toggle_pat_visibility(self, checked):
        self.pat_container.setVisible(checked)

    def toggle_source_input(self):
        # Show or hide the appropriate input widget based on radio button selection
        if self.repo_radio.isChecked():
            self.repo_input_widget.show()
            self.local_input_widget.hide()
            self.source_layout.addWidget(self.repo_input_widget)
            self.only_structure_checkbox.setChecked(False)
            self.only_structure_checkbox.setEnabled(False)
            self.refresh_button.hide()
        else:
            self.repo_input_widget.hide()
            self.local_input_widget.show()
            self.source_layout.addWidget(self.local_input_widget)
            self.only_structure_checkbox.setEnabled(True)
            if self.tree_container.isVisible():
                self.refresh_button.show()
            else:
                self.refresh_button.hide()

    def browse_local_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Analyze",
            os.path.expanduser("~")
        )

        if folder_path:
            self.local_folder_path = folder_path
            # Show only the folder name in the text field for cleaner UI
            folder_name = os.path.basename(folder_path)
            parent_dir = os.path.basename(os.path.dirname(folder_path))
            display_path = f"{parent_dir}/{folder_name}" if parent_dir else folder_name

            # Set tooltip to show full path on hover
            self.local_path_display.setToolTip(folder_path)
            self.local_path_display.setText(display_path)

    def setup_right_panel(self):
        # Create a splitter to divide tree view and text display
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)  # Increase the handle width for better visual separation
        self.right_layout.addWidget(self.splitter)

        # Create a container for the tree and buttons
        self.tree_container = QWidget()
        self.tree_layout = QVBoxLayout(self.tree_container)
        self.tree_layout.setContentsMargins(0, 0, 0, 0)

        # Tree filter input
        self.tree_filter_input = QLineEdit()
        self.tree_filter_input.setPlaceholderText("Filter tree by name...")
        self.tree_filter_input.textChanged.connect(self.filter_tree_widget)
        self.tree_layout.addWidget(self.tree_filter_input)

        # Create tree toolbar with compact buttons
        self.tree_toolbar = QWidget()
        self.tree_toolbar.setProperty("class", "ButtonGroup")
        self.tree_toolbar_layout = QHBoxLayout(self.tree_toolbar)
        self.tree_toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.tree_toolbar_layout.setSpacing(5)

        # Create compact buttons with icons
        self.select_all_button = QToolButton()
        self.select_all_button.setToolTip("Select all files")
        self.select_all_button.setIcon(QIcon.fromTheme("edit-select-all"))
        self.select_all_button.clicked.connect(self.select_all_files)
        self.tree_toolbar_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QToolButton()
        self.deselect_all_button.setToolTip("Deselect all files")
        self.deselect_all_button.setIcon(QIcon.fromTheme("edit-clear"))
        self.deselect_all_button.clicked.connect(self.deselect_all_files)
        self.tree_toolbar_layout.addWidget(self.deselect_all_button)

        self.tree_toolbar_layout.addStretch()

        # Add tree toolbar to main layout
        self.tree_layout.addWidget(self.tree_toolbar)

        # Tree widget for file structure
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setColumnCount(1)
        self.file_tree.itemClicked.connect(self.on_tree_item_clicked)
        self.file_tree.itemChanged.connect(self.on_item_changed)  # Connect to the itemChanged signal
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.file_tree.setMinimumWidth(250)
        self.file_tree.setAlternatingRowColors(True)

        # Add tree to the container
        self.tree_layout.addWidget(self.file_tree)

        # Add tree container to splitter
        self.splitter.addWidget(self.tree_container)
        self.tree_container.hide()  # Initially hidden

        # Create a container for text display and buttons
        self.text_container = QWidget()
        self.text_layout = QVBoxLayout(self.text_container)
        self.text_layout.setContentsMargins(0, 0, 0, 0)

        # Create search bar
        self.setup_search_bar()

        # Create central toolbar for text display
        self.text_actions_frame = QWidget()
        self.text_actions_layout = QVBoxLayout(self.text_actions_frame)
        self.text_actions_layout.setContentsMargins(0, 0, 0, 10)

        # Create a centered toolbar for text actions
        self.text_toolbar = QWidget()
        self.text_toolbar.setProperty("class", "ButtonGroup")
        self.text_toolbar_layout = QHBoxLayout(self.text_toolbar)
        self.text_toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.text_toolbar_layout.setSpacing(5)

        # Show full content button - shows all content even if a folder/file is selected
        self.show_all_button = QToolButton()
        self.show_all_button.setText("Show All")
        self.show_all_button.setToolTip("Show all content")
        self.show_all_button.setIcon(QIcon.fromTheme("view-fullscreen"))
        self.show_all_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.show_all_button.clicked.connect(self.show_all_content)
        self.text_toolbar_layout.addWidget(self.show_all_button)

        # Add "Copy:" label
        copy_label = QLabel("Copy:")
        self.text_toolbar_layout.addWidget(copy_label)

        # Create compact buttons with icons
        self.copy_selected_files_button = QToolButton()
        self.copy_selected_files_button.setText("Selected Files")
        self.copy_selected_files_button.setToolTip("Copy selected files from the tree to clipboard")
        self.copy_selected_files_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_selected_files_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_selected_files_button.clicked.connect(self.copy_selected_files)
        self.text_toolbar_layout.addWidget(self.copy_selected_files_button)

        self.copy_selection_button = QToolButton()
        self.copy_selection_button.setText("Selection")
        self.copy_selection_button.setToolTip("Copy selected text to clipboard")
        self.copy_selection_button.setIcon(QIcon.fromTheme("edit-cut"))
        self.copy_selection_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_selection_button.clicked.connect(self.copy_selection)
        self.text_toolbar_layout.addWidget(self.copy_selection_button)
        
        self.copy_visible_button = QToolButton()
        self.copy_visible_button.setText("Visible")
        self.copy_visible_button.setToolTip("Copy currently visible text to clipboard")
        self.copy_visible_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_visible_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_visible_button.clicked.connect(self.copy_visible_text)
        self.text_toolbar_layout.addWidget(self.copy_visible_button)

        self.copy_all_button = QToolButton()
        self.copy_all_button.setText("All")
        self.copy_all_button.setToolTip("Copy all text to clipboard")
        self.copy_all_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_all_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_all_button.clicked.connect(self.copy_text)
        self.text_toolbar_layout.addWidget(self.copy_all_button)

        self.save_full_button = QToolButton()
        self.save_full_button.setText("Save Full")
        self.save_full_button.setToolTip("Save the complete analysis to a UTF-8 text file")
        self.save_full_button.setIcon(QIcon.fromTheme("document-save"))
        self.save_full_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.save_full_button.clicked.connect(self.save_full_text)
        self.text_toolbar_layout.addWidget(self.save_full_button)

        self.copy_structure_button = QToolButton()
        self.copy_structure_button.setText("Structure")
        self.copy_structure_button.setToolTip("Copy the folder structure to clipboard")
        self.copy_structure_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_structure_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_structure_button.clicked.connect(self.copy_structure)
        self.text_toolbar_layout.addWidget(self.copy_structure_button)

        # Center the toolbar in the frame
        self.text_actions_layout.addWidget(self.text_toolbar, 0, Qt.AlignmentFlag.AlignCenter)

        # Add the toolbar to the text layout
        self.text_layout.addWidget(self.text_actions_frame)

        # Create a frame for the counts that will be right-aligned
        self.count_frame = QWidget()
        self.count_layout = QHBoxLayout(self.count_frame)
        self.count_layout.setContentsMargins(0, 0, 0, 5)

        # Add character and token count labels
        self.char_count_label = QLabel("Characters: 0")
        self.count_layout.addWidget(self.char_count_label)

        self.token_count_label = QLabel("Tokens: 0")
        self.count_layout.addWidget(self.token_count_label)

        self.selected_token_count_label = QLabel("Selected Tokens: 0")
        self.count_layout.addWidget(self.selected_token_count_label)

        # Add search result count label
        self.search_result_label = QLabel("")
        self.count_layout.addWidget(self.search_result_label)

        self.count_layout.addStretch()

        # Add count frame to text layout
        self.text_layout.addWidget(self.count_frame, 0, Qt.AlignmentFlag.AlignRight)

        # Add text edit for displaying content
        self.text_display = QPlainTextEdit()
        self.text_display.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_display.textChanged.connect(self.update_counts)
        self.text_display.setTabStopDistance(QFont("Consolas").pointSizeF() * 4)
        self.text_layout.addWidget(self.text_display)

        # Add text container to splitter
        self.splitter.addWidget(self.text_container)

        # Set splitter proportions (25% tree, 75% text)
        self.splitter.setSizes([250, 750])

    def filter_tree_widget(self, text):
        """Filter the tree widget based on the search text."""
        search_text = text.lower()
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._filter_tree_recursive(root.child(i), search_text)

    def _filter_tree_recursive(self, item, search_text):
        """Recursively filter tree items."""
        child_matches = False
        for i in range(item.childCount()):
            if self._filter_tree_recursive(item.child(i), search_text):
                child_matches = True

        self_matches = search_text in item.text(0).lower()
        should_be_visible = self_matches or child_matches
        item.setHidden(not should_be_visible)

        return should_be_visible

    def show_all_content(self):
        """Restore the immutable serialized result, not editable widget state."""
        if self.current_result is None:
            return
        self.text_display.setPlainText(self.current_result.full_text)
        self.update_counts()

    def setup_search_bar(self):
        # Create search container
        self.search_container = QWidget()
        self.search_layout = QVBoxLayout(self.search_container)
        self.search_layout.setContentsMargins(0, 0, 0, 10)
        
        # Create search bar container
        self.search_bar_container = QWidget()
        self.search_bar_layout = QHBoxLayout(self.search_bar_container)
        self.search_bar_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search input field
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in content...")
        self.search_input.returnPressed.connect(self.perform_search)
        self.search_bar_layout.addWidget(self.search_input)
        
        # Search button
        self.search_button = QToolButton()
        self.search_button.setText("Search")
        self.search_button.setIcon(QIcon.fromTheme("edit-find"))
        self.search_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.search_button.clicked.connect(self.perform_search)
        self.search_bar_layout.addWidget(self.search_button)
        
        # Previous result button
        self.prev_result_button = QToolButton()
        self.prev_result_button.setIcon(QIcon.fromTheme("go-up"))
        self.prev_result_button.setToolTip("Previous result")
        self.prev_result_button.clicked.connect(self.navigate_to_previous_result)
        self.search_bar_layout.addWidget(self.prev_result_button)
        
        # Next result button
        self.next_result_button = QToolButton()
        self.next_result_button.setIcon(QIcon.fromTheme("go-down"))
        self.next_result_button.setToolTip("Next result")
        self.next_result_button.clicked.connect(self.navigate_to_next_result)
        self.search_bar_layout.addWidget(self.next_result_button)
        
        # Clear search button
        self.clear_search_button = QToolButton()
        self.clear_search_button.setIcon(QIcon.fromTheme("edit-clear"))
        self.clear_search_button.setToolTip("Clear search")
        self.clear_search_button.clicked.connect(self.clear_search)
        self.search_bar_layout.addWidget(self.clear_search_button)
        
        # Add search bar container to main search layout
        self.search_layout.addWidget(self.search_bar_container)
        
        # Create search options container
        self.search_options_container = QWidget()
        self.search_options_layout = QHBoxLayout(self.search_options_container)
        self.search_options_layout.setContentsMargins(0, 0, 0, 0)
        
        # Case sensitive checkbox
        self.case_sensitive_checkbox = QCheckBox("Case sensitive")
        self.search_options_layout.addWidget(self.case_sensitive_checkbox)
        
        # Whole word checkbox
        self.whole_word_checkbox = QCheckBox("Whole word")
        self.search_options_layout.addWidget(self.whole_word_checkbox)
        
        # Regular expression checkbox
        self.regex_checkbox = QCheckBox("Regular expression")
        self.search_options_layout.addWidget(self.regex_checkbox)
        
        # Add search progress bar (initially hidden)
        self.search_progress_bar = QProgressBar()
        self.search_progress_bar.setFixedHeight(10)
        self.search_progress_bar.setTextVisible(False)
        self.search_progress_bar.hide()
        
        # Add options and progress bar to search layout
        self.search_options_layout.addStretch()
        self.search_layout.addWidget(self.search_options_container)
        self.search_layout.addWidget(self.search_progress_bar)
        
        # Add search container to text layout
        self.text_layout.addWidget(self.search_container)

    def perform_search(self):
        self.cancel_search()
        search_text = self.search_input.text()
        if not search_text:
            return

        use_regex = self.regex_checkbox.isChecked()
        whole_word = self.whole_word_checkbox.isChecked()
        pattern_text = search_text if use_regex else re.escape(search_text)
        if whole_word:
            pattern_text = rf"\b(?:{pattern_text})\b"
        try:
            re.compile(pattern_text)
        except re.error as error:
            self.search_result_label.setText(f"Invalid regular expression: {error}")
            self.update_navigation_buttons()
            return

        search_files = sorted(self.file_contents.items())
        if not search_files:
            self.search_results = []
            self.search_result_label.setText("No loaded file content to search")
            self.update_navigation_buttons()
            return

        self.clear_search_highlights()
        self.search_job_id += 1
        job_id = self.search_job_id
        self.search_cancel_event = Event()
        self.is_searching = True
        self.search_button.setEnabled(False)
        self.search_progress_bar.setRange(0, len(search_files))
        self.search_progress_bar.setValue(0)
        self.search_progress_bar.show()
        self.search_results = []
        self.search_errors = []
        self.current_search_index = -1
        self.search_completed_files = 0
        self.search_total_files = len(search_files)
        self.update_navigation_buttons()

        worker_count = min(self.max_threads, len(search_files))
        chunks = [search_files[index::worker_count] for index in range(worker_count)]
        self.search_pending_workers = len(chunks)
        self.search_workers = []
        for chunk in chunks:
            worker = SearchWorker(
                job_id,
                chunk,
                search_text,
                case_sensitive=self.case_sensitive_checkbox.isChecked(),
                whole_word=whole_word,
                use_regex=use_regex,
                cancel_event=self.search_cancel_event,
            )
            worker.signals.result.connect(self.handle_search_results)
            worker.signals.progress.connect(self.update_search_progress)
            worker.signals.error.connect(self.handle_search_error)
            worker.signals.finished.connect(self.worker_finished)
            self.search_workers.append(worker)
            self.thread_pool.start(worker)

    def cancel_search(self):
        """Invalidate in-flight work; late worker signals are ignored by job id."""
        if self.search_cancel_event is not None:
            self.search_cancel_event.set()
        self.search_cancel_event = None
        self.is_searching = False
        self.search_button.setEnabled(True)
        if self.search_progress_bar is not None:
            self.search_progress_bar.hide()

    def update_search_progress(self, job_id, _current, _total):
        if job_id != self.search_job_id or not self.is_searching:
            return
        self.search_completed_files += 1
        self.search_progress_bar.setValue(self.search_completed_files)

    def finalize_search(self):
        # Hide progress bar
        if hasattr(self, 'search_progress_bar') and self.search_progress_bar is not None:
            self.search_progress_bar.hide()
        
        self.is_searching = False
        self.search_button.setEnabled(True)
        self.search_cancel_event = None
        self.search_workers = []
        self.search_results.sort(key=lambda result: result[0])
        
        # Display final results
        if self.search_errors:
            self.search_result_label.setText(f"Search completed with errors: {self.search_errors[0]}")
        elif self.search_results:
            # Flatten and organize results
            total_matches = sum(len(matches) for _, matches in self.search_results)
            self.search_result_label.setText(f"Found {total_matches} matches in {len(self.search_results)} files")
            
            # Display results in text area
            self.display_search_results()
        else:
            self.search_result_label.setText("No matches found")
            
        # Enable/disable navigation buttons
        self.update_navigation_buttons()

    def handle_search_results(self, job_id, results):
        if job_id != self.search_job_id or not self.is_searching:
            return
        self.search_results.extend(results)
        self.search_result_label.setText(f"Searching… {len(self.search_results)} matching files")

    def handle_search_error(self, job_id, error_message):
        if job_id != self.search_job_id or not self.is_searching:
            return
        self.search_errors.append(error_message)
        self.search_result_label.setText(f"Search error: {error_message}")

    def worker_finished(self, job_id):
        if job_id != self.search_job_id or not self.is_searching:
            return
        self.search_pending_workers -= 1
        if self.search_pending_workers == 0:
            self.finalize_search()


    def display_search_results(self):
        """Display search results in the text area with highlighted occurrences"""
        if not self.search_results:
            return

        display_sections = []
        for file_path, matches in self.search_results:
            display_sections.append(f"--{file_path}--")
            content = self.file_contents.get(file_path, "")
            if not content:
                continue

            lines = content.split('\n')
            highlighted_sections = []
            last_line_displayed = -1
            for match in matches:
                match_start = match.start()
                line_start = content.rfind('\n', 0, match_start) + 1
                line_number = content[:line_start].count('\n')
                start_line = max(0, line_number - 3)
                end_line = min(len(lines), line_number + 4)
                if start_line <= last_line_displayed:
                    start_line = last_line_displayed + 1
                if start_line >= end_line:
                    continue
                if highlighted_sections:
                    highlighted_sections.append("...")
                context_lines = lines[start_line:end_line]
                formatted_lines = [f"{i+start_line+1}: {line}" for i, line in enumerate(context_lines)]
                last_line_displayed = end_line - 1
                highlighted_sections.append('\n'.join(formatted_lines))

            display_sections.append('\n'.join(highlighted_sections))

        self.text_display.setPlainText('\n\n'.join(display_sections))
        cursor = self.text_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_display.setTextCursor(cursor)

        self._highlight_matching_tree_files()
        search_text = self.search_input.text()
        if not self.regex_checkbox.isChecked():
            highlight_format = QTextCharFormat()
            highlight_format.setBackground(QColor("#8E44AD"))
            highlight_format.setForeground(QColor("white"))
            cursor = self.text_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_display.setTextCursor(cursor)
            search_flags = QTextDocument.FindFlag(0)
            if self.case_sensitive_checkbox.isChecked():
                search_flags |= QTextDocument.FindFlag.FindCaseSensitively
            if self.whole_word_checkbox.isChecked():
                search_flags |= QTextDocument.FindFlag.FindWholeWords
            while self.text_display.find(search_text, search_flags):
                cursor = self.text_display.textCursor()
                cursor.mergeCharFormat(highlight_format)

    def _highlight_matching_tree_files(self):
        self._clear_tree_search_highlights()
        highlight = QBrush(QColor("#C792EA"))
        for file_path, _matches in self.search_results:
            item = self.path_to_item_map.get(file_path)
            if item is not None:
                item.setForeground(0, highlight)

    def _clear_tree_search_highlights(self):
        for item in self.path_to_item_map.values():
            item.setForeground(0, QBrush())

    def navigate_to_result(self, index):
        # This function is for jumping between occurrences
        # Not implemented in this version as we're displaying all results together
        pass

    def navigate_to_next_result(self):
        # Jump to next search result file
        if not self.search_results:
            return
            
        # Move to next file
        self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
        file_path, _ = self.search_results[self.current_search_index]
        
        # Find this file in the text
        self.find_and_scroll_to(f"--{file_path}--")
        
        # Update count display
        self.search_result_label.setText(f"File {self.current_search_index + 1} of {len(self.search_results)}")

    def navigate_to_previous_result(self):
        # Jump to previous search result file
        if not self.search_results:
            return
            
        # Move to previous file
        self.current_search_index = (self.current_search_index - 1) % len(self.search_results) 
        file_path, _ = self.search_results[self.current_search_index]
        
        # Find this file in the text
        self.find_and_scroll_to(f"--{file_path}--")
        
        # Update count display
        self.search_result_label.setText(f"File {self.current_search_index + 1} of {len(self.search_results)}")

    def find_and_scroll_to(self, text):
        """Find and scroll to specific text in the display."""
        cursor = self.text_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_display.setTextCursor(cursor)
        
        found = self.text_display.find(text)
        if found:
            self.text_display.ensureCursorVisible()

    def update_navigation_buttons(self):
        has_results = len(self.search_results) > 0
        self.prev_result_button.setEnabled(has_results)
        self.next_result_button.setEnabled(has_results)
        self.clear_search_button.setEnabled(has_results or self.is_searching)

    def clear_search(self):
        self.cancel_search()
        # Clear search input
        self.search_input.clear()
        
        # Clear highlights
        self.clear_search_highlights()
        
        # Reset search results
        self.search_results = []
        self.search_errors = []
        self.current_search_index = -1
        self._clear_tree_search_highlights()
        
        # Update UI
        self.search_result_label.setText("")
        self.update_navigation_buttons()
        
        # Restore full content
        self.show_all_content()

    def clear_search_highlights(self):
        # Remove all highlighting from the text
        cursor = self.text_display.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        
        # Reset format
        format = QTextCharFormat()
        cursor.setCharFormat(format)
        
        # Restore cursor
        cursor.clearSelection()
        self.text_display.setTextCursor(cursor)

    def _get_file_content(self, file_path):
        content = self.file_contents.get(file_path)
        if content is not None:
            return content

        if self.current_options and not self.current_options.concatenate and self.local_folder_path:
            root = os.path.abspath(self.local_folder_path)
            abs_path = os.path.abspath(os.path.join(root, file_path))
            try:
                inside_root = os.path.commonpath([root, abs_path]) == root
            except ValueError:
                inside_root = False
            if not inside_root or os.path.islink(abs_path) or not os.path.isfile(abs_path):
                return None
            if file_path.casefold().endswith('.ipynb'):
                if os.path.getsize(abs_path) > self.current_options.max_file_bytes:
                    return None
                content = convert_notebook_to_markdown(abs_path)
            else:
                content = read_text_file(abs_path, self.current_options.max_file_bytes)

            if content is not None:
                self.file_contents[file_path] = content
            return content
        return None

    def on_tree_item_clicked(self, item, column):
        # Get the full path of the clicked item
        path = self.get_item_path(item)
        
        # Check if this is a file or directory
        if item.childCount() > 0:  # Directory
            # Concatenate all files in this directory
            self.display_folder_contents(path)
        else:  # File
            # Display just this file's content
            self.display_file_content(path)

    def show_tree_context_menu(self, position):
        item = self.file_tree.itemAt(position)
        if item and item.childCount() == 0:  # It's a file
            menu = QMenu(self)
            copy_action = menu.addAction("Copy file content")
            action = menu.exec(self.file_tree.mapToGlobal(position))
            
            if action == copy_action:
                self.copy_file_content_from_tree(item)

    def copy_file_content_from_tree(self, item):
        path = self.get_item_path(item)
        content = self._get_file_content(path)

        if content is not None:
            content = self._apply_line_numbers(content)

            clipboard = QApplication.clipboard()
            clipboard.setText(content)
            self.show_toast_message(f"Content of {PurePosixPath(path).name} copied")
        else:
            self.show_message(f"Content not found for {path}")

    def get_item_path(self, item):
        """Get the full path of a tree item."""
        path = []
        current = item
        while current is not None:
            path.insert(0, current.text(0))
            current = current.parent()
            
        # Remove the root / if it exists
        if path and path[0] == "/":
            path = path[1:]
            
        return "/".join(path) if path else ""

    def display_folder_contents(self, folder_path):
        """Display all descendant files, not only direct children."""
        concatenated_parts = []
        folder = folder_path.strip("/")
        for file_path in sorted(self.file_positions):
            if folder and not file_path.startswith(f"{folder}/"):
                continue
            content = self._get_file_content(file_path)
            if content is not None:
                concatenated_parts.append(f"--{file_path}--\n{content}")

        if concatenated_parts:
            self.text_display.setPlainText("\n\n".join(concatenated_parts))
        else:
            self.text_display.setPlainText("No text files in this folder.")

        self.update_counts()

    def display_file_content(self, file_path):
        """Display a single file's content."""
        content = self._get_file_content(file_path)
        
        self.text_display.clear()
        if content is not None:
            self.text_display.setPlainText(content)
        else:
            self.text_display.setPlainText(f"File content not found for {file_path}")
        self.update_counts()

    def on_item_changed(self, item, column):
        # Ensure we're not triggering recursive updates
        if hasattr(self, '_updating_items') and self._updating_items:
            return

        try:
            self._updating_items = True
            
            # Get the state being propagated
            is_checked = item.checkState(0) == Qt.CheckState.Checked
            
            # Process children non-recursively
            if item.childCount() > 0:
                self.update_children_check_state(item, is_checked)
            
            # Update parents non-recursively
            self.update_parent_check_state(item.parent())
        finally:
            self._updating_items = False
        
        self.update_selected_counts()

    def update_children_check_state(self, parent_item, checked):
        if parent_item is None:
            return
            
        check_state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        
        # Use a queue for breadth-first traversal
        items_to_process = deque([parent_item])
        
        # Disable UI updates during bulk operations
        self.file_tree.setUpdatesEnabled(False)
        
        try:
            while items_to_process:
                current_item = items_to_process.popleft()
                
                # Process all children of the current item
                for i in range(current_item.childCount()):
                    child = current_item.child(i)
                    child.setCheckState(0, check_state)
                    
                    # Only add to queue if it has children
                    if child.childCount() > 0:
                        items_to_process.append(child)
        finally:
            # Always re-enable updates
            self.file_tree.setUpdatesEnabled(True)

    def update_parent_check_state(self, parent_item):
        if parent_item is None:
            return
            
        current = parent_item
        
        # Use loop instead of recursion to update parents
        while current is not None:
            total_children = current.childCount()
            if total_children == 0:
                break

            states = [current.child(i).checkState(0) for i in range(total_children)]
            if all(state == Qt.CheckState.Unchecked for state in states):
                current.setCheckState(0, Qt.CheckState.Unchecked)
            elif all(state == Qt.CheckState.Checked for state in states):
                current.setCheckState(0, Qt.CheckState.Checked)
            else:
                current.setCheckState(0, Qt.CheckState.PartiallyChecked)
            
            # Move up the tree
            current = current.parent()

    def select_all_files(self):
        self._updating_items = True
        # Update root items
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, Qt.CheckState.Checked)
            self.update_children_check_state(item, True)
        self._updating_items = False
        self.update_selected_counts()

    def deselect_all_files(self):
        self._updating_items = True
        # Update root items
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self.update_children_check_state(item, False)
        self._updating_items = False
        self.update_selected_counts()

    def load_history(self):
        """Load history from settings."""
        self.repo_history = self.settings.value("repo_history", [], type=list)
        self.local_history = self.settings.value("local_history", [], type=list)

    def save_history(self):
        """Save history to settings."""
        self.settings.setValue("repo_history", self.repo_history)
        self.settings.setValue("local_history", self.local_history)

    def closeEvent(self, event):
        """Handle window close event."""
        if self.analysis_thread is not None and self.analysis_thread.isRunning():
            self.cancel_analysis()
            self.show_message("Cancellation was requested. Close the window after the analysis stops.")
            event.ignore()
            return
        self.cancel_search()
        self.save_history()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter_state", self.splitter.saveState())
        super().closeEvent(event)

    def add_to_history(self, path, is_local):
        """Add an item to the history, ensuring no duplicates and limiting size."""
        if not path:
            return
            
        history_list = self.local_history if is_local else self.repo_history
        
        if path in history_list:
            history_list.remove(path)
        
        history_list.insert(0, path)
        
        # Limit history to 10 items
        if len(history_list) > 10:
            if is_local:
                self.local_history = history_list[:10]
            else:
                self.repo_history = history_list[:10]

    def show_repo_history_menu(self):
        """Show a dropdown menu for repository history."""
        if not self.repo_history:
            return

        menu = QMenu(self)
        for repo_path in self.repo_history:
            action = QAction(repo_path, self)
            action.triggered.connect(lambda checked, path=repo_path: self.repo_entry.setText(path))
            menu.addAction(action)

        menu.exec(self.repo_history_button.mapToGlobal(self.repo_history_button.rect().bottomLeft()))

    def show_local_history_menu(self):
        """Show a dropdown menu for local folder history."""
        if not self.local_history:
            return

        menu = QMenu(self)
        for full_path in self.local_history:
            folder_name = os.path.basename(full_path)
            parent_dir = os.path.basename(os.path.dirname(full_path))
            display_path = f"{parent_dir}/{folder_name}" if parent_dir else folder_name

            action = QAction(display_path, self)
            action.triggered.connect(lambda checked, path=full_path: self.set_local_folder_path(path))
            menu.addAction(action)

        menu.exec(self.local_history_button.mapToGlobal(self.local_history_button.rect().bottomLeft()))

    def set_local_folder_path(self, full_path):
        """Set the local folder path from a history selection."""
        self.local_folder_path = full_path
        
        folder_name = os.path.basename(full_path)
        parent_dir = os.path.basename(os.path.dirname(full_path))
        display_path = f"{parent_dir}/{folder_name}" if parent_dir else folder_name

        self.local_path_display.setToolTip(full_path)
        self.local_path_display.setText(display_path)

    def refresh_local_folder(self):
        if not self.local_radio.isChecked() or not self.local_folder_path:
            self.show_message("Refresh is only available for an active local folder analysis.")
            return

        self.paths_to_restore = self._get_checked_item_paths()
        self.analyze_source()

    def _get_checked_item_paths(self):
        paths = set()
        root = self.file_tree.invisibleRootItem()
        
        items_to_process = deque()
        for i in range(root.childCount()):
            items_to_process.append(root.child(i))

        while items_to_process:
            item = items_to_process.popleft()
            if item.childCount() == 0 and item.checkState(0) == Qt.CheckState.Checked:
                paths.add(self.get_item_path(item))
            
            for i in range(item.childCount()):
                items_to_process.append(item.child(i))
        
        return paths

    def analyze_source(self):
        if self.analysis_thread is not None and self.analysis_thread.isRunning():
            self.show_message("An analysis is already running.")
            return

        is_local = self.local_radio.isChecked()

        if is_local:
            source_path = self.local_folder_path
            if not source_path or not os.path.isdir(source_path):
                self.show_error("Please select a valid local folder")
                return
            self.add_to_history(source_path, is_local=True)
        else:
            source_path = self.repo_entry.text().strip()
            if not source_path:
                self.show_error("Please enter a repository URL")
                return
            self.add_to_history(self._safe_history_source(source_path), is_local=False)

        exclude_folders = list(self._parse_rules(self.exclude_folders_entry.text()))
        
        if self.ignore_pycache_checkbox.isChecked():
            exclude_folders.extend(['__pycache__', '*/__pycache__', '__pycache__/*', '*/__pycache__/*'])
            exclude_folders.append('*.pyc')
        if self.ignore_node_modules_checkbox.isChecked():
            exclude_folders.extend(['node_modules', '*/node_modules', 'node_modules/*', '*/node_modules/*'])
        if self.ignore_lock_files_checkbox.isChecked():
            exclude_folders.extend(['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'])
        if self.ignore_build_checkbox.isChecked():
            exclude_folders.extend(['build', '*/build', 'build/*', '*/build/*'])
            exclude_folders.extend(['dist', '*/dist', 'dist/*', '*/dist/*'])
        if self.ignore_ide_checkbox.isChecked():
            exclude_folders.extend(['.vscode', '*/.vscode', '.vscode/*', '*/.vscode/*'])
            exclude_folders.extend(['.idea', '*/.idea', '.idea/*', '*/.idea/*'])

        if self.ignore_log_files_checkbox.isChecked():
            exclude_folders.append('*.log')
        if self.ignore_secret_files_checkbox.isChecked():
            exclude_folders.extend(['.env', '.env.*', '*.pem', '*.key', 'id_rsa', 'credentials*'])

        try:
            max_file_bytes = self._parse_size_mib(self.max_file_size_entry.text(), 1)
            max_total_bytes = self._parse_size_mib(self.max_output_size_entry.text(), 20)
        except ValueError as error:
            self.show_error(str(error))
            return

        options = AnalysisOptions(
            source_path=source_path,
            is_local=is_local,
            include_extensions=self._parse_rules(self.include_entry.text()),
            exclude_extensions=self._parse_rules(self.exclude_entry.text()),
            exclude_patterns=tuple(exclude_folders),
            concatenate=not self.only_structure_checkbox.isChecked(),
            include_git=not self.ignore_git_checkbox.isChecked(),
            include_license=not self.ignore_license_checkbox.isChecked(),
            exclude_readme=self.ignore_readme_checkbox.isChecked(),
            copy_local_folder=self.copy_local_folder_checkbox.isChecked() if is_local else False,
            branch=self.branch_entry.text().strip() or None,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        )

        self.file_contents = {}
        self.file_positions = {}
        self.file_token_counts = {}
        self.current_result = None
        self.current_options = None
        self.file_tree.clear()
        self.tree_container.hide()
        self.refresh_button.hide()
        self.text_display.setPlainText("Analyzing…")
        try:
            self.start_analysis(options)
        except Exception as e:
            self.show_error(f"An error occurred: {str(e)}")

    @staticmethod
    def _parse_rules(text):
        return tuple(rule for rule in re.split(r"[,\s]+", text.strip()) if rule)

    @staticmethod
    def _parse_size_mib(text, default_mib):
        value = default_mib if not text.strip() else float(text)
        if value <= 0 or value > 1_024:
            raise ValueError("Size limits must be greater than 0 and no more than 1024 MiB.")
        return int(value * 1024 * 1024)

    @staticmethod
    def _safe_history_source(source):
        parsed = urlsplit(source)
        if not parsed.scheme:
            return source
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))

    def start_analysis(self, options):
        self.progress_dialog = QProgressDialog(
            "Analyzing...", "Cancel", 0, 100, self
        )
        self.progress_dialog.setWindowTitle("Analysis Progress")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumSize(QSize(400, 100))
        
        pat = None
        if not options.is_local and self.use_pat_checkbox.isChecked():
            pat = self.pat_entry.text().strip() or None

        self.pending_options = options
        self.analysis_thread = AnalysisThread(options, pat)

        self.analysis_thread.progress_signal.connect(self.update_progress)
        self.analysis_thread.finished_signal.connect(self.analysis_completed)
        self.analysis_thread.error_signal.connect(self.handle_analysis_error)
        self.analysis_thread.cancelled_signal.connect(self.handle_analysis_cancelled)
        self.analysis_thread.finished.connect(self.analysis_thread_finished)
        self.analysis_thread.start()

        self.analyze_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.progress_dialog.canceled.connect(self.cancel_analysis)
        self.progress_dialog.show()

    def cancel_analysis(self):
        if self.analysis_thread is not None and self.analysis_thread.isRunning():
            self.progress_dialog.setLabelText("Cancelling after the current operation…")
            self.progress_dialog.setCancelButton(None)
            self.analysis_thread.request_cancel()

    def update_progress(self, message, value):
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(value)

    def handle_analysis_error(self, error_message):
        self._close_progress_dialog()
        self.analyze_button.setEnabled(True)
        self.pending_options = None
        self.paths_to_restore = None
        self.refresh_button.setEnabled(self.local_radio.isChecked() and bool(self.file_positions))
        self.show_error(error_message)

    def handle_analysis_cancelled(self):
        self._close_progress_dialog()
        self.analyze_button.setEnabled(True)
        self.pending_options = None
        self.paths_to_restore = None
        self.refresh_button.setEnabled(False)
        self.text_display.setPlainText("Analysis cancelled.")

    def _close_progress_dialog(self):
        if self.progress_dialog:
            self.progress_dialog.blockSignals(True)
            self.progress_dialog.close()
            self.progress_dialog = None

    def analysis_thread_finished(self):
        thread = self.sender()
        if thread is self.analysis_thread:
            self.analysis_thread = None

    def analysis_completed(self, result):
        self._close_progress_dialog()
        self.analyze_button.setEnabled(True)
        self.current_result = result
        self.current_options = self.pending_options
        self.pending_options = None
        self.folder_structure = result.folder_structure
        self.text_display.setPlainText(result.full_text)
        self.update_counts()

        self.file_contents = result.file_contents
        self.file_positions = result.file_positions
        self.file_token_counts = {}

        if result.file_positions:
            self.update_sidebar(result.file_positions)
            if hasattr(self, 'paths_to_restore') and self.paths_to_restore:
                self._restore_checked_items(self.paths_to_restore)
                self.paths_to_restore = None
            self.tree_container.show()
            if self.local_radio.isChecked():
                self.refresh_button.show()
                self.refresh_button.setEnabled(True)
        else:
            self.tree_container.hide()
            self.refresh_button.hide()

        self.update_selected_counts()

        self.show_toast_message("Analysis completed")

    def _restore_checked_items(self, paths_to_restore):
        try:
            self._updating_items = True
            parents_to_update = []

            for path in paths_to_restore:
                item = self.path_to_item_map.get(path)
                if item:
                    item.setCheckState(0, Qt.CheckState.Checked)
                    parent = item.parent()
                    if parent and parent not in parents_to_update:
                        parents_to_update.append(parent)
            
            for parent in parents_to_update:
                self.update_parent_check_state(parent)

        finally:
            self._updating_items = False
            self.update_selected_counts()

    def update_sidebar(self, file_positions):
        if not file_positions:
            self.tree_container.hide()
            return

        # Clear the tree
        self.file_tree.clear()
        self.path_to_item_map.clear()

        # Disconnect signal temporarily to prevent events during tree building
        self.file_tree.itemChanged.disconnect(self.on_item_changed)

        # Create a dictionary to store tree items
        tree_items = {}

        # Add root item
        root_item = QTreeWidgetItem(self.file_tree, ["/"])
        root_item.setCheckState(0, Qt.CheckState.Unchecked)
        root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        root_item.setIcon(0, QIcon.fromTheme("folder"))
        tree_items["/"] = root_item

        # Add all other items
        for path in sorted(file_positions.keys()):
            parts = path.split("/")

            # Handle the case where the path starts with "."
            if parts[0] == '.':
                parts = parts[1:]

            current_path = ""
            parent_item = root_item

            for i, part in enumerate(parts):
                if not part:  # Skip empty parts
                    continue

                if i < len(parts) - 1:  # This is a directory
                    current_path = current_path + "/" + part if current_path else part

                    if current_path not in tree_items:
                        # Create new directory item
                        item = QTreeWidgetItem(parent_item, [part])
                        item.setCheckState(0, Qt.CheckState.Unchecked)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setIcon(0, QIcon.fromTheme("folder"))
                        tree_items[current_path] = item

                    parent_item = tree_items[current_path]
                else:  # This is a file
                    # Create file item
                    item = QTreeWidgetItem(parent_item, [part])
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    self.path_to_item_map[path] = item

                    # Set an icon based on file extension
                    if part.endswith(('.py')):
                        item.setIcon(0, QIcon.fromTheme("text-x-python"))
                    elif part.endswith(('.js')):
                        item.setIcon(0, QIcon.fromTheme("text-x-javascript"))
                    elif part.endswith(('.html', '.htm')):
                        item.setIcon(0, QIcon.fromTheme("text-html"))
                    elif part.endswith(('.css')):
                        item.setIcon(0, QIcon.fromTheme("text-css"))
                    elif part.endswith(('.md')):
                        item.setIcon(0, QIcon.fromTheme("text-x-markdown"))
                    elif part.endswith(('.json')):
                        item.setIcon(0, QIcon.fromTheme("application-json"))
                    elif part.endswith(('.xml')):
                        item.setIcon(0, QIcon.fromTheme("application-xml"))
                    elif part.endswith(('.txt')):
                        item.setIcon(0, QIcon.fromTheme("text-plain"))
                    else:
                        item.setIcon(0, QIcon.fromTheme("text-x-generic"))

        # Expand all items
        self.file_tree.expandAll()

        # Reconnect signal
        self.file_tree.itemChanged.connect(self.on_item_changed)

        # Show the tree container
        self.tree_container.show()

    def copy_selected_files(self):
        checked_files = self.get_checked_items()
        if not checked_files:
            self.show_message("No files selected - please check items to copy")
            return

        full_content, copied_count = self._serialize_checked_files(checked_files)
        if full_content:
            clipboard = QApplication.clipboard()
            clipboard.setText(full_content)
            self.show_toast_message(f"{copied_count} file(s) copied")
        else:
            self.show_message("No content found for selected files")

    def _apply_line_numbers(self, content):
        if not self.line_numbers_checkbox.isChecked():
            return content
        return "\n".join(
            f"{line_number}: {line}"
            for line_number, line in enumerate(content.splitlines(), start=1)
        )

    def _serialize_checked_files(self, checked_files):
        copied_content = []
        for path_parts, _ in sorted(checked_files, key=lambda item: "/".join(item[0])):
            full_path = "/".join(path_parts)
            content = self._get_file_content(full_path)
            if content is not None:
                copied_content.append(f"--{full_path}--\n{self._apply_line_numbers(content)}")
        return "\n\n".join(copied_content), len(copied_content)

    def get_checked_items(self, parent_item=None):
        checked_files = []

        if parent_item is None:
            # Start from the root
            root = self.file_tree.invisibleRootItem()
            for i in range(root.childCount()):
                checked_files.extend(self.get_checked_items(root.child(i)))
            return checked_files

        # This is a file if it has no children in the tree
        is_file = parent_item.childCount() == 0
        state = parent_item.checkState(0)

        if is_file:
            if state == Qt.CheckState.Checked:
                path = []
                current = parent_item
                while current is not None and current.text(0) != "/":
                    path.insert(0, current.text(0))
                    current = current.parent()
                if path:
                    checked_files.append((path, "file"))
        else:  # It's a directory
            for i in range(parent_item.childCount()):
                checked_files.extend(self.get_checked_items(parent_item.child(i)))

        return checked_files

    def copy_text(self):
        clipboard = QApplication.clipboard()
        text = self.current_result.full_text if self.current_result else self.text_display.toPlainText()
        clipboard.setText(text)
        self.show_toast_message("Full analysis copied")

    def copy_selection(self):
        cursor = self.text_display.textCursor()
        if cursor.hasSelection():
            clipboard = QApplication.clipboard()
            clipboard.setText(cursor.selectedText().replace("\u2029", "\n"))
            self.show_toast_message("Selection copied")
        else:
            self.show_message("No text selected")
            
    def copy_structure(self):
        if hasattr(self, 'folder_structure') and self.folder_structure:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.folder_structure)
            self.show_toast_message("Folder structure copied")
        else:
            self.show_message("No folder structure available to copy.")

    def copy_visible_text(self):
        # Copy only what's currently displayed in the text area
        text = self.text_display.toPlainText()
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.show_toast_message("Visible text copied")

    def save_full_text(self):
        text = self.current_result.full_text if self.current_result else self.text_display.toPlainText()
        if not text:
            self.show_message("No analysis text is available to save.")
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save ChaReCo context",
            "chareco-context.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not destination:
            return
        try:
            with open(destination, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except OSError as error:
            self.show_error(f"Could not save context: {error}")
            return
        self.show_toast_message("Full analysis saved")

    def show_toast_message(self, message):
        # Create a semi-transparent notification
        status_msg = QLabel(message, self)
        status_msg.setStyleSheet("""
            background-color: rgba(142, 68, 173, 0.8);
            color: white;
            border-radius: 0px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: bold;
        """)
        status_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_msg.adjustSize()

        # Center on the main window
        x = (self.width() - status_msg.width()) // 2
        y = self.height() - status_msg.height() - 30  # Position at the bottom
        status_msg.move(x, y)
        status_msg.show()

        # Auto-hide after 1.5 seconds
        timer = QTimer(self)
        timer.singleShot(1500, status_msg.deleteLater)

    def show_message(self, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Message")
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2b2b2b;
                color: white;
            }
            QLabel {
                color: white;
                background-color: transparent;
            }
            QPushButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 0px;
                padding: 5px 15px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
        """)
        msg_box.exec()

    def show_error(self, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Error")
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2b2b2b;
                color: white;
            }
            QLabel {
                color: white;
                background-color: transparent;
            }
            QPushButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 0px;
                padding: 5px 15px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
        """)
        msg_box.exec()

    def count_tokens(self, text):
        if self._token_encoding is None:
            return 0
        try:
            return len(self._token_encoding.encode(text))
        except Exception as e:
            logging.error(f"Error counting tokens: {str(e)}")
            return 0

    def update_counts(self):
        self._counts_timer.start(150)

    def _recalculate_counts(self):
        text = self.text_display.toPlainText()
        char_count = len(text)
        token_count = self.count_tokens(text)
        self.char_count_label.setText(f"Characters: {char_count}")
        self.token_count_label.setText(f"Tokens: {token_count}")

    def _get_file_token_count(self, file_path):
        if file_path in self.file_token_counts:
            return self.file_token_counts[file_path]
            
        content = self._get_file_content(file_path)
        if content:
            count = self.count_tokens(content)
            self.file_token_counts[file_path] = count
            return count
        return 0

    def update_selected_counts(self):
        self._selected_counts_timer.start(100)

    def _recalculate_selected_counts(self):
        checked_files = self.get_checked_items()
        serialized, _count = self._serialize_checked_files(checked_files)
        self.selected_token_count_label.setText(f"Selected Tokens: {self.count_tokens(serialized)}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
                if os.path.isdir(path):
                    self.local_radio.setChecked(True)
                    self.set_local_folder_path(path)
                    self.analyze_source()

#
