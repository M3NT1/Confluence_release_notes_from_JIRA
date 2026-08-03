import PyInstaller.__main__
import os
import sys

# Az aktuális könyvtár beállítása
current_dir = os.path.dirname(os.path.abspath(__file__))

# Windows-specifikus beállítások
if sys.platform.startswith('win'):
    separator = ';'
else:
    separator = ':'

# Az exe fájl összeállításához szükséges paraméterek
params = [
    'rn_excel_generalas_windows.py',  # A fő Python fájl
    '--onefile',  # Egyetlen exe fájl létrehozása
    '--noconsole',  # Konzol ablak elrejtése
    '--name=ReleaseNotesGenerator',  # Az exe fájl neve
    f'--add-data=config.json{separator}.',  # Config fájl hozzáadása
    '--icon=icon.ico' if os.path.exists('icon.ico') else None,  # Ikon hozzáadása (ha létezik)
    '--clean',  # Tiszta build
    '--windowed',  # Windows alkalmazás
    '--target-arch=x86_64',  # 64-bites Windows architektúra
    # Tkinter és alapvető modulok
    '--hidden-import=tkinter',
    '--hidden-import=tkinter.ttk',
    '--hidden-import=PIL._tkinter_finder',
    # Jaraco ve pkg_resources hiányzó modulok
    '--collect-all=jaraco',  # Collect all jaraco namespace package files
    '--collect-all=setuptools',  # Collect all setuptools
    '--hidden-import=pkg_resources',
    '--hidden-import=pkg_resources.extern',
    # JIRA és Git modulok
    '--collect-all=jira',
    '--hidden-import=git',
    '--hidden-import=git.util',
    # XML és adatfeldolgozás
    '--hidden-import=xml.etree.ElementTree',
    '--hidden-import=json',
    '--hidden-import=re',
    '--hidden-import=threading',
    '--hidden-import=tempfile',
    '--hidden-import=shutil',
    '--hidden-import=stat',
]

# None értékek eltávolítása
params = [p for p in params if p is not None]

# PyInstaller futtatása
PyInstaller.__main__.run(params) 