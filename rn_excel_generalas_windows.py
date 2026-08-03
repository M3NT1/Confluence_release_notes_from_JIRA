# -*- coding: utf-8 -*-
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
import tempfile
import shutil
from git import Repo, GitCommandError
import xml.etree.ElementTree as ET
import stat

git_repository_url = "https://gitlab.ulyssys.hu/hu.kiruly.ekozig/szakterulet-demo.git"
ekk2_folder_path = "app-persistence-jog/src/main/resources/META-INF/liquibase"

string_to_search = ["renameColumn", "createTable", "addColumn", "dropColumn"]

# Column width configurations for Excel worksheets
RELEASE_NOTES_COLUMN_WIDTHS = {
    'A': 40,  # Fejlesztés/javítás
    'B': 20,  # Szállító belső issue
    'C': 46,  # Redmine, RT jegy
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

DB_CHANGES_COLUMN_WIDTHS = {
    'A': 12,  # Verzió
    'B': 53,  # Tábla
    'C': 50,  # Mező
    'D': 40,  # Új Mezőnév
    'E': 23,  # Változás Leírása
    'F': 50  # Megjegyzés
}

DATA_WORKSHEET_COLUMN_WIDTHS = {
    'A': 30,  # Felelős
    'B': 15  # Státusz
}

# Header color configurations
RELEASE_NOTES_HEADER_COLOR = '#C5D9F1'
DB_CHANGES_HEADER_COLOR = '#C5D9F1'


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


def get_base_jira_url(jira_url):
    """Extract base JIRA URL from a full search URL if needed"""
    parsed = urlparse(jira_url)
    # Return just scheme + netloc (base URL) if query params or path contains 'issues' or 'browse'
    if parsed.query or '/issues' in parsed.path or '/browse' in parsed.path:
        return f"{parsed.scheme}://{parsed.netloc}"
    return jira_url


def connect_to_jira(jira_url, pat_token, log):
    try:
        # Extract base URL if the user accidentally provided a search URL
        base_url = get_base_jira_url(jira_url)
        log(f"Csatlakozás a JIRA-hoz: {base_url}")
        jira = JIRA(server=base_url.rstrip('/'), token_auth=pat_token)
        jira.myself()
        log("Sikeresen csatlakozva a JIRA-hoz!")
        return jira
    except JIRAError as e:
        log(f"JIRA hiba: {e.text}")
        return None
    except Exception as e:
        log(f"Sikertelen csatlakozás a JIRA-hoz: {str(e)}")
        log(f"Hiba típusa: {type(e).__name__}")
        log(f"Kérjük ellenőrizze a JIRA URL-t és az auth tokent")
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
    except Exception as e:
        print(f"Error extracting remote links for issue {issue_key}: {str(e)}")
        return []


def fetch_jira_issues(jira, jql_query, is_filter, jira_url, log):
    try:
        start_time = time.time()
        # Normalize jira_url to base (in case user pasted a search URL)
        base_url = get_base_jira_url(jira_url)
        if is_filter:
            issues = jira.search_issues(f'filter={jql_query}', maxResults=False)
        else:
            issues = jira.search_issues(jql_query, maxResults=False)

        issue_data = []
        for idx, issue in enumerate(issues):
            try:
                version_info = getattr(issue.fields, 'customfield_13240', None)
                if version_info is None or version_info.strip() in ['-', '–', '_', '—'] or len(version_info.strip()) <= 3:
                    version_info = "KITÖLTENDŐ!!!"
                else:
                    version_info = version_info.strip()

                all_links = []

                for link in issue.fields.issuelinks:
                    if hasattr(link, 'outwardIssue'):
                        outward_issue = link.outwardIssue
                        external_link = f"{base_url}/browse/{outward_issue.key}"
                        if is_valid_domain(external_link):
                            all_links.append({"url": external_link, "title": outward_issue.key})

                web_links = extract_web_links(issue)
                all_links.extend(web_links)

                remote_links = extract_remotelinks(jira, issue.key)
                all_links.extend(remote_links)

                issue_info = {
                    'Summary': issue.fields.summary,
                    'Ticket ID': issue.key,
                    'Ticket URL': f"{base_url}/browse/{issue.key}",
                    'External Links': all_links,
                    'Version Info': version_info
                }
                issue_data.append(issue_info)
                elapsed_time = time.time() - start_time
                log(f"{idx + 1}/{len(issues)} JIRA jegy feldolgozva (Eltelt idő: {elapsed_time:.2f} másodperc)")
            except Exception as e:
                log(f"Hiba a {issue.key} jegy feldolgozásakor: {str(e)}")
                continue

        total_time = time.time() - start_time
        log(f"JIRA jegyek lekérése befejeződött {total_time:.2f} másodperc alatt.")
        return issue_data
    except JIRAError as e:
        log(f"Sikertelen JIRA jegyek lekérése: {e.text}")
        return []
    except Exception as e:
        log(f"Hiba a JIRA jegyek lekérésekor: {str(e)}")
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

        git_button = tk.Button(button_frame, text="GitLab Token módosítása", 
                             command=self.update_git_token, width=20, height=2)
        git_button.pack(side=tk.LEFT, padx=5)

        exit_button = tk.Button(button_frame, text="Kilépés", 
                              command=root.destroy, width=10, height=2)
        exit_button.pack(side=tk.LEFT, padx=5)

        if not self.config_manager.load_config():
            self.ask_for_credentials()
        else:
            # Restore saved JIRA search URL and version from config
            if 'jira_search_url' in self.config_manager.config:
                self.url_entry.insert(0, self.config_manager.config['jira_search_url'])
            if 'version' in self.config_manager.config:
                self.version_entry.insert(0, self.config_manager.config['version'])

    def update_pat_token(self):
        new_token = simpledialog.askstring("JIRA PAT token", "Add meg az új JIRA Personal Access tokent:",
                                         show="*")  # A show="*" miatt a beírt karakterek helyett * jelenik meg
        if new_token:  # Ha nem nyomta meg a Cancel gombot
            config = self.config_manager.config
            config['jira_pat_token'] = new_token
            self.config_manager.save_config(config)
            messagebox.showinfo("Siker", "A JIRA PAT token sikeresen frissítve!")

    def update_git_token(self):
        new_token = simpledialog.askstring("GitLab Token", "Add meg az új GitLab személyes hozzáférési tokent:",
                                         show="*")
        if new_token:
            config = self.config_manager.config
            config['git_token'] = new_token
            self.config_manager.save_config(config)
            messagebox.showinfo("Siker", "A GitLab token sikeresen frissítve!")

    def ask_for_credentials(self):
        credentials = {}
        credentials['jira_url'] = simpledialog.askstring("JIRA URL", 
                                                         "Add meg a JIRA szerver URL-t (pl. https://jira.ulyssys.hu)\nNE a keresési URL-t!",
                                                         initialvalue="https://jira.ulyssys.hu")
        credentials['jira_pat_token'] = simpledialog.askstring("JIRA PAT token",
                                                               "Add meg a JIRA Personal Access tokent:",
                                                               show="*")
        credentials['git_token'] = simpledialog.askstring("GitLab Token",
                                                         "Add meg a GitLab személyes hozzáférési tokent:",
                                                         show="*")
        self.config_manager.save_config(credentials)

    def log(self, message):
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.root.update()

    def run_thread(self):
        thread = threading.Thread(target=self.run)
        thread.start()

    def clone_repository(self, git_token):
        """Clone the Git repository to a temporary directory"""
        try:
            temp_dir = tempfile.mkdtemp()
            repo_url = f"https://oauth2:{git_token}@gitlab.ulyssys.hu/hu.kiruly.ekozig/szakterulet-demo.git"
            self.log(f"Git repository klónozása: {temp_dir}")
            Repo.clone_from(repo_url, temp_dir)
            return temp_dir
        except GitCommandError as e:
            self.log(f"Sikertelen Git repository klónozás: {str(e)}")
            return None

    def inspect_directory_structure(self, path, max_depth=3, current_depth=0, prefix=""):
        """List directory structure for debugging"""
        if current_depth > max_depth or not os.path.isdir(path):
            return ""
        
        structure = ""
        try:
            items = sorted(os.listdir(path))
            dirs = [item for item in items if os.path.isdir(os.path.join(path, item))]
            files = [item for item in items if os.path.isfile(os.path.join(path, item))]
            
            # Show directories
            for dirname in dirs[:10]:  # Limit to first 10 to avoid too much output
                structure += f"{prefix}📁 {dirname}/\n"
                if current_depth < max_depth:
                    subpath = os.path.join(path, dirname)
                    structure += self.inspect_directory_structure(subpath, max_depth, current_depth + 1, prefix + "  ")
            
            # Show first few files
            for filename in files[:5]:
                structure += f"{prefix}📄 {filename}\n"
            
            if len(files) > 5:
                structure += f"{prefix}... és további {len(files) - 5} fájl\n"
                
        except PermissionError:
            structure += f"{prefix}[Hozzáférés megtagadva]\n"
        except Exception as e:
            structure += f"{prefix}[Hiba: {str(e)}]\n"
        
        return structure

    def scan_ekk2_folder(self, repo_dir, ticket_id):
        """Find folders under ekk2_folder_path matching the ticket ID, parse XMLs, and extract DB changes.

        Behavior:
        - Walk `ekk2_folder_path` recursively.
        - If a folder's basename equals the `ticket_id` (case-insensitive), find all XML files
          in that folder (including subdirectories).
        - Parse each XML file using `parse_xml_for_db_changes` to extract database modifications.
        - Logs progress via `self.log` for found folders and parsed changes.

        Returns a list of dicts with database change information. Empty list if none.
        """
        ekk2_path = os.path.join(repo_dir, ekk2_folder_path)
        db_changes = []

        if not os.path.isdir(ekk2_path):
            self.log(f"{ticket_id}: ekk2 mappa nem létezik: {ekk2_path}")
            self.log(f"Könyvtár szerkezet ellenőrzése: {repo_dir}")
            struct = self.inspect_directory_structure(repo_dir, max_depth=2)
            self.log("Elérhető mappa szerkezet:")
            for line in struct.split('\n')[:50]:  # Show first 50 lines
                if line:
                    self.log(f"  {line}")
            return db_changes

        self.log(f"{ticket_id}: ekk2 mappa tartalmának szkennelése: {ekk2_path}")

        try:
            all_dirs = []
            for dirpath, dirnames, filenames in os.walk(ekk2_path):
                basename = os.path.basename(dirpath)
                all_dirs.append(basename)
                
                if basename.lower() != ticket_id.lower():
                    continue

                rel_dir = os.path.relpath(dirpath, repo_dir)
                self.log(f"{ticket_id}: Pontos mappa egyezés: {rel_dir} — XML fájlok feldolgozása...")

                # collect and parse XML files under this matched folder (walk subdirs as well)
                for sub_root, sub_dirs, sub_files in os.walk(dirpath):
                    for fname in sub_files:
                        if not fname.lower().endswith('.xml'):
                            continue
                        file_path = os.path.join(sub_root, fname)
                        rel_file = os.path.relpath(file_path, repo_dir)
                        self.log(f"{ticket_id}: XML fájl feldolgozása: {rel_file}")
                        
                        # Parse the XML file to extract database changes
                        changes = self.parse_xml_for_db_changes(file_path)
                        if changes:
                            self.log(f"{ticket_id}: {len(changes)} adatbázis módosítás találva a fájlban")
                            db_changes.extend(changes)
                        else:
                            self.log(f"{ticket_id}: Nincs adatbázis módosítás ebben az XML fájlban")

                # once exact folder handled, we don't need to find other folders with same name deeper
            if not db_changes:
                self.log(f"{ticket_id}: Nincs adatbázis módosítás. (Elérhető mappák: {', '.join(all_dirs[:10])}...)")
        except Exception as e:
            self.log(f"Hiba az ekk2 mappa szkennelése során: {str(e)}")

        return db_changes

    def parse_xml_for_db_changes(self, xml_file_path):
        """Parse XML file and extract database change information.
        
        Returns a list of dicts with keys:
        - change_type: 'createTable', 'addColumn', or 'renameColumn'
        - table_name: name of the table
        - column_name: column name (for addColumn)
        - old_column_name: old column name (for renameColumn)
        - new_column_name: new column name (for renameColumn)
        """
        changes = []
        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # Define namespace (liquibase typically uses this)
            namespace_uri = 'http://www.liquibase.org/xml/ns/dbchangelog'
            
            # Search for database change elements
            for change_type in string_to_search:
                # Try with namespace first
                tag_with_ns = '{' + namespace_uri + '}' + change_type
                elements = root.findall('.//' + tag_with_ns)
                
                # If not found, try without namespace
                if not elements:
                    elements = root.findall('.//' + change_type)
                
                for elem in elements:
                    change_info = {'change_type': change_type}
                    
                    if change_type == 'createTable':
                        # Extract tableName attribute
                        table_name = elem.get('tableName')
                        if table_name:
                            change_info['table_name'] = table_name
                            changes.append(change_info)
                    
                    elif change_type == 'addColumn':
                        # Extract tableName and all column elements (handle multiple columns)
                        column_tag_ns = '{' + namespace_uri + '}' + 'column'
                        column_elems = elem.findall('.//' + column_tag_ns)
                        if not column_elems:
                            column_elems = elem.findall('.//column')

                        table_name = elem.get('tableName')

                        for column_elem in column_elems:
                            if column_elem is None:
                                continue
                            column_name = column_elem.get('name')
                            if table_name and column_name:
                                change_info = {'change_type': change_type, 'table_name': table_name, 'column_name': column_name}
                                changes.append(change_info)
                    
                    elif change_type == 'renameColumn':
                        # Extract tableName, oldColumnName, newColumnName
                        table_name = elem.get('tableName')
                        old_name = elem.get('oldColumnName')
                        new_name = elem.get('newColumnName')
                        
                        if table_name and old_name and new_name:
                            change_info['table_name'] = table_name
                            change_info['old_column_name'] = old_name
                            change_info['new_column_name'] = new_name
                            changes.append(change_info)
                    
                    elif change_type == 'dropColumn':
                        # Handle dropColumn: attribute columnName or nested <column> elements
                        table_name = elem.get('tableName')
                        col_attr = elem.get('columnName') or elem.get('name')
                        if table_name and col_attr:
                            changes.append({'change_type': change_type, 'table_name': table_name, 'column_name': col_attr})
                        else:
                            column_tag_ns = '{' + namespace_uri + '}' + 'column'
                            column_elems = elem.findall('.//' + column_tag_ns)
                            if not column_elems:
                                column_elems = elem.findall('.//column')
                            for column_elem in column_elems:
                                if column_elem is None:
                                    continue
                                column_name = column_elem.get('name') or column_elem.get('columnName')
                                if table_name and column_name:
                                    changes.append({'change_type': change_type, 'table_name': table_name, 'column_name': column_name})
        
        except Exception as e:
            print(f"Hiba az XML fájl feldolgozása során ({xml_file_path}): {str(e)}")
        
        return changes

    def extract_field_content(self, text, field_name):
        if not text or text == "KITÖLTENDŐ!!!":
            return ""
        
        escaped_field_name = re.escape(field_name)

        next_fields = [
            "Fejlesztés/javítás", "Érintett felhasználói kör", "Fejlesztés/javítás eredménye", 
            "Új elemi jog", "Új menüpont", "Új eljárástípus", 
            "Adatbázis változás leírása", "Érintett tábla", "Érintett mező(k)", "Tesztelés"
        ]

        escaped_next_fields = "|".join([re.escape(field) for field in next_fields])

        # Keresési minták a különböző formátumokhoz
        patterns = [
            rf"{escaped_field_name}:(.*?)(?=(?:{escaped_next_fields}):|\Z)",
            rf"{escaped_field_name}:(.*?)(?=\n|$)",
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
            "Adatbázis változás leírása",
            "Érintett tábla",
            "Érintett mező(k)",
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

    def generate_excel(self, issues, version, install_date, git_data=None, output_path=None):
        excel_data = []
        for idx, issue in enumerate(issues):
            # Prepare external links: if exactly one link, keep as HYPERLINK formula;
            # if more than one, store plain text with each URL on its own line.
            external_links_list = issue.get('External Links') or []
            if len(external_links_list) == 1:
                ln = external_links_list[0]
                external_links_str = f'=HYPERLINK("{ln["url"]}", "{ln.get("title", ln["url"]) }")'
            elif len(external_links_list) > 1:
                # Plain text, one URL per line
                external_links_str = '\n'.join([l.get('url', '') for l in external_links_list])
            else:
                external_links_str = 'N/A'

            # Store ticket display (ID) and keep URL in internal field for hyperlink
            ticket_link = issue["Ticket ID"]
            ticket_url_internal = issue["Ticket URL"]
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
                'Státusz': '',
                '__ticket_url': ticket_url_internal
            })

        # Keep full dataframe (with internal ticket URL) and a visible dataframe without internal column
        df_full = pd.DataFrame(excel_data)
        df = df_full.drop(columns=['__ticket_url'])
        version = version.lower().replace('v', '')
        
        if output_path:
            # Ha megadtak egy teljes elérési utat, azt használjuk
            filename = output_path
        else:
            # Ha nem, akkor az alapértelmezett nevet használjuk az aktuális könyvtárban
            filename = f"v{version}_{install_date}.xlsx"

        # Wrap entire Excel generation in try-except to handle permission errors
        while True:
            try:
                writer = pd.ExcelWriter(filename, engine='xlsxwriter')
            except (PermissionError, IOError, OSError) as e:
                self.log(f"Hozzáférés megtagadva a fájlhoz: {filename}")
                self.log(f"A fájl valószínűleg már megnyitva van egy másik programban.")
                
                new_path = filedialog.asksaveasfilename(
                    defaultextension=".xlsx",
                    filetypes=[("Excel fájlok", "*.xlsx")],
                    initialfile=os.path.basename(filename),
                    title="A fájl már megnyitva. Válasszon új nevet vagy helyet!"
                )
                
                if not new_path:
                    raise Exception("Fájl mentése lemondva a felhasználó által.")
                
                filename = new_path
                continue
            
            break

        # Release Notes munkalap létrehozása
        df.to_excel(writer, sheet_name='Release Notes', index=False)

        workbook = writer.book
        worksheet = writer.sheets['Release Notes']

        # DB változások munkalap létrehozása
        db_changes_worksheet = workbook.add_worksheet('DB változások')

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

        # DB változások munkalap fejléc
        db_header_format = workbook.add_format({
            'bold': True,
            'bg_color': DB_CHANGES_HEADER_COLOR,
            'border': 1,
            'text_wrap': True,
            'valign': 'top',
            'align': 'left'
        })
        
        db_changes_worksheet.write(0, 0, 'Verzió', db_header_format)
        db_changes_worksheet.write(0, 1, 'Tábla', db_header_format)
        db_changes_worksheet.write(0, 2, 'Mező', db_header_format)
        db_changes_worksheet.write(0, 3, 'Új mező név', db_header_format)
        db_changes_worksheet.write(0, 4, 'Változás Leírása', db_header_format)
        db_changes_worksheet.write(0, 5, 'Megjegyzés', db_header_format)

        # DB adatok írása
        db_cell_format = workbook.add_format({
            'text_wrap': True,
            'border': 1,
            'valign': 'top'
        })
        # Format for dropped columns (red background)
        db_drop_format = workbook.add_format({
            'text_wrap': True,
            'border': 1,
            'valign': 'top',
            'bg_color': '#FFC7CE'
        })

        row = 1
        version_clean = version.lower().replace('v', '')

        # Loop through all issues and extract DB changes from parsed XML entries
        for issue in issues:
            tid = issue['Ticket ID']

            # If git_data contains parsed changes for this ticket, use them
            if git_data and tid in git_data and isinstance(git_data[tid], list) and git_data[tid]:
                for change in git_data[tid]:
                    change_type = change.get('change_type', '')
                    table_name = change.get('table_name', '')

                    # Determine description and which columns to fill per user spec
                    if change_type == 'addColumn':
                        # Tábla: tableName, Mező: columnName, Új Mezőnév: empty
                        desc = "Mező hozzáadása"
                        t_val = table_name
                        mező_val = change.get('column_name', '')
                        új_mező_val = ''
                    
                    elif change_type == 'renameColumn':
                        # Tábla: tableName, Mező: oldColumnName, Új Mezőnév: newColumnName
                        desc = "Oszlopnév változás"
                        t_val = table_name
                        mező_val = change.get('old_column_name', '')
                        új_mező_val = change.get('new_column_name', '')
                    
                    elif change_type == 'createTable':
                        # Tábla: tableName, Mező: empty, Új Mezőnév: empty
                        desc = "Új tábla létrehozása"
                        t_val = table_name
                        mező_val = ''
                        új_mező_val = ''
                    elif change_type == 'dropColumn':
                        # Tábla: tableName, Mező: columnName, Új Mezőnév: empty; mark as deletion
                        desc = "Mező törlése"
                        t_val = table_name
                        mező_val = change.get('column_name', '')
                        új_mező_val = ''
                    
                    else:
                        desc = change_type
                        t_val = table_name
                        mező_val = ''
                        új_mező_val = ''

                    # Use special formatting for dropped columns
                    write_fmt = db_drop_format if change_type == 'dropColumn' else db_cell_format
                    db_changes_worksheet.write(row, 0, version_clean, write_fmt)
                    db_changes_worksheet.write(row, 1, t_val, write_fmt)
                    db_changes_worksheet.write(row, 2, mező_val, write_fmt)
                    db_changes_worksheet.write(row, 3, új_mező_val, write_fmt)
                    db_changes_worksheet.write(row, 4, desc, write_fmt)
                    db_changes_worksheet.write(row, 5, '', write_fmt)
                    row += 1
                continue

            # No fallback: skip issues with no parsed git XML entries per user request
        
        # Freeze the first row in DB changes worksheet
        db_changes_worksheet.freeze_panes(1, 0)
        
        # DB változások munkalap oszlopszélességek
        for col, width in DB_CHANGES_COLUMN_WIDTHS.items():
            db_changes_worksheet.set_column(f'{col}:{col}', width)

        # Formátumok
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': RELEASE_NOTES_HEADER_COLOR,
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
        for col, width in RELEASE_NOTES_COLUMN_WIDTHS.items():
            worksheet.set_column(f'{col}:{col}', width)

        # Data worksheet oszlopszélességek
        for col, width in DATA_WORKSHEET_COLUMN_WIDTHS.items():
            data_worksheet.set_column(f'{col}:{col}', width)

        # Fejléc formázása a Release Notes munkalapon
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Freeze the first row in Release Notes worksheet
        worksheet.freeze_panes(1, 0)

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

                # Column 1 (index 1) = 'Szállító belső issue' -> display ticket id, link to ticket URL
                if col_num == 1:
                    ticket_url = df_full.loc[row_num, '__ticket_url'] if '__ticket_url' in df_full.columns else None
                    if isinstance(ticket_url, str) and ticket_url.startswith('http'):
                        display_text = cell_value if cell_value else ticket_url
                        worksheet.write_url(row_num + 1, col_num, ticket_url, link_format, display_text)
                        continue
                # Column 2 (index 2) = external links may contain HYPERLINK formulas
                if col_num in [2] and isinstance(cell_value, str) and cell_value.startswith('=HYPERLINK'):
                    worksheet.write_formula(row_num + 1, col_num, cell_value, link_format)
                else:
                    worksheet.write(row_num + 1, col_num, cell_value, cell_format)

        # Close and save the Excel file
        writer.close()
        
        return filename

    def run(self):
        config = self.config_manager.config
        jira_url = config['jira_url']
        jira_pat_token = config['jira_pat_token']
        git_token = config.get('git_token', '')

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

        # Git repository klónozása és DB fájlok keresése
        git_data = {}
        repo_dir = None
        
        if git_token:
            repo_dir = self.clone_repository(git_token)
            if repo_dir:
                self.log("Git repository klónozásra és ekk2 mappák szkennelésre vételezte...")
                for issue in issues:
                    ticket_id = issue['Ticket ID']
                    self.log(f"Szerzett kapcsolódó fájlok: {ticket_id}")
                    related_files = self.scan_ekk2_folder(repo_dir, ticket_id)
                    if related_files:
                        git_data[ticket_id] = related_files
                
                self.log(f"Git scanning befejeződött. {len(git_data)} ticket(s) adatbázis módosítást tartalmaznak.")
            else:
                self.log("Git repository klónozása sikertelen volt. Excel generálás visszaállítandó szűrővel.")
        else:
            self.log("Nincs megadott Git token. Az adatbázis módosítások nem lesznek beolvasva.")

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
                
            filename = self.generate_excel(issues, version, install_date, git_data if git_data else None, output_path)
            self.log(f"Excel fájl sikeresen létrehozva: {filename}")
            
            # Save search URL and version to config for next time
            self.config_manager.config['jira_search_url'] = search_url
            self.config_manager.config['version'] = version
            self.config_manager.save_config(self.config_manager.config)
            
            messagebox.showinfo("Siker", f"Az Excel fájl sikeresen létrehozva: {filename}")
        except Exception as e:
            self.log(f"Hiba történt az Excel generálása során: {str(e)}")
            messagebox.showerror("Hiba", f"Hiba történt az Excel generálása során: {str(e)}")
        finally:
            # Git repository takarítás
            def _on_rm_error(func, path, exc_info):
                # Clear read-only flag and retry; small retry loop for transient locks
                try:
                    os.chmod(path, stat.S_IWRITE)
                except Exception:
                    pass
                for _ in range(3):
                    try:
                        func(path)
                        return
                    except Exception:
                        time.sleep(0.3)
                # Final attempt: try chmod then func
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception as e:
                    self.log(f"Hiba az ideiglenes Git repository eltávolítása során: {str(e)}")

            if repo_dir and os.path.exists(repo_dir):
                try:
                    shutil.rmtree(repo_dir, onerror=_on_rm_error)
                    self.log("Ideiglenes Git repository eltávolítva.")
                except Exception as e:
                    self.log(f"Hiba az ideiglenes Git repository eltávolítása során: {str(e)}")

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