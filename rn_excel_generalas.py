import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext
import threading
from urllib.parse import urlparse, parse_qs
import pandas as pd
from datetime import datetime
import json
import base64
import os
from jira import JIRA, JIRAError
import time
import re

class ConfigManager:
    def __init__(self, config_file):
        self.config_file = config_file
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
                'Version Info': version_info,
                'Responsible': '',
                'Status': ''
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

        # Frame létrehozása a mezőknek
        input_frame = tk.Frame(root)
        input_frame.pack(padx=10, pady=5)

        # Input fields
        self.url_label = tk.Label(input_frame, text="JIRA keresési URL:")
        self.url_label.pack()
        self.url_entry = tk.Entry(input_frame, width=50)
        self.url_entry.pack()

        self.version_label = tk.Label(input_frame, text="Verziószám:")
        self.version_label.pack()
        self.version_entry = tk.Entry(input_frame, width=20)
        self.version_entry.pack()

        self.date_label = tk.Label(input_frame, text="Telepítés dátuma (YYYYMMDD):")
        self.date_label.pack()
        self.date_entry = tk.Entry(input_frame, width=20)
        self.date_entry.pack()
        # Alapértelmezett dátum beállítása
        self.date_entry.insert(0, datetime.now().strftime("%Y%m%d"))

        # Output field
        self.output_text = scrolledtext.ScrolledText(root, width=100, height=20)
        self.output_text.pack(padx=10, pady=5)

        # Submit button
        self.submit_button = tk.Button(root, text="Generálás", command=self.run_thread)
        self.submit_button.pack(pady=5)

        # Load configuration
        if not self.config_manager.load_config():
            self.ask_for_credentials()

    def ask_for_credentials(self):
        credentials = {}
        credentials['jira_url'] = simpledialog.askstring("JIRA URL", "Add meg a JIRA URL-t:",
                                                        initialvalue="https://jira.ulyssys.hu")
        credentials['jira_pat_token'] = simpledialog.askstring("JIRA PAT token",
                                                             "Add meg a JIRA Personal Access tokent:")
        self.config_manager.save_config(credentials)

    def log(self, message):
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.root.update()

    def run_thread(self):
        thread = threading.Thread(target=self.run)
        thread.start()

    def format_version_info(self, text):
        if not text or text == "KITÖLTENDŐ!!!":
            return text

        keywords = [
            "Fejlesztés/javítás leírása",
            "Érintett felhasználói kör",
            "Fejlesztés/javítás eredménye",
            "Új elemi jog",
            "Új menüpont",
            "Új eljárástípus",
            "Tesztelés"
        ]

        lines = text.split('\n')
        formatted_lines = []

        for line in lines:
            line = line.strip()
            found_keyword = False
            for keyword in keywords:
                if line.startswith(f"- {keyword}:") or line == f"- {keyword}:":
                    formatted_lines.append(f"- **{keyword}:**{line.split(':', 1)[1] if ':' in line else ''}")
                    found_keyword = True
                    break
            if not found_keyword:
                formatted_lines.append(line)

        return '\n'.join(formatted_lines)

    def generate_excel(self, issues, version, install_date):
        # Átalakítjuk az adatokat Excel-kompatibilis formátumra
        excel_data = []
        for issue in issues:
            external_links = []
            if issue['External Links']:
                for link in issue['External Links']:
                    external_links.append(f'=HYPERLINK("{link["url"]}", "{link["title"]}")')
            external_links_str = '\n'.join(external_links) if external_links else 'N/A'

            # Ticket ID hivatkozás formázása
            ticket_link = f'=HYPERLINK("{issue["Ticket URL"]}", "{issue["Ticket ID"]}")'

            # Megjegyzés formázása
            formatted_version_info = self.format_version_info(issue['Version Info'])

            excel_data.append({
                'Fejlesztés/javítás': issue['Summary'],
                'Szállító belső issue': ticket_link,
                'Redmine, RT jegy': external_links_str,
                'Megjegyzés': formatted_version_info,
                'Felelős': '',
                'Státusz': ''
            })

        # DataFrame létrehozása
        df = pd.DataFrame(excel_data)

        # Excel fájl neve a verzió és dátum alapján
        version = version.lower().replace('v', '')
        filename = f"v{version}_{install_date}.xlsx"

        # Excel fájl mentése
        writer = pd.ExcelWriter(filename, engine='xlsxwriter')
        df.to_excel(writer, sheet_name='Release Notes', index=False)

        # Formázás
        workbook = writer.book
        worksheet = writer.sheets['Release Notes']

        # Cellaformátumok
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

        # Link formátum
        link_format = workbook.add_format({
            'text_wrap': True,
            'border': 1,
            'valign': 'top',
            'font_color': 'blue',
            'underline': True
        })

        # Megjegyzés formátum alapértelmezett és félkövér változat
        comment_format = workbook.add_format({
            'text_wrap': True,
            'border': 1,
            'valign': 'top'
        })

        bold_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'border': 1,
            'valign': 'top'
        })
        # Oszlopszélességek beállítása
        worksheet.set_column('A:A', 40)  # Fejlesztés/javítás
        worksheet.set_column('B:B', 20)  # Szállító belső issue
        worksheet.set_column('C:C', 30)  # Redmine, RT jegy
        worksheet.set_column('D:D', 40)  # Megjegyzés
        worksheet.set_column('E:E', 20)  # Felelős
        worksheet.set_column('F:F', 15)  # Státusz

        # Fejléc formázása
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Cellák formázása
        for row_num in range(len(df)):
            for col_num in range(len(df.columns)):
                cell_value = df.iloc[row_num, col_num]

                # Hivatkozások formázása
                if col_num in [1, 2] and str(cell_value).startswith('=HYPERLINK'):
                    worksheet.write_formula(row_num + 1, col_num, cell_value, link_format)
                # Megjegyzés oszlop formázása
                elif col_num == 3:  # D oszlop
                    if cell_value and cell_value != "KITÖLTENDŐ!!!":
                        lines = str(cell_value).split('\n')
                        rich_text_parts = []

                        for line in lines:
                            if '**' in line:
                                # A sor részekre bontása a ** jelölők mentén
                                parts = line.split('**')
                                for i, part in enumerate(parts):
                                    if i % 2 == 0:  # Normál szöveg
                                        if part:
                                            rich_text_parts.append({'text': part, 'format': comment_format})
                                    else:  # Félkövér szöveg
                                        if part:
                                            rich_text_parts.append({'text': part, 'format': bold_format})
                            else:
                                rich_text_parts.append({'text': line, 'format': comment_format})
                            # Sortörés hozzáadása minden sor végéhez, kivéve az utolsót
                            if line != lines[-1]:
                                rich_text_parts.append({'text': '\n', 'format': comment_format})

                        # Rich text írása a cellába
                        try:
                            rich_text_args = []
                            for part in rich_text_parts:
                                rich_text_args.extend([part['text'], part['format']])
                            worksheet.write_rich_string(row_num + 1, col_num, *rich_text_args)
                        except Exception as e:
                            # Fallback: egyszerű szöveg írása hiba esetén
                            plain_text = ''.join(part['text'] for part in rich_text_parts)
                            worksheet.write(row_num + 1, col_num, plain_text, comment_format)
                    else:
                        worksheet.write(row_num + 1, col_num, cell_value, comment_format)
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

        # Dátum formátum ellenőrzése
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
            filename = self.generate_excel(issues, version, install_date)
            self.log(f"Excel fájl sikeresen létrehozva: {filename}")
            messagebox.showinfo("Siker", f"Az Excel fájl sikeresen létrehozva: {filename}")
        except Exception as e:
            self.log(f"Hiba történt az Excel generálása során: {str(e)}")
            messagebox.showerror("Hiba", f"Hiba történt az Excel generálása során: {str(e)}")

    @staticmethod
    def extract_query_from_url(url):
        """Lekérdezi a JQL lekérdezést vagy filter azonosítót a megadott JIRA keresési URL-ből."""
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
