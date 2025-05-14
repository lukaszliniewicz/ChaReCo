import os
import shutil
import logging
import fnmatch
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_binary(file_path):
    binary_extensions = [
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.tif', '.tiff',
        '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
        '.zip', '.tar', '.gz', '.rar', '.7z', '.exe', '.dll', '.so', '.dylib',
        '.pyc', '.pyd', '.db', '.sqlite', '.dat', '.bin', '.o', '.class'
    ]

    if any(file_path.lower().endswith(ext) for ext in binary_extensions):
        return True

    try:
        with open(file_path, 'rb') as check_file:
            chunk = check_file.read(1024)
            
            if b'\0' in chunk:
                return True
            
            if (chunk.startswith(b'\x89PNG') or
                chunk.startswith(b'GIF8') or
                chunk.startswith(b'\xff\xd8\xff') or
                chunk.startswith(b'PK\x03\x04')):
                return True
            
            try:
                chunk.decode('utf-8')
                return False
            except UnicodeDecodeError:
                return True
                
    except Exception:
        return True


def is_git_related(path):
    git_patterns = ['.git', '.gitignore', '.gitattributes']
    return any(pattern in path for pattern in git_patterns)

def should_exclude(path, ignore_git, exclude_license, exclude_readme, exclude_folders=None):
    filename = os.path.basename(path)
    if ignore_git and is_git_related(path):
        return True
    if exclude_license and filename.lower() in ['license', 'license.txt', 'license.md']:
        return True
    if exclude_readme and filename.lower() in ['readme', 'readme.txt', 'readme.md']:
        return True
    if exclude_folders and any(fnmatch.fnmatch(path, pattern) for pattern in exclude_folders):
        return True
    return False

def get_structure(path, only_dirs=False, exclude=None, include=None,
                 ignore_git=True, exclude_license=True, exclude_readme=False, exclude_folders=None):
    structure = []
    for root, dirs, files in os.walk(path):
        if ignore_git and is_git_related(root):
            continue

        rel_path = os.path.relpath(root, path)
        if exclude_folders and any(fnmatch.fnmatch(rel_path, pattern) for pattern in exclude_folders):
            dirs[:] = []
            continue

        level = root.replace(path, '').count(os.sep)
        indent = '│   ' * (level - 1) + '├── '
        subindent = '│   ' * level + '├── '

        if only_dirs:
            structure.append(f'{indent}{os.path.basename(root)}/')
        else:
            structure.append(f'{indent}{os.path.basename(root)}/')
            for f in files:
                file_path = os.path.join(rel_path, f)
                if should_exclude(file_path, ignore_git, exclude_license, exclude_readme, exclude_folders):
                    continue
                if exclude and any(f.endswith(ext) for ext in exclude):
                    continue
                if include and not any(f.endswith(ext) for ext in include):
                    continue
                structure.append(f'{subindent}{f}')
    return '\n'.join(structure)

def convert_notebook_to_markdown(file_path):
    try:
        import jupytext
        notebook = jupytext.read(file_path)
        return jupytext.writes(notebook, fmt='md')
    except Exception as e:
        logging.error(f"Error converting notebook {file_path}: {str(e)}")
        return None

def concatenate_files(path, exclude=None, include=None, ignore_git=True,
                     exclude_license=True, exclude_readme=False, exclude_folders=None):
    content = []
    file_positions = {}
    current_position = 0
    file_contents = {}

    for root, dirs, files in sorted(os.walk(path)):
        if ignore_git and is_git_related(root):
            continue

        rel_path = os.path.relpath(root, path)
        
        if exclude_folders and any(fnmatch.fnmatch(rel_path, pattern) for pattern in exclude_folders):
            dirs[:] = []
            continue
            
        if rel_path != '.':
            header = f"\n---{rel_path}/---\n"
        else:
            header = f"\n---/---\n"
        content.append(header)
        current_position += len(header)

        for file in sorted(files):
            file_path = os.path.join(root, file)
            rel_file_path = os.path.join(rel_path, file)
            
            if should_exclude(rel_file_path, ignore_git, exclude_license, exclude_readme, exclude_folders):
                continue
                
            if file.endswith('.ipynb'):
                md_content = convert_notebook_to_markdown(file_path)
                if md_content is None:
                    continue
                file_content = md_content
            else:
                if is_binary(file_path):
                    continue
                if exclude and any(file.endswith(ext) for ext in exclude):
                    continue
                if include and not any(file.endswith(ext) for ext in include):
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                except Exception as e:
                    logging.error(f"Error reading file {file_path}: {str(e)}")
                    continue

            file_header = f"\n--{file}--\n"
            content.append(file_header)
            file_positions[os.path.join(rel_path, file)] = current_position
            current_position += len(file_header)
            content.append(file_content)
            
            file_contents[os.path.join(rel_path, file)] = file_content
            
            current_position += len(file_content)

    return '\n'.join(content), file_positions, file_contents

def concatenate_folder_files(folder_path, file_contents):
    result = []

    for path, content in file_contents.items():
        folder, filename = os.path.split(path)
        if folder == folder_path:
            result.append(f"\n--{filename}--\n{content}")

    return "\n".join(result) if result else "No text files in this folder."

def safe_remove(path):
    def onerror(func, path, exc_info):
        logging.warning(f"Failed to remove {path}. Skipping.")

    if os.path.isdir(path):
        shutil.rmtree(path, onerror=onerror)
    elif os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logging.warning(f"Failed to remove file {path}: {str(e)}")

#