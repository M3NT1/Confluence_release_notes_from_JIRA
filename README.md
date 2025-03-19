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
- xlsxwriter==3.1.9

## Megjegyzések

- Az alkalmazás automatikusan menti a JIRA bejelentkezési adatokat titkosítva
- Az Excel fájl tartalmaz egy "data" munkalapot a validációs listákkal
- A generált Excel fájl tartalmazza a JIRA jegyek linkjeit és a verzióinformációkat 