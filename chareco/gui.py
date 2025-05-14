import os
import argparse
import multiprocessing
import logging
import sys
import tiktoken
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, QLineEdit,
    QCheckBox, QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QSplitter, QProgressDialog, QTabWidget,
    QRadioButton, QButtonGroup, QFrame, QToolButton, QStyle, QProgressBar,
    QScrollArea
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer, QRunnable, QThreadPool, QObject
)
from PyQt6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QIcon, QFont, QBrush, QTextDocument
)

from chareco.core.analysis import AnalysisThread
from chareco.core.search import SearchWorker
from chareco.core.utils import concatenate_folder_files

class App(QMainWindow):
    def __init__(self):
        super().__init__()

        # Main window configuration
        self.setWindowTitle("ChaReCo")
        
        # Create a size that works for most screens
        self.resize(1400, 900)
        
        # Set to maximized state to use full screen
        self.showMaximized()

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
        self.scroll_area.setFixedWidth(300)
        
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
        self.main_layout.addWidget(self.scroll_area)
        self.main_layout.addWidget(self.right_panel)

        # Setup the left panel contents
        self.setup_left_panel()

        # Setup the right panel contents
        self.setup_right_panel()

        # Initialize state variables
        self.file_positions = {}
        self.file_contents = {}  # Store file contents for faster access
        self.progress_dialog = None
        self.local_folder_path = None
        self.search_results = []
        self.current_search_index = -1
        self.is_searching = False
        self.search_progress_bar = None
        self.search_workers = []
        self.thread_pool = QThreadPool.globalInstance()
        
        # Set maximum thread count (can be adjusted based on system)
        self.max_threads = max(4, multiprocessing.cpu_count())
        self.thread_pool.setMaxThreadCount(self.max_threads)

        # Setup dark theme
        self.setup_dark_theme()
        
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
            QTextEdit {
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
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 0px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                border: none;
                background: #2b2b2b;
                height: 12px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #555555;
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
        self.repo_entry = QLineEdit()
        self.repo_entry.setPlaceholderText("Enter GitHub repo URL")

        # Add checkbox for PAT
        self.use_pat_checkbox = QCheckBox("I would like to provide a private key")
        self.use_pat_checkbox.toggled.connect(self.toggle_pat_visibility)

        # PAT container
        self.pat_container = QWidget()
        self.pat_container_layout = QVBoxLayout(self.pat_container)
        self.pat_container_layout.setContentsMargins(0, 0, 0, 0)
        self.pat_container.hide()  # Initially hidden

        self.pat_label = QLabel("Personal Access Token:")
        self.pat_entry = QLineEdit()
        self.pat_entry.setPlaceholderText("For private repositories")
        self.pat_entry.setEchoMode(QLineEdit.EchoMode.Password)

        self.pat_container_layout.addWidget(self.pat_label)
        self.pat_container_layout.addWidget(self.pat_entry)

        self.repo_input_layout.addWidget(self.repo_label)
        self.repo_input_layout.addWidget(self.repo_entry)
        self.repo_input_layout.addWidget(self.use_pat_checkbox)
        self.repo_input_layout.addWidget(self.pat_container)

        # Local folder selection
        self.local_input_widget = QWidget()
        self.local_input_layout = QVBoxLayout(self.local_input_widget)
        self.local_input_layout.setContentsMargins(0, 0, 0, 0)

        self.local_path_label = QLabel("Local folder path:")
        self.local_path_display = QLineEdit()
        self.local_path_display.setReadOnly(True)
        self.local_path_display.setPlaceholderText("No folder selected")

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_local_folder)

        self.local_input_layout.addWidget(self.local_path_label)
        self.local_input_layout.addWidget(self.local_path_display)
        self.local_input_layout.addWidget(self.browse_button)

        # Add repository input to source container (default view)
        self.source_layout.addWidget(self.repo_input_widget)
        self.local_input_widget.hide()  # Initially hide the local input widget

        self.left_layout.addSpacing(5)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        self.left_layout.addWidget(separator2)
        self.left_layout.addSpacing(5)

        # Options section
        self.options_label = QLabel("Options:")
        self.options_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.left_layout.addWidget(self.options_label)
        self.left_layout.addSpacing(5)

        # Display options
        self.only_structure_checkbox = QCheckBox("Only show structure, don't concatenate")
        self.only_structure_checkbox.toggled.connect(self.toggle_structure_only)
        self.left_layout.addWidget(self.only_structure_checkbox)
        self.left_layout.addSpacing(5)

        # Include file types
        self.include_label = QLabel("Include file types:")
        self.left_layout.addWidget(self.include_label)
        self.include_entry = QLineEdit()
        self.include_entry.setPlaceholderText("e.g. .py .js .java")
        self.left_layout.addWidget(self.include_entry)
        self.left_layout.addSpacing(5)

        # Exclude file types
        self.exclude_label = QLabel("Exclude file types:")
        self.left_layout.addWidget(self.exclude_label)
        self.exclude_entry = QLineEdit()
        self.exclude_entry.setPlaceholderText("e.g. .log .tmp .bak")
        self.left_layout.addWidget(self.exclude_entry)
        self.left_layout.addSpacing(5)

        # Exclude folder patterns
        self.exclude_folders_label = QLabel("Exclude folders (glob patterns):")
        self.left_layout.addWidget(self.exclude_folders_label)
        self.exclude_folders_entry = QLineEdit()
        self.exclude_folders_entry.setPlaceholderText("e.g. **/node_modules/* **/build/*")
        self.left_layout.addWidget(self.exclude_folders_entry)
        self.left_layout.addSpacing(5)

        # Checkboxes for various options
        self.include_git_checkbox = QCheckBox("Include git files")
        self.left_layout.addWidget(self.include_git_checkbox)

        self.exclude_readme_checkbox = QCheckBox("Exclude Readme")
        self.left_layout.addWidget(self.exclude_readme_checkbox)

        self.exclude_license_checkbox = QCheckBox("Exclude license")
        self.exclude_license_checkbox.setChecked(True)
        self.left_layout.addWidget(self.exclude_license_checkbox)
        self.left_layout.addSpacing(10)

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
        self.left_layout.addWidget(self.analyze_button)

        # Add spacer to push everything to the top
        self.left_layout.addStretch()

        # Add a version label at the bottom
        version_label = QLabel("v2.0.0")
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
        else:
            self.repo_input_widget.hide()
            self.local_input_widget.show()
            self.source_layout.addWidget(self.local_input_widget)

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

        # Create tree toolbar with compact buttons
        self.tree_toolbar = QWidget()
        self.tree_toolbar.setProperty("class", "ButtonGroup")
        self.tree_toolbar_layout = QHBoxLayout(self.tree_toolbar)
        self.tree_toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.tree_toolbar_layout.setSpacing(5)

        # Create compact buttons with icons
        self.copy_selected_button = QToolButton()
        self.copy_selected_button.setText("Copy Files")
        self.copy_selected_button.setToolTip("Copy selected files to clipboard")
        self.copy_selected_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_selected_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_selected_button.clicked.connect(self.copy_selected_files)
        self.tree_toolbar_layout.addWidget(self.copy_selected_button)

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
        self.text_toolbar.setFixedWidth(500)  # Set a fixed width for the toolbar
        self.text_toolbar_layout = QHBoxLayout(self.text_toolbar)
        self.text_toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.text_toolbar_layout.setSpacing(5)

        # Create compact buttons with icons
        self.copy_all_button = QToolButton()
        self.copy_all_button.setText("Copy All")
        self.copy_all_button.setToolTip("Copy all text to clipboard")
        self.copy_all_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_all_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_all_button.clicked.connect(self.copy_text)
        self.text_toolbar_layout.addWidget(self.copy_all_button)

        self.copy_selection_button = QToolButton()
        self.copy_selection_button.setText("Copy Selection")
        self.copy_selection_button.setToolTip("Copy selected text to clipboard")
        self.copy_selection_button.setIcon(QIcon.fromTheme("edit-cut"))
        self.copy_selection_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_selection_button.clicked.connect(self.copy_selection)
        self.text_toolbar_layout.addWidget(self.copy_selection_button)
        
        self.copy_visible_button = QToolButton()
        self.copy_visible_button.setText("Copy Visible")
        self.copy_visible_button.setToolTip("Copy currently visible text to clipboard")
        self.copy_visible_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_visible_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_visible_button.clicked.connect(self.copy_visible_text)
        self.text_toolbar_layout.addWidget(self.copy_visible_button)
        
        # Show full content button - shows all content even if a folder/file is selected
        self.show_all_button = QToolButton()
        self.show_all_button.setText("Show All")
        self.show_all_button.setToolTip("Show all content")
        self.show_all_button.setIcon(QIcon.fromTheme("view-fullscreen"))
        self.show_all_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.show_all_button.clicked.connect(self.show_all_content)
        self.text_toolbar_layout.addWidget(self.show_all_button)

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

        # Add search result count label
        self.search_result_label = QLabel("")
        self.count_layout.addWidget(self.search_result_label)

        self.count_layout.addStretch()

        # Add count frame to text layout
        self.text_layout.addWidget(self.count_frame, 0, Qt.AlignmentFlag.AlignRight)

        # Add text edit for displaying content
        self.text_display = QTextEdit()
        self.text_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.text_display.textChanged.connect(self.update_counts)
        self.text_display.setTabStopDistance(QFont("Consolas").pointSizeF() * 4)
        self.text_layout.addWidget(self.text_display)

        # Add text container to splitter
        self.splitter.addWidget(self.text_container)

        # Set splitter proportions (25% tree, 75% text)
        self.splitter.setSizes([250, 750])

    def show_all_content(self):
        """Show all content in the text display."""
        # Use the analyzed content stored in memory
        full_content = self.text_display.document().toPlainText()
        
        # Check if we have distinct section markers or this is already the full content
        if "Folder structure:" in full_content:
            # This may already be the full content, do nothing
            return
            
        # Try to reconstruct from folder structure and concatenated content
        content = []
        
        # Append folder structure if available
        if hasattr(self, 'folder_structure') and self.folder_structure:
            content.append(f"Folder structure:\n{self.folder_structure}")
        
        # Add concatenated content
        if self.file_contents:
            content.append("\nConcatenated content:")
            
            # Group files by directory
            dirs = {}
            for path in sorted(self.file_contents.keys()):
                dirname = os.path.dirname(path)
                if dirname not in dirs:
                    dirs[dirname] = []
                dirs[dirname].append(path)
            
            # Add directory headers and files
            for dirname in sorted(dirs.keys()):
                if dirname:
                    content.append(f"\n---{dirname}/---")
                else:
                    content.append("\n---/---")
                    
                for filepath in dirs[dirname]:
                    filename = os.path.basename(filepath)
                    file_content = self.file_contents[filepath]
                    content.append(f"\n--{filename}--\n{file_content}")
        
        # Set reconstructed content
        self.text_display.clear()
        self.text_display.setPlainText("\n".join(content))
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
        # Don't start a new search if one is in progress
        if self.is_searching:
            return
            
        # Clear previous search results
        self.clear_search_highlights()
        
        # Get search parameters
        search_text = self.search_input.text()
        if not search_text:
            return
            
        self.is_searching = True
        self.search_button.setEnabled(False)
        
        # Check if progress bar exists before using it
        if hasattr(self, 'search_progress_bar') and self.search_progress_bar is not None:
            self.search_progress_bar.setValue(0)
            self.search_progress_bar.show()
        else:
            # Create it if it doesn't exist
            self.search_progress_bar = QProgressBar()
            self.search_progress_bar.setFixedHeight(10)
            self.search_progress_bar.setTextVisible(False)
            self.search_layout.addWidget(self.search_progress_bar)
            self.search_progress_bar.setValue(0)
            self.search_progress_bar.show()
        
        # Prepare search parameters  
        case_sensitive = self.case_sensitive_checkbox.isChecked()
        whole_word = self.whole_word_checkbox.isChecked()
        use_regex = self.regex_checkbox.isChecked()
        
        # Create list of files to search
        search_files = []
        for file_path, content in self.file_contents.items():
            search_files.append((file_path, content))
        
        # Break files into chunks for multiple threads
        chunk_size = max(1, len(search_files) // self.max_threads)
        chunks = [search_files[i:i + chunk_size] for i in range(0, len(search_files), chunk_size)]
        
        # Clear previous results
        self.search_results = []
        self.current_search_index = -1
        
        # Keep track of active workers
        self.active_workers = len(chunks)
        
        # Create and start workers
        for chunk in chunks:
            worker = SearchWorker(chunk, search_text, case_sensitive, whole_word, use_regex)
            worker.signals.result.connect(self.handle_search_results)
            worker.signals.progress.connect(self.update_search_progress)
            worker.signals.error.connect(self.handle_search_error)
            worker.signals.finished.connect(self.worker_finished)
            
            # Start the worker
            self.thread_pool.start(worker)

    def update_search_progress(self, progress_value):
        # This will aggregate progress from multiple workers
        if hasattr(self, 'search_progress_bar') and self.search_progress_bar is not None:
            self.search_progress_bar.setValue(progress_value)

    def finalize_search(self):
        # Hide progress bar
        if hasattr(self, 'search_progress_bar') and self.search_progress_bar is not None:
            self.search_progress_bar.hide()
        
        self.is_searching = False
        self.search_button.setEnabled(True)
        
        # Display final results
        if self.search_results:
            # Flatten and organize results
            total_matches = sum(len(matches) for _, matches in self.search_results)
            self.search_result_label.setText(f"Found {total_matches} matches in {len(self.search_results)} files")
            
            # Display results in text area
            self.display_search_results()
        else:
            self.search_result_label.setText("No matches found")
            
        # Enable/disable navigation buttons
        self.update_navigation_buttons()

    def handle_search_results(self, results):
        # Append results from this worker
        if results:
            self.search_results.extend(results)
            
            # Update UI with preliminary results
            self.search_result_label.setText(f"Searching... Found: {len(self.search_results)} files with matches")

    def handle_search_error(self, error_message):
        self.is_searching = False
        self.search_button.setEnabled(True)
        self.search_progress_bar.hide()
        self.show_error(error_message)

    def worker_finished(self):
        self.active_workers -= 1
        
        # If all workers have finished, finalize the search
        if self.active_workers <= 0:
            self.finalize_search()


    def display_search_results(self):
        """Display search results in the text area with highlighted occurrences"""
        if not self.search_results:
            return
            
        # Clear text display
        self.text_display.clear()
        
        # Create a formatted display of search results
        for file_path, matches in self.search_results:
            # Add file header
            self.text_display.append(f"\n--{file_path}--")
            
            # Get file content
            content = self.file_contents.get(file_path, "")
            if not content:
                continue
                
            # Add a few lines before and after each match with highlights
            lines = content.split('\n')
            highlighted_sections = []
            last_line_displayed = -1
            
            for match in matches:
                # Find the line number for this match
                match_start = match.start()
                line_start = content.rfind('\n', 0, match_start) + 1
                match_end = match.end()
                
                # Find line number
                line_number = content[:line_start].count('\n')
                
                # Determine the context range (3 lines before and after)
                start_line = max(0, line_number - 3)
                end_line = min(len(lines), line_number + 4)  # +4 because the range is exclusive
                
                # If we already displayed these lines, skip
                if start_line <= last_line_displayed:
                    start_line = last_line_displayed + 1
                
                # If no new lines to display, skip
                if start_line >= end_line:
                    continue
                    
                # Add separator if this isn't the first section
                if highlighted_sections:
                    highlighted_sections.append("...")
                
                # Extract the context lines
                context_lines = lines[start_line:end_line]
                
                # Format with line numbers
                formatted_lines = [f"{i+start_line+1}: {line}" for i, line in enumerate(context_lines)]
                
                # Remember the last line we displayed
                last_line_displayed = end_line - 1
                
                # Add to our sections
                highlighted_sections.append('\n'.join(formatted_lines))
            
            # Add the highlighted sections to the text display
            self.text_display.append('\n'.join(highlighted_sections))
        
        # Set cursor to the beginning
        cursor = self.text_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_display.setTextCursor(cursor)
        
        # Highlight search terms
        search_text = self.search_input.text()
        if not self.regex_checkbox.isChecked():
            # Simple text highlighting
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
        self.find_and_scroll_to(f"\n--{file_path}--")
        
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
        self.find_and_scroll_to(f"\n--{file_path}--")
        
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
        self.clear_search_button.setEnabled(has_results)

    def clear_search(self):
        # Clear search input
        self.search_input.clear()
        
        # Clear highlights
        self.clear_search_highlights()
        
        # Reset search results
        self.search_results = []
        self.current_search_index = -1
        
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
            
        return os.path.join(*path) if path else ""

    def display_folder_contents(self, folder_path):
        """Display concatenated contents of all files in a folder."""
        # Clear the current display
        self.text_display.clear()
        
        # Concatenate all files in this folder
        concatenated = concatenate_folder_files(folder_path, self.file_contents)
        
        # Set the text
        self.text_display.setPlainText(concatenated)
        
        # Update counts
        self.update_counts()

    def display_file_content(self, file_path):
        """Display a single file's content."""
        # Check if we have this file in our contents
        if file_path in self.file_contents:
            self.text_display.clear()
            self.text_display.setPlainText(self.file_contents[file_path])
            self.update_counts()
        else:
            # Try to find it with different separator format
            alt_path = file_path.replace('\\', '/')
            
            # Try with dot prefix for root files
            dot_path = os.path.join('.', file_path)
            
            if alt_path in self.file_contents:
                self.text_display.clear()
                self.text_display.setPlainText(self.file_contents[alt_path])
                self.update_counts()
            elif dot_path in self.file_contents:
                self.text_display.clear()
                self.text_display.setPlainText(self.file_contents[dot_path])
                self.update_counts()
            else:
                self.text_display.clear()
                self.text_display.setPlainText(f"File content not found for {file_path}")

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

    def update_children_check_state(self, parent_item, checked):
        if parent_item is None:
            return
            
        check_state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        
        # Use a queue for breadth-first traversal
        items_to_process = [parent_item]
        
        # Disable UI updates during bulk operations
        self.file_tree.setUpdatesEnabled(False)
        
        try:
            while items_to_process:
                current_item = items_to_process.pop(0)
                
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
            # Count checked and total children
            total_children = current.childCount()
            if total_children == 0:
                break
                
            checked_children = sum(1 for i in range(total_children)
                                if current.child(i).checkState(0) == Qt.CheckState.Checked)
            
            # Update current state based on children
            if checked_children == 0:
                current.setCheckState(0, Qt.CheckState.Unchecked)
            elif checked_children == total_children:
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

    def deselect_all_files(self):
        self._updating_items = True
        # Update root items
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self.update_children_check_state(item, False)
        self._updating_items = False

    def analyze_source(self):
        # Determine whether to analyze a remote repo or local folder
        is_local = self.local_radio.isChecked()

        if is_local:
            source_path = self.local_folder_path
            if not source_path or not os.path.isdir(source_path):
                self.show_error("Please select a valid local folder")
                return
        else:
            source_path = self.repo_entry.text()
            if not source_path:
                self.show_error("Please enter a repository URL")
                return

        # Prepare arguments
        args = argparse.Namespace(
            input=source_path,
            directories=False,
            exclude=self.exclude_entry.text().split() if self.exclude_entry.text() else None,
            include=self.include_entry.text().split() if self.include_entry.text() else None,
            exclude_folders=self.exclude_folders_entry.text().split() if self.exclude_folders_entry.text() else None,
            concatenate=not self.only_show_structure,  # Use the structure-only setting
            include_git=self.include_git_checkbox.isChecked(),
            include_license=not self.exclude_license_checkbox.isChecked(),
            exclude_readme=self.exclude_readme_checkbox.isChecked()
        )

        # Clear current data
        self.file_contents = {}

        # Run analysis
        try:
            self.start_analysis(args, is_local)
        except Exception as e:
            self.show_error(f"An error occurred: {str(e)}")

    def start_analysis(self, args, is_local=False):
        source_path = args.input

        # Create progress dialog
        self.progress_dialog = QProgressDialog(
            "Analyzing...", "Cancel", 0, 100, self
        )
        self.progress_dialog.setWindowTitle("Analysis Progress")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumSize(QSize(400, 100))
        
        # Start analysis thread
        pat = None
        if not is_local and hasattr(self, 'use_pat_checkbox') and self.use_pat_checkbox.isChecked():
            pat = self.pat_entry.text()
            
        self.analysis_thread = AnalysisThread(
            source_path, args, is_local, pat
        )

        self.analysis_thread.progress_signal.connect(self.update_progress)
        self.analysis_thread.finished_signal.connect(self.analysis_completed)
        self.analysis_thread.error_signal.connect(self.handle_analysis_error)
        self.analysis_thread.start()

        self.progress_dialog.canceled.connect(self.analysis_thread.terminate)
        self.progress_dialog.show()

    def update_progress(self, message, value):
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(value)

    def handle_analysis_error(self, error_message):
        if self.progress_dialog:
            self.progress_dialog.close()
        self.show_error(error_message)

    def analysis_completed(self, content, file_positions, file_contents):
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Save folder structure in case we need it later
        if "Folder structure:" in content:
            folder_structure_section = content.split("Concatenated content:", 1)[0]
            self.folder_structure = folder_structure_section.replace("Folder structure:\n", "").strip()

        # Update UI
        self.text_display.clear()
        self.text_display.setPlainText(content)
        self.update_counts()

        # Store file contents for faster access
        self.file_contents = file_contents
        self.file_positions = file_positions

        # Update file tree if we have file positions
        if file_positions:
            self.update_sidebar(file_positions)
            self.tree_container.show()
        else:
            self.tree_container.hide()

        # Show success message
        self.show_message("Analysis completed.")

    def update_sidebar(self, file_positions):
        if not file_positions:
            self.tree_container.hide()
            return

        # Clear the tree
        self.file_tree.clear()

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
            parts = path.split(os.sep)

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
        # Get the checked items from the tree
        checked_items = self.get_checked_items()

        if not checked_items:
            self.show_message("No files selected - please check items to copy")
            return

        copied_content = []

        for path_parts, item_type in checked_items:
            # Only process files, not directories
            if item_type == "directory":
                continue

            # Construct the full path
            if len(path_parts) > 1:
                full_path = os.path.join(*path_parts)
            else:
                full_path = path_parts[0]

            # Get the file content from our cached content
            if full_path in self.file_contents:
                file_content = self.file_contents[full_path]
                copied_content.append(f"--{path_parts[-1]}--\n{file_content}")
            else:
                # Try with different separator format
                alt_path = full_path.replace('\\', '/')
                if alt_path in self.file_contents:
                    file_content = self.file_contents[alt_path]
                    copied_content.append(f"--{path_parts[-1]}--\n{file_content}")

        if copied_content:
            full_content = "\n\n".join(copied_content)
            clipboard = QApplication.clipboard()
            clipboard.setText(full_content)
            self.show_toast_message(f"{len(copied_content)} file(s) copied")
        else:
            self.show_message("No content found for selected files")

    def get_checked_items(self, parent_item=None):
        checked_items = []

        if parent_item is None:
            # Start from the root
            root = self.file_tree.invisibleRootItem()
            for i in range(root.childCount()):
                checked_items.extend(self.get_checked_items(root.child(i)))
        else:
            # Process this item
            if parent_item.checkState(0) == Qt.CheckState.Checked:
                # Get the full path
                path = []
                current = parent_item
                while current is not None and current.text(0) != "/":
                    path.insert(0, current.text(0))
                    current = current.parent()

                if path:  # Avoid empty paths
                    # Determine if it's a file or directory
                    is_file = (parent_item.childCount() == 0 or '.' in path[-1])
                    if is_file:
                        checked_items.append((path, "file"))
                    else:
                        checked_items.append((path, "directory"))

            # Process children
            for i in range(parent_item.childCount()):
                child_items = self.get_checked_items(parent_item.child(i))
                checked_items.extend(child_items)

        return checked_items

    def copy_text(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_display.toPlainText())
        self.show_toast_message("All text copied")

    def copy_selection(self):
        cursor = self.text_display.textCursor()
        if cursor.hasSelection():
            clipboard = QApplication.clipboard()
            clipboard.setText(cursor.selectedText())
            self.show_toast_message("Selection copied")
        else:
            self.show_message("No text selected")
            
    def copy_visible_text(self):
        # Copy only what's currently displayed in the text area
        text = self.text_display.toPlainText()
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.show_toast_message("Visible text copied")

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
        try:
            encoding = tiktoken.encoding_for_model("gpt-4")
            return len(encoding.encode(text))
        except Exception as e:
            logging.error(f"Error counting tokens: {str(e)}")
            return 0

    def update_counts(self):
        text = self.text_display.toPlainText()
        char_count = len(text)
        token_count = self.count_tokens(text)
        self.char_count_label.setText(f"Characters: {char_count}")
        self.token_count_label.setText(f"Tokens: {token_count}")

#