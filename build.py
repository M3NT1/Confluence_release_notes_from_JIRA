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
    # Windows-specifikus DLL-ek hozzáadása
    '--hidden-import=tkinter',
    '--hidden-import=tkinter.ttk',
    '--hidden-import=PIL._tkinter_finder',
]

# None értékek eltávolítása
params = [p for p in params if p is not None]

# PyInstaller futtatása
PyInstaller.__main__.run(params) 