# JIRA Release Notes Generator

Ez az alkalmazás segít a JIRA jegyekből Excel formátumú Release Notes-ok generálásában.

## Telepítés

### macOS (M1) verzió

1. Telepítse a Python 3.8 vagy újabb verziót a [Python hivatalos weboldaláról](https://www.python.org/downloads/)
2. Telepítse a szükséges függőségeket:
   ```bash
   pip install -r requirements.txt
   ```
3. Futtassa az alkalmazást:
   ```bash
   python rn_excel_generalas_macos.py
   ```

### Windows verzió

1. Telepítse a Python 3.8 vagy újabb verziót a [Python hivatalos weboldaláról](https://www.python.org/downloads/)
2. Telepítse a szükséges függőségeket:
   ```bash
   pip install -r requirements.txt
   ```
3. Futtassa az alkalmazást:
   ```bash
   python rn_excel_generalas_windows.py
   ```

## Használat

1. Az alkalmazás első indításakor meg kell adnia a JIRA URL-t és a Personal Access Token-t
2. A főablakban adja meg:
   - A JIRA keresési URL-t (filter vagy JQL lekérdezés)
   - A verziószámot
   - A telepítés dátumát (YYYYMMDD formátumban)
3. Kattintson a "Generálás és mentés" gombra
4. Válassza ki, hova szeretné menteni az Excel fájlt
5. Várja meg, amíg az alkalmazás befejezi a generálást

## Függőségek

- jira==3.5.2
- pandas==2.2.1
## JIRA Release Notes Generator

Egy Windows/macOS Python alkalmazás, amely JIRA jegyekből generál Excel formátumú Release Notes-ot, és a kapcsolódó Liquibase XML-ekből kiolvassa az adatbázis-változásokat.

### Főbb jellemzők
- JIRA API (PAT) használata jegyek lekérésére
- Liquibase changelog XML-ek beolvasása a git repository-ból (createTable, addColumn, renameColumn, dropColumn támogatott)
- Több munkalapos Excel generálás: `Release Notes`, `DB változások`, `data` (dropdown értékek)
- Fejléc-színek konfigurálhatók konstansokkal a fájl tetején
- A munkalapok első sora rögzítve (freeze panes)
- Fájlmentésnél jogosultsági ütközés kezelése: ha a célfájl zárolva van, felajánlja az átnevezést/új helyet

### Követelmények
- Python 3.8+ (a fejlesztés Windows-on történt)
- A projekt `requirements.txt` fájlban található függőségek (példa):
  ```text
  pandas==2.0.3
  jira==3.5.2
  XlsxWriter==3.1.9
  GitPython==3.1.43
  pyinstaller==6.4.0   # csak ha exe-t szeretne készíteni
  ```

### Telepítés és futtatás (fejlesztőknek)
1. Klónozza vagy helyezze a projektet a gépére.
2. Hozzon létre egy virtuális környezetet és aktiválja:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell
```
3. Telepítse a könyvtárakat:
```powershell
pip install -r requirements.txt
```
4. Futtassa a Windows-specifikus scriptet:
```powershell
python rn_excel_generalas_windows.py
```

### Konfiguráció
- A program `config.json` fájlba menti a felhasználó által megadott beállításokat (JIRA URL, PAT, Git token, legutóbbi JIRA keresés, verzió). A fájl tartalma többszörös Base64 kódolással van tárolva a könnyű elrejtés miatt.
- A következő konstansok a fájl tetején módosíthatók gyorsan: `RELEASE_NOTES_HEADER_COLOR`, `DB_CHANGES_HEADER_COLOR`, valamint oszlopszélesség-konstansok (`RELEASE_NOTES_COLUMN_WIDTHS`, `DB_CHANGES_COLUMN_WIDTHS`, `DATA_WORKSHEET_COLUMN_WIDTHS`).

### Excel formátum részletek
- Munkalapok sorrendje: `Release Notes`, `DB változások`, `data` (a `data` munkalap van legutoljára)
- `Release Notes`: megjeleníti a JIRA jegy összefoglalóját, a szállító belső jegy számát (csak a ticket ID jelenik meg, kattintásra a jegy URL-je nyílik meg), a Redmine/RT linkeket, valamint a strukturált verzió-információt.
- `DB változások`: minden adatbázis-változás külön sorban szerepel; az `addColumn` esetén minden `<column>` elemet külön sorba írunk. A `dropColumn` sorokhoz a leírás `Mező törlése`, és piros háttérformázást kapnak.
- `data`: tartalmazza a `Felelős` és `Státusz` dropdown listaértékeit, melyekre a `Release Notes` munkalap hivatkozik adatérvényesítés céljából.

### XML parsing megjegyzések
- A parser kezeli a névtereket (namespace-aware), és fallbackként név nélküli tageket is keres.
- Támogatott változtatások: `createTable`, `addColumn` (több `<column>` esetén minden oszlop külön sor), `renameColumn`, `dropColumn`.

### Futtatható EXE készítése (Windows)
- A projektben van egy `build.py` segédszkript, amely PyInstaller-t hív meg. Példa futtatás:
```powershell
cd c:\path\to\release_notes
python build.py
```
- Ismert PyInstaller-issue: a `jaraco` / `pkg_resources` csomagok néha hiányoznak a buildből — a `build.py` már tartalmaz collect/hidden-import beállításokat a problémák csökkentésére.

### Hibakeresés
- Ha Excel mentésnél PermissionError lép fel (a fájl nyitva van Excel-ben), a program felajánlja, hogy mentse átnevezve/új helyre.
- Ha a JIRA csatlakozás sikertelen, ellenőrizze az `jira_url` és a `jira_pat_token` értékét a beállításokban.

### További fejlesztési ötletek
- Cache a git repository számára a gyorsabb újrafuttatás érdekében
- Grafikus haladássáv hosszú XML-szkennelésekhez
- Beállítási képernyő a fejlécek és oszlopszélességek szerkesztéséhez

---
Frissítve: a jelen munkafájl tartalma és funkcionalitás szerint (XML parsing, dropColumn kezelés, Excel mentési hiba kezelés, exe build útmutató).
