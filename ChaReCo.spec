# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# --- This section collects all necessary files ---
datas_jupytext, binaries_jupytext, *_ = collect_all('jupytext')
datas_dulwich, binaries_dulwich, *_ = collect_all('dulwich')
datas_tiktoken, binaries_tiktoken, *_ = collect_all('tiktoken')

# --- This section defines the main application analysis ---
a = Analysis(
    ['run.py'],
    pathex=[],
    # Add all collected binaries here
    binaries=binaries_jupytext + binaries_dulwich + binaries_tiktoken,
    # Add all collected data files here
    datas=datas_jupytext + datas_dulwich + datas_tiktoken,
    
    # --- FIX FOR TIKTOKEN STARTS HERE ---
    hiddenimports=[
        'qtpy',
        'tiktoken_ext', 
        'tiktoken_ext.openai_public'
    ],
    # --- FIX FOR TIKTOKEN ENDS HERE ---
    
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ChaReCo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # IMPORTANT: Replace with the actual path to your icon file
)