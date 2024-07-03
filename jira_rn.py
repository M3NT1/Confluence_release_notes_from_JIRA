import requests
import html
import os
import json
import base64
import re
import time
import threading
from urllib.parse import urlparse, parse_qs
from jira import JIRA, JIRAError
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext

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

class GUIApp:
    def __init__(self, root, config_manager):
        self.root = root
        self.config_manager = config_manager
        self.root.title("Confluence Release Notes Generator")

        # Input fields
        self.url_label = tk.Label(root, text="JIRA keresési URL:")
        self.url_label.pack()
        self.url_entry = tk.Entry(root, width=50)
        self.url_entry.pack()

        self.version_label = tk.Label(root, text="Verziószám:")
        self.version_label.pack()
        self.version_entry = tk.Entry(root, width=20)
        self.version_entry.pack()

        # Output field
        self.output_text = scrolledtext.ScrolledText(root, width=100, height=20)
        self.output_text.pack()

        # Submit button
        self.submit_button = tk.Button(root, text="Generálás", command=self.run_thread)
        self.submit_button.pack()

        # Load configuration
        if not self.config_manager.load_config():
            self.ask_for_credentials()

    def ask_for_credentials(self):
        credentials = {}
        credentials['jira_url'] = simpledialog.askstring("JIRA URL", "Add meg a JIRA URL-t:", initialvalue="https://jira.ulyssys.hu")
        credentials['confluence_url'] = simpledialog.askstring("Confluence URL", "Add meg a Confluence URL-t:", initialvalue="https://confluence.ulyssys.hu")
        credentials['confluence_api_token'] = simpledialog.askstring("Confluence API token","Add meg a Confluence API tokent:")
        credentials['confluence_page_id'] = simpledialog.askstring("Confluence Page ID","Add meg a Confluence Page ID-t:")
        credentials['jira_pat_token'] = simpledialog.askstring("JIRA PAT token","Add meg a JIRA Personal Access tokent:")

        self.config_manager.save_config(credentials)

    def log(self, message):
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.root.update()

    def run_thread(self):
        thread = threading.Thread(target=self.run)
        thread.start()

    def run(self):
        config = self.config_manager.config
        jira_url = config['jira_url']
        confluence_url = config['confluence_url']
        confluence_api_token = config['confluence_api_token']
        confluence_page_id = config['confluence_page_id']
        jira_pat_token = config['jira_pat_token']

        search_url = self.url_entry.get()
        version = self.version_entry.get()

        query_or_filter, is_filter = extract_query_from_url(search_url)
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

        table = generate_release_notes_table(issues, self.log)
        update_confluence_page(confluence_url, confluence_api_token, confluence_page_id, version, table, self.log)

        self.log("A Confluence oldal frissítése sikeresen befejeződött.")
        messagebox.showinfo("Siker", "A Confluence oldal frissítése sikeresen befejeződött.")

def connect_to_jira(jira_url, pat_token, log):
    try:
        jira = JIRA(server=jira_url.rstrip('/'), token_auth=pat_token)
        jira.myself()  # Csatlakozás tesztelése
        log("Sikeresen csatlakozva a JIRA-hoz!")
        return jira
    except JIRAError as e:
        log(f"Sikertelen csatlakozás a JIRA-hoz: {e.text}")
        return None

def extract_web_links(issue):
    web_links = []
    if hasattr(issue.fields, 'issuelinks'):
        for link in issue.fields.issuelinks:
            if hasattr(link, 'object'):
                web_link = link.object
                if hasattr(web_link, 'url'):
                    url_ = html.unescape(web_link.url)
                    if is_valid_domain(url_):
                        web_links.append(f"<a href='{html.escape(web_link.url)}'>{html.escape(web_link.url)}</a>")
    return web_links

def extract_remotelinks(jira, issue_key):
    try:
        remotelinks = jira.remote_links(issue_key)
        links = [f"<a href='{html.escape(link.object.url)}'>{html.escape(link.object.url)}</a>"
                 for link in remotelinks if
                 hasattr(link, 'object') and hasattr(link.object, 'url') and is_valid_domain(link.object.url)]
        return links
    except JIRAError as e:
        print(f"Failed to fetch remote links for issue {issue_key}: {e.text}")
        return []

def is_valid_domain(url):
    return urlparse(url).netloc.endswith(("projekt.nak.hu", "rt5.nak.hu"))

def fetch_jira_issues(jira, jql_query, is_filter, jira_url, log):
    try:
        start_time = time.time()
        if is_filter:
            issues = jira.search_issues(f'filter={jql_query}', maxResults=False)
        else:
            issues = jira.search_issues(jql_query, maxResults=False)

        issue_data = []
        for idx, issue in enumerate(issues):
            # Verzió információ mező kezelése
            version_info = getattr(issue.fields, 'customfield_13240', None)
            if version_info is None or version_info.strip() in ['-', '–', '_', '—'] or len(version_info.strip()) <= 3:
                version_info_html = "<span style='color:red'><strong>KITÖLTENDŐ!!!</strong></span>"
            else:
                version_info_html = html.escape(version_info.strip())

            # Belső hivatkozások kigyűjtése csak issue linkekből
            all_links = []

            # Belső linkek kigyűjtése issue linkekből
            for link in issue.fields.issuelinks:
                if hasattr(link, 'outwardIssue'):
                    outward_issue = link.outwardIssue
                    external_link = f"{jira_url}/browse/{outward_issue.key}"
                    if is_valid_domain(external_link):
                        all_links.append(f"<a href='{html.escape(external_link)}'>{html.escape(outward_issue.key)}</a>")

            # Külső hivatkozások kigyűjtése (Web Link típusú hivatkozások)
            web_links = extract_web_links(issue)
            all_links.extend(web_links)

            # Remote links kigyűjtése
            remote_links = extract_remotelinks(jira, issue.key)
            all_links.extend(remote_links)

            external_links_str = ', '.join(all_links) if all_links else 'N/A'

            issue_info = {
                'Summary': html.escape(issue.fields.summary),
                'Ticket ID': f"<a href='{html.escape(jira_url + '/browse/' + issue.key)}'>{html.escape(issue.key)}</a>",
                'External Links': external_links_str,
                'Version Info': version_info_html,
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

def generate_release_notes_table(issues, log):
    start_time = time.time()
    table_header = (
        '<table><tr><th>Fejlesztés/javítás</th>'
        '<th>Szállító belső issue</th>'
        '<th>Redmine, RT jegy</th>'
        '<th>Megjegyzés</th></tr>'
    )
    table_rows = ''.join([
        f"<tr><td>{issue['Summary']}</td><td>{issue['Ticket ID']}</td><td>{issue['External Links']}</td>"
        f"<td>{issue['Version Info']}</td></tr>"
        for issue in issues
    ])
    table_footer = '</table>'
    total_time = time.time() - start_time
    log(f"Tábla generálása befejeződött {total_time:.2f}s")
    return table_header + table_rows + table_footer

def update_confluence_page(url, confluence_api_token, page_id, version, table, log):
    start_time = time.time()
    get_url = f"{url}/rest/api/content/{page_id}?expand=body.storage,version"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {confluence_api_token}'
    }

    response = requests.get(get_url, headers=headers)
    if not response.ok:
        log(f"Sikertelen oldal tartalom lekérése: {response.status_code} {response.text}")
        return

    page_content = response.json()
    page_version = page_content['version']['number']
    page_body = page_content['body']['storage']['value']

    # Ellenőrizzük, hogy a verzió már létezik-e az oldalon
    version_header = f"<h1>{html.escape(version)}</h1>"
    if version_header in page_body:
        # Frissítsük a meglévő verziót
        new_content = re.sub(
            f'(<h1>{html.escape(version)}</h1>)(.*?)(<h1>|$)',
            f'{version_header}\n{table}\n\\3',  # Így biztosítjuk, hogy a találat többi része is megmaradjon
            page_body,
            flags=re.DOTALL
        )
        log(f"A {html.escape(version)} verzió meglévő szakaszának frissítése.")
    else:
        # Új szakasz hozzáadása
        new_content = f"{page_body}{version_header}\n{table}\n"
        log(f"Új szakasz hozzáadása a {html.escape(version)} verzióhoz.")

    new_version = page_version + 1

    update_url = f"{url}/rest/api/content/{page_id}"
    data = {
        "id": page_id,
        "type": "page",
        "title": page_content['title'],
        "version": {"number": new_version},
        "body": {
            "storage": {
                "value": new_content,
                "representation": "storage"
            }
        }
    }

    update_response = requests.put(update_url, json=data, headers=headers)
    if update_response.ok:
        total_time = time.time() - start_time
        log(f"Confluence oldal frissítése sikeresen befejeződött {total_time:.2f}s")
    else:
        log(f"Sikertelen Confluence oldal frissítés: {update_response.status_code} {update_response.text}")

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
