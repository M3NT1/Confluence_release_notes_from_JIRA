import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext, filedialog
import threading
from urllib.parse import urlparse, parse_qs
import pandas as pd
from datetime import datetime
import json
import base64
import os
import sys
from jira import JIRA, JIRAError
import time
import re


def get_resource_path(relative_path):
    """Get the path to a resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class ConfigManager:
    def __init__(self, config_file):
        self.config_file = get_resource_path(config_file)
        self.config = None

    def encode_data(self, data):
        for _ in range(3):
            data = base64.b64encode(data.encode()).decode()
        return data

    def decode_data(self, data):
        for _ in range(3):
            data = base64.b64decode(data.encode()).decode()
        return data

    def load_config(self):
        if not os.path.isfile(self.config_file):
            return False
        with open(self.config_file, 'r') as f:
            encrypted_data = f.read()
        self.config = json.loads(self.decode_data(encrypted_data))
        return True

    def save_config(self, config):
        self.config = config
        encrypted_data = self.encode_data(json.dumps(self.config))
        with open(self.config_file, 'w') as f:
            f.write(encrypted_data)


def connect_to_jira(jira_url, pat_token, log):
    try:
        jira = JIRA(server=jira_url.rstrip('/'), token_auth=pat_token)
        jira.myself()
        log("Sikeresen csatlakozva a JIRA-hoz!")
        return jira
    except JIRAError as e:
        log(f"Sikertelen csatlakozás a JIRA-hoz: {e.text}")
        return None


def is_valid_domain(url):
    return urlparse(url).netloc.endswith(("projekt.nak.hu", "rt5.nak.hu"))


def extract_web_links(issue):
    web_links = []
    if hasattr(issue.fields, 'issuelinks'):
        for link in issue.fields.issuelinks:
            if hasattr(link, 'object'):
                web_link = link.object
                if hasattr(web_link, 'url'):
                    url_ = web_link.url
                    if is_valid_domain(url_):
                        web_links.append({"url": web_link.url, "title": web_link.url})
    return web_links


def extract_remotelinks(jira, issue_key):
    try:
        remotelinks = jira.remote_links(issue_key)
        links = [{"url": link.object.url, "title": link.object.url}
                 for link in remotelinks if
                 hasattr(link, 'object') and hasattr(link.object, 'url') and is_valid_domain(link.object.url)]
        return links
    except JIRAError as e:
        print(f"Failed to fetch remote links for issue {issue_key}: {e.text}")
        return []


def fetch_jira_issues(jira, jql_query, is_filter, jira_url, log):
    try:
        start_time = time.time()
        if is_filter:
            issues = jira.search_issues(f'filter={jql_query}', maxResults=False)
        else:
            issues = jira.search_issues(jql_query, maxResults=False)

        issue_data = []
        for idx, issue in enumerate(issues):
            version_info = getattr(issue.fields, 'customfield_13240', None)
            if version_info is None or version_info.strip() in ['-', '–', '_', '—'] or len(version_info.strip()) <= 3:
                version_info = "KITÖLTENDŐ!!!"
            else:
                version_info = version_info.strip()

            all_links = []

            for link in issue.fields.issuelinks:
                if hasattr(link, 'outwardIssue'):
                    outward_issue = link.outwardIssue
                    external_link = f"{jira_url}/browse/{outward_issue.key}"
                    if is_valid_domain(external_link):
                        all_links.append({"url": external_link, "title": outward_issue.key})

            web_links = extract_web_links(issue)
            all_links.extend(web_links)

            remote_links = extract_remotelinks(jira, issue.key)
            all_links.extend(remote_links)

            issue_info = {
                'Summary': issue.fields.summary,
                'Ticket ID': issue.key,
                'Ticket URL': f"{jira_url}/browse/{issue.key}",
                'External Links': all_links,
                'Version Info': version_info
            }
            issue_data.append(issue_info)
            elapsed_time = time.time() - start_time
            log(f"{idx + 1}/{len(issues)} JIRA jegy feldolgozva (Eltelt idő: {elapsed_time:.2f} másodperc)")

        total_time = time.time() - start_time
        log(f"JIRA jegyek lekérése befejeződött {total_time:.2f} másodperc alatt.")
        return issue_data
    except JIRAError as e:
        log(f"Sikertelen JIRA jegyek lekérése: {e.text}")
        return []


class GUIApp:
    def __init__(self, root, config_manager):
        self.root = root
        self.config_manager = config_manager
        self.root.title("Excel Release Notes Generator")
        self.root.geometry("800x600")  # Windows-hoz optimalizált méret

        # Ikon beállítása Windows platformon
        try:
            self.root.iconbitmap(default="icon.ico")
        except tk.TclError:
            pass  # Ha nincs ikon, nincs probléma

        # Fő konténer
        main_container = tk.Frame(root, padx=10, pady=10)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Input mezők konténere
        input_frame = tk.Frame(main_container)
        input_frame.pack(fill=tk.X, pady=5)

        # URL mező
        url_frame = tk.Frame(input_frame)
        url_frame.pack(fill=tk.X, pady=2)
        self.url_label = tk.Label(url_frame, text="JIRA keresési URL:")
        self.url_label.pack(side=tk.LEFT)
        self.url_entry = tk.Entry(url_frame, width=50)
        self.url_entry.pack(side=tk.LEFT, padx=5)

        # Verzió mező
        version_frame = tk.Frame(input_frame)
        version_frame.pack(fill=tk.X, pady=2)
        self.version_label = tk.Label(version_frame, text="Verziószám:")
        self.version_label.pack(side=tk.LEFT)
        self.version_entry = tk.Entry(version_frame, width=20)
        self.version_entry.pack(side=tk.LEFT, padx=5)

        # Dátum mező
        date_frame = tk.Frame(input_frame)
        date_frame.pack(fill=tk.X, pady=2)
        self.date_label = tk.Label(date_frame, text="Telepítés dátuma (YYYYMMDD):")
        self.date_label.pack(side=tk.LEFT)
        self.date_entry = tk.Entry(date_frame, width=20)
        self.date_entry.pack(side=tk.LEFT, padx=5)
        self.date_entry.insert(0, datetime.now().strftime("%Y%m%d"))

        # Kimenet szövegmező
        self.output_text = scrolledtext.ScrolledText(main_container, width=100, height=20)
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=5)

        # Gombok konténere
        button_frame = tk.Frame(main_container)
        button_frame.pack(fill=tk.X, pady=5)

        self.submit_button = tk.Button(button_frame, text="Generálás és mentés", 
                                     command=self.run_thread, width=20, height=2)
        self.submit_button.pack(side=tk.LEFT, padx=5)

        pat_button = tk.Button(button_frame, text="JIRA PAT Token módosítása", 
                             command=self.update_pat_token, width=20, height=2)
        pat_button.pack(side=tk.LEFT, padx=5)

        exit_button = tk.Button(button_frame, text="Kilépés", 
                              command=root.destroy, width=10, height=2)
        exit_button.pack(side=tk.LEFT, padx=5)

        if not self.config_manager.load_config():
            self.ask_for_credentials()

    def update_pat_token(self):
        new_token = simpledialog.askstring("JIRA PAT token", "Add meg az új JIRA Personal Access tokent:",
                                         show="*")  # A show="*" miatt a beírt karakterek helyett * jelenik meg
        if new_token:  # Ha nem nyomta meg a Cancel gombot
            config = self.config_manager.config
            config['jira_pat_token'] = new_token
            self.config_manager.save_config(config)
            messagebox.showinfo("Siker", "A JIRA PAT token sikeresen frissítve!")

    def ask_for_credentials(self):
        credentials = {}
        credentials['jira_url'] = simpledialog.askstring("JIRA URL", "Add meg a JIRA URL-t:",
                                                         initialvalue="https://jira.ulyssys.hu")
        credentials['jira_pat_token'] = simpledialog.askstring("JIRA PAT token",
                                                               "Add meg a JIRA Personal Access tokent:",
                                                               show="*")
        self.config_manager.save_config(credentials)

    def log(self, message):
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.root.update()

    def run_thread(self):
        thread = threading.Thread(target=self.run)
        thread.start()

    def extract_field_content(self, text, field_name):
        if not text or text == "KITÖLTENDŐ!!!":
            return ""

        # Keresési minták a különböző formátumokhoz
        patterns = [
            f"{field_name}:(.*?)(?=(?:Fejlesztés/javítás|Érintett felhasználói kör|Fejlesztés/javítás eredménye|Új elemi jog|Új menüpont|Új eljárástípus|Tesztelés):|\Z)",
            f"{field_name}:(.*?)(?=\n|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if content and content != "-":
                    return content
        return ""

    def format_version_info(self, text):
        if not text or text == "KITÖLTENDŐ!!!":
            return text

        # A formázandó mezők listája
        fields = [
            "Fejlesztés/javítás leírása",
            "Érintett felhasználói kör",
            "Fejlesztés/javítás eredménye",
            "Új elemi jog",
            "Új menüpont",
            "Új eljárástípus",
            "Tesztelés"
        ]

        # A szöveg sorokra bontása
        lines = text.split('\n')
        formatted_lines = []
        current_field = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Mező kezdetének keresése
            for field in fields:
                if line.startswith(f"{field}:"):
                    current_field = field
                    formatted_lines.append(f"{field}: {line.split(':', 1)[1].strip()}")
                    break
            else:
                if current_field and line:
                    formatted_lines.append(f"  {line}")

        return '\n'.join(formatted_lines)

    def generate_excel(self, issues, version, install_date, output_path=None):
        excel_data = []
        for issue in issues:
            external_links = []
            if issue['External Links']:
                for link in issue['External Links']:
                    external_links.append(f'=HYPERLINK("{link["url"]}", "{link["title"]}")')
            external_links_str = '\n'.join(external_links) if external_links else 'N/A'

            ticket_link = f'=HYPERLINK("{issue["Ticket URL"]}", "{issue["Ticket ID"]}")'
            version_info = issue['Version Info']

            # Mezők kinyerése
            description = self.extract_field_content(version_info, "Fejlesztés/javítás leírása")
            users = self.extract_field_content(version_info, "Érintett felhasználói kör")
            result = self.extract_field_content(version_info, "Fejlesztés/javítás eredménye")

            # Új jogok/menük/eljárástípusok külön-külön
            new_rights = self.extract_field_content(version_info, "Új elemi jog")
            new_menu = self.extract_field_content(version_info, "Új menüpont")
            new_procedure = self.extract_field_content(version_info, "Új eljárástípus")

            testing = self.extract_field_content(version_info, "Tesztelés")

            # Formázott verzió információ
            formatted_version_info = self.format_version_info(version_info)

            excel_data.append({
                'Fejlesztés/javítás': issue['Summary'],
                'Szállító belső issue': ticket_link,
                'Redmine, RT jegy': external_links_str,
                'Fejlesztés/javítás leírása': formatted_version_info,
                'Érintett felhasználói kör': users,
                'Fejlesztés/javítás eredménye': result,
                'Új elemi jog': new_rights if new_rights and new_rights != "-" else "",
                'Új menüpont': new_menu if new_menu and new_menu != "-" else "",
                'Új eljárástípus': new_procedure if new_procedure and new_procedure != "-" else "",
                'Tesztelés módja': testing,
                'Felelős': '',
                'Státusz': ''
            })

        df = pd.DataFrame(excel_data)
        version = version.lower().replace('v', '')
        
        if output_path:
            # Ha megadtak egy teljes elérési utat, azt használjuk
            filename = output_path
        else:
            # Ha nem, akkor az alapértelmezett nevet használjuk az aktuális könyvtárban
            filename = f"v{version}_{install_date}.xlsx"

        writer = pd.ExcelWriter(filename, engine='xlsxwriter')

        # Release Notes munkalap létrehozása
        df.to_excel(writer, sheet_name='Release Notes', index=False)

        workbook = writer.book
        worksheet = writer.sheets['Release Notes']

        # Data munkalap létrehozása
        data_worksheet = workbook.add_worksheet('data')

        # Értékkészletek definiálása kezdeti értékekkel
        felelős_list = [
            'Csernyánszki-Hermann Zsófia',
            'Félegyházi Viki',
            'Göndöcs Szilvi',
            'Kollár Tamás',
            'Sárközi Anna'
        ]

        status_list = [
            'Folyamatban',
            'Hibás',
            'Élesíthető'
        ]

        # Oszlopfejlécek a data munkalapon
        data_worksheet.write(0, 0, 'Felelős', workbook.add_format({'bold': True}))
        data_worksheet.write(0, 1, 'Státusz', workbook.add_format({'bold': True}))

        # Értékkészletek írása a data munkalapra
        for idx, value in enumerate(felelős_list, start=1):
            data_worksheet.write(idx, 0, value)

        for idx, value in enumerate(status_list, start=1):
            data_worksheet.write(idx, 1, value)

        # Formátumok
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D9D9D9',
            'border': 1,
            'text_wrap': True,
            'valign': 'top',
            'align': 'center'
        })

        cell_format = workbook.add_format({
            'text_wrap': True,
            'border': 1,
            'valign': 'top'
        })

        link_format = workbook.add_format({
            'text_wrap': True,
            'border': 1,
            'valign': 'top',
            'font_color': 'blue',
            'underline': True
        })

        # Oszlopszélességek beállítása
        column_widths = {
            'A': 40,  # Fejlesztés/javítás
            'B': 20,  # Szállító belső issue
            'C': 30,  # Redmine, RT jegy
            'D': 40,  # Fejlesztés/javítás leírása
            'E': 30,  # Érintett felhasználói kör
            'F': 30,  # Fejlesztés/javítás eredménye
            'G': 30,  # Új elemi jog
            'H': 30,  # Új menüpont
            'I': 30,  # Új eljárástípus
            'J': 30,  # Tesztelés módja
            'K': 20,  # Felelős
            'L': 15  # Státusz
        }

        for col, width in column_widths.items():
            worksheet.set_column(f'{col}:{col}', width)

        # Data worksheet oszlopszélességek
        data_worksheet.set_column('A:A', 30)
        data_worksheet.set_column('B:B', 15)

        # Fejléc formázása a Release Notes munkalapon
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Adatérvényesítés beállítása a Felelős oszlophoz
        worksheet.data_validation(f'K2:K{len(df) + 1}', {
            'validate': 'list',
            'source': '=INDIRECT("data!$A$2:$A$1000")',  # Dinamikus tartomány az A oszlopra
            'input_title': 'Felelős választása',
            'input_message': 'Válasszon a listából'
        })

        # Adatérvényesítés beállítása a Státusz oszlophoz
        worksheet.data_validation(f'L2:L{len(df) + 1}', {
            'validate': 'list',
            'source': '=INDIRECT("data!$B$2:$B$1000")',  # Dinamikus tartomány a B oszlopra
            'input_title': 'Státusz választása',
            'input_message': 'Válasszon a listából'
        })

        # Cellák formázása
        for row_num in range(len(df)):
            for col_num in range(len(df.columns)):
                cell_value = df.iloc[row_num, col_num]

                if col_num in [1, 2] and str(cell_value).startswith('=HYPERLINK'):
                    worksheet.write_formula(row_num + 1, col_num, cell_value, link_format)
                else:
                    worksheet.write(row_num + 1, col_num, cell_value, cell_format)

        writer.close()
        return filename

    def run(self):
        config = self.config_manager.config
        jira_url = config['jira_url']
        jira_pat_token = config['jira_pat_token']

        search_url = self.url_entry.get()
        version = self.version_entry.get()
        install_date = self.date_entry.get()

        if not re.match(r'^\d{8}$', install_date):
            self.log("Hibás dátum formátum. Használja a YYYYMMDD formátumot.")
            messagebox.showerror("Hiba", "Hibás dátum formátum. Használja a YYYYMMDD formátumot.")
            return

        query_or_filter, is_filter = self.extract_query_from_url(search_url)
        if not query_or_filter:
            self.log("Helytelen URL formátum. Kérjük, használjon JIRA filter vagy JQL linket.")
            messagebox.showerror("Hiba", "Helytelen URL formátum. Kérjük, használjon JIRA filter vagy JQL linket.")
            return

        self.log(f"Kinyert lekérdezés/szűrő: {query_or_filter} (szűrő: {is_filter})")

        jira = connect_to_jira(jira_url, jira_pat_token, self.log)
        if not jira:
            self.log("Sikertelen csatlakozás a JIRA-hoz.")
            messagebox.showerror("Hiba", "Sikertelen csatlakozás a JIRA-hoz")
            return

        issues = fetch_jira_issues(jira, query_or_filter, is_filter, jira_url, self.log)
        if not issues:
            self.log("Nincs találat, vagy sikertelen volt a lekérdezés.")
            messagebox.showerror("Hiba", "Nincs találat, vagy sikertelen volt a lekérdezés.")
            return

        try:
            # Alapértelmezett fájlnév előkészítése
            version_clean = version.lower().replace('v', '')
            default_filename = f"v{version_clean}_{install_date}.xlsx"
            
            # Fájlmentés ablak megjelenítése
            self.log("Válassza ki a mentés helyét...")
            output_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel fájlok", "*.xlsx")],
                initialfile=default_filename,
                title="Excel fájl mentése"
            )
            
            # Ha a felhasználó nem választott mentési helyet, megszakítjuk a folyamatot
            if not output_path:
                self.log("Az Excel generálása meg lett szakítva a felhasználó által.")
                return
                
            filename = self.generate_excel(issues, version, install_date, output_path)
            self.log(f"Excel fájl sikeresen létrehozva: {filename}")
            messagebox.showinfo("Siker", f"Az Excel fájl sikeresen létrehozva: {filename}")
        except Exception as e:
            self.log(f"Hiba történt az Excel generálása során: {str(e)}")
            messagebox.showerror("Hiba", f"Hiba történt az Excel generálása során: {str(e)}")

    @staticmethod
    def extract_query_from_url(url):
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if 'jql' in query_params:
            return query_params.get('jql', [''])[0], False
        elif 'filter' in query_params:
            return query_params.get('filter', [''])[0], True
        return '', False


if __name__ == "__main__":
    root = tk.Tk()
    config_manager = ConfigManager('config.json')
    app = GUIApp(root, config_manager)
    root.mainloop() 