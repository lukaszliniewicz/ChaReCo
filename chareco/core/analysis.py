import os
import tempfile
import time
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from dulwich import porcelain
from chareco.core.utils import (
    get_structure, concatenate_files, safe_remove
)

class AnalysisThread(QThread):
    progress_signal = pyqtSignal(str, int)
    finished_signal = pyqtSignal(str, dict, dict)
    error_signal = pyqtSignal(str)

    def __init__(self, source_path, args, is_local=False, pat=None):
        super().__init__()
        self.source_path = source_path
        self.args = args
        self.is_local = is_local
        self.pat = pat

    def run(self):
        temp_dir = None
        try:
            if self.is_local:
                folder_path = self.source_path
                self.progress_signal.emit("Analyzing local folder...", 25)
            else:
                temp_dir = tempfile.mkdtemp()
                self.progress_signal.emit("Cloning repository...", 25)
                logging.info(f"Cloning repository: {self.source_path}")

                if self.pat:
                    if 'github.com' in self.source_path:
                        repo_url = self.source_path.replace('https://', f'https://{self.pat}@')
                    else:
                        repo_url = self.source_path
                else:
                    repo_url = self.source_path

                try:
                    porcelain.clone(repo_url, temp_dir)
                except Exception as e:
                    self.error_signal.emit(f"Failed to clone repository: {str(e)}")
                    safe_remove(temp_dir)
                    return

                folder_path = temp_dir

            self.progress_signal.emit("Generating folder structure...", 50)
            logging.info("Generating folder structure")
            structure = get_structure(
                folder_path,
                self.args.directories,
                self.args.exclude,
                self.args.include,
                not self.args.include_git,
                not self.args.include_license,
                self.args.exclude_readme,
                self.args.exclude_folders
            )

            content = f"Folder structure:\n{structure}\n"
            file_positions = {}
            file_contents = {}

            if self.args.concatenate:
                self.progress_signal.emit("Concatenating file contents...", 75)
                logging.info("Concatenating file contents")
                concat_content, file_positions, file_contents = concatenate_files(
                    folder_path,
                    self.args.exclude,
                    self.args.include,
                    not self.args.include_git,
                    not self.args.include_license,
                    self.args.exclude_readme,
                    self.args.exclude_folders
                )
                content += f"\nConcatenated content:\n{concat_content}"

            self.progress_signal.emit("Finalizing results...", 90)
            self.finished_signal.emit(content, file_positions, file_contents)

        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            self.error_signal.emit(str(e))
        finally:
            if temp_dir:
                logging.info("Cleaning up temporary directory")
                safe_remove(temp_dir)

#
