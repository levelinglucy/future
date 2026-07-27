# assistant_shell_v2.py
# Pythonista local-first Assistant Shell v2
# Sci-fi styled, paste-native lab shell for human + LLM co-development.
# Built for routing artifacts, managing candidates/stable/archive,
# generating packets, and reducing cognitive load.

import ui
import os
import json
import sqlite3
import datetime
import dialogs
import console
from pathlib import Path

APP_DIR = Path(os.path.expanduser('~/Documents'))
DB_PATH = APP_DIR / 'assistant_shell_v2.db'
EXPORT_DIR = APP_DIR / 'AssistantShellExports'
EXPORT_DIR.mkdir(exist_ok=True)

# --- Theme ---------------------------------------------------------

THEME = {
    'bg': '#05070a',
    'panel': '#0b1016',
    'panel_2': '#101823',
    'panel_3': '#0d141d',
    'border': '#223449',
    'text': '#d9f7ff',
    'muted': '#77a8b8',
    'accent': '#6bf7ff',
    'accent_2': '#84ffa6',
    'warn': '#ffd166',
    'danger': '#ff6b8f',
    'shadow': '#09131d',
}

FONT_BODY = ('<system>', 14)
FONT_SMALL = ('<system>', 12)
FONT_TITLE = ('<system-bold>', 22)
FONT_SUBTITLE = ('<system-bold>', 16)
FONT_MONO = ('Menlo', 12)


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat(sep=' ')


def safe_name(text):
    text = (text or 'artifact').strip()
    keep = ''.join(ch if ch.isalnum() or ch in '-_ .' else '_' for ch in text)
    keep = '_'.join(keep.split())
    return keep or 'artifact'


def json_text(obj, pretty=True):
    if pretty:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def detect_extension(artifact_type):
    mapping = {
        'python_file': '.py',
        'patch': '.txt',
        'packet': '.json',
        'bug_report': '.txt',
        'note': '.txt',
        'analysis': '.md',
        'command': '.json',
    }
    return mapping.get(artifact_type, '.txt')


# --- UI helpers ----------------------------------------------------

def panel(frame):
    v = ui.View(frame=frame)
    v.background_color = THEME['panel']
    v.border_width = 1
    v.border_color = THEME['border']
    v.corner_radius = 12
    return v


def section_title(text, frame):
    lbl = ui.Label(frame=frame)
    lbl.text = text
    lbl.font = FONT_SUBTITLE
    lbl.text_color = THEME['accent']
    return lbl


def title_label(text, frame):
    lbl = ui.Label(frame=frame)
    lbl.text = text
    lbl.font = FONT_TITLE
    lbl.text_color = THEME['text']
    return lbl


def make_button(title, x, y, w, h, action):
    b = ui.Button(title=title)
    b.frame = (x, y, w, h)
    b.action = action
    b.tint_color = THEME['accent']
    b.border_width = 1
    b.border_color = THEME['border']
    b.corner_radius = 9
    b.background_color = THEME['panel_2']
    b.font = FONT_BODY
    return b


def style_tf(tf):
    tf.border_width = 1
    tf.border_color = THEME['border']
    tf.corner_radius = 9
    tf.background_color = THEME['panel_2']
    tf.text_color = THEME['text']
    tf.tint_color = THEME['accent']
    tf.font = FONT_BODY
    return tf


def style_tv(tv, mono=False):
    tv.border_width = 1
    tv.border_color = THEME['border']
    tv.corner_radius = 9
    tv.background_color = THEME['panel_2']
    tv.text_color = THEME['text']
    tv.tint_color = THEME['accent']
    tv.font = FONT_MONO if mono else FONT_BODY
    return tv


def style_seg(seg):
    seg.tint_color = THEME['accent']
    seg.background_color = THEME['panel_2']
    return seg


def chip(text, x, y, w=96, color=None):
    lbl = ui.Label(frame=(x, y, w, 22))
    lbl.text = f'  {text}'
    lbl.font = FONT_SMALL
    lbl.text_color = color or THEME['accent']
    lbl.border_width = 1
    lbl.border_color = THEME['border']
    lbl.corner_radius = 9
    lbl.background_color = THEME['panel_3']
    return lbl


# --- Database ------------------------------------------------------

class DB:
    def __init__(self, path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.setup()

    def setup(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT,
                artifact_type TEXT NOT NULL,
                bucket TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT '',
                instructions TEXT DEFAULT '',
                tags_json TEXT DEFAULT '[]',
                meta_json TEXT DEFAULT '{}'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS shell_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT DEFAULT ''
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
        """)
        self.conn.commit()
        self.ensure_defaults()

    def ensure_defaults(self):
        if self.get_setting('version_rail') is None:
            self.set_setting('version_rail', {
                'stable_id': None,
                'candidate_id': None,
                'archive_ids': [],
                'last_export_path': '',
            })
        if self.get_setting('workspace') is None:
            self.set_setting('workspace', {
                'selected_artifact_id': None,
                'active_project': 'default',
                'next_action': 'Paste an artifact into the dock.',
                'status': 'idle',
            })

    # ----- settings/logs ------------------------------------------

    def get_setting(self, key, default=None):
        row = self.conn.execute('SELECT value_json FROM settings WHERE key=?', (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row['value_json'])
        except Exception:
            return default

    def set_setting(self, key, value):
        payload = json.dumps(value, ensure_ascii=False)
        self.conn.execute("""
            INSERT INTO settings (key, value_json)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json
        """, (key, payload))
        self.conn.commit()

    def log(self, message, level='info', details=''):
        self.conn.execute("""
            INSERT INTO shell_logs (created_at, level, message, details)
            VALUES (?, ?, ?, ?)
        """, (now_iso(), level, message, details))
        self.conn.commit()

    def list_logs(self, limit=100):
        return self.conn.execute("""
            SELECT * FROM shell_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    # ----- artifact operations -----------------------------------

    def normalize_tags(self, tags):
        if not tags:
            return []
        if isinstance(tags, str):
            tags = [x.strip() for x in tags.replace('\n', ',').split(',')]
        out = []
        seen = set()
        for t in tags:
            t = (t or '').strip()
            if t and t not in seen:
                out.append(t)
                seen.add(t)
        return out

    def add_artifact(self, title, artifact_type, bucket, content,
                     source='', instructions='', tags=None, meta=None):
        ts = now_iso()
        tags_json = json.dumps(self.normalize_tags(tags), ensure_ascii=False)
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        self.conn.execute("""
            INSERT INTO artifacts (
                created_at, updated_at, title, artifact_type, bucket, content,
                source, instructions, tags_json, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, ts, (title or '').strip(), artifact_type.strip(), bucket.strip(),
            content, (source or '').strip(), (instructions or '').strip(),
            tags_json, meta_json
        ))
        self.conn.commit()
        artifact_id = self.conn.execute('SELECT last_insert_rowid() AS x').fetchone()['x']
        self.log(f'Artifact stored in {bucket}', details=f'id={artifact_id} type={artifact_type}')
        return artifact_id

    def update_artifact(self, artifact_id, title=None, artifact_type=None, bucket=None,
                        content=None, source=None, instructions=None, tags=None, meta=None):
        row = self.get_artifact(artifact_id)
        if not row:
            return False
        current_meta = self.get_artifact_meta(row)
        if meta is not None:
            current_meta.update(meta)
        payload = {
            'title': row['title'] if title is None else title,
            'artifact_type': row['artifact_type'] if artifact_type is None else artifact_type,
            'bucket': row['bucket'] if bucket is None else bucket,
            'content': row['content'] if content is None else content,
            'source': row['source'] if source is None else source,
            'instructions': row['instructions'] if instructions is None else instructions,
            'tags_json': row['tags_json'] if tags is None else json.dumps(self.normalize_tags(tags), ensure_ascii=False),
            'meta_json': json.dumps(current_meta, ensure_ascii=False),
        }
        self.conn.execute("""
            UPDATE artifacts
            SET updated_at=?, title=?, artifact_type=?, bucket=?, content=?, source=?,
                instructions=?, tags_json=?, meta_json=?
            WHERE id=?
        """, (
            now_iso(), payload['title'], payload['artifact_type'], payload['bucket'],
            payload['content'], payload['source'], payload['instructions'],
            payload['tags_json'], payload['meta_json'], int(artifact_id)
        ))
        self.conn.commit()
        return True

    def get_artifact(self, artifact_id):
        if not artifact_id:
            return None
        return self.conn.execute('SELECT * FROM artifacts WHERE id=?', (int(artifact_id),)).fetchone()

    def latest_artifact(self):
        return self.conn.execute('SELECT * FROM artifacts ORDER BY id DESC LIMIT 1').fetchone()

    def list_artifacts(self, bucket=None, query='', limit=300):
        sql = 'SELECT * FROM artifacts'
        clauses = []
        params = []
        if bucket:
            clauses.append('bucket=?')
            params.append(bucket)
        if query.strip():
            q = f'%{query.strip()}%'
            clauses.append('(title LIKE ? OR content LIKE ? OR source LIKE ? OR instructions LIKE ?)')
            params.extend([q, q, q, q])
        if clauses:
            sql += ' WHERE ' + ' AND '.join(clauses)
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def get_artifact_meta(self, row):
        try:
            return json.loads(row['meta_json'] or '{}')
        except Exception:
            return {}

    def get_artifact_tags(self, row):
        try:
            return json.loads(row['tags_json'] or '[]')
        except Exception:
            return []

    def classify_artifact(self, text):
        t = (text or '').strip()
        if not t:
            return 'note'
        if t.startswith('{') and ('"packet_type"' in t or '"project"' in t):
            return 'packet'
        if t.startswith('```') or '*** Begin Patch' in t or 'diff --git' in t:
            return 'patch'
        if 'Traceback (most recent call last)' in t or 'SyntaxError' in t or 'Exception:' in t:
            return 'bug_report'
        if 'def ' in t or 'class ' in t or 'import ' in t or 'if __name__ ==' in t:
            return 'python_file'
        if 'TODO' in t or 'next step' in t.lower() or 'plan' in t.lower():
            return 'analysis'
        return 'note'

    def route_suggestion(self, artifact_type):
        mapping = {
            'python_file': 'candidate',
            'patch': 'candidate',
            'packet': 'packet',
            'bug_report': 'note',
            'analysis': 'note',
            'note': 'inbox',
            'command': 'note',
        }
        return mapping.get(artifact_type, 'inbox')

    def summarize_artifact(self, row, max_len=140):
        if not row:
            return None
        body = (row['content'] or '').replace('\n', ' ').strip()
        if len(body) > max_len:
            body = body[:max_len - 3] + '...'
        return {
            'id': row['id'],
            'title': row['title'] or f'Artifact {row["id"]}',
            'artifact_type': row['artifact_type'],
            'bucket': row['bucket'],
            'summary': body,
            'source': row['source'] or '',
        }

    # ----- version rail -------------------------------------------

    def version_rail(self):
        return self.get_setting('version_rail', {
            'stable_id': None,
            'candidate_id': None,
            'archive_ids': [],
            'last_export_path': '',
        })

    def set_candidate(self, artifact_id):
        rail = self.version_rail()
        rail['candidate_id'] = int(artifact_id)
        self.update_artifact(artifact_id, bucket='candidate')
        self.set_setting('version_rail', rail)
        self.log('Candidate updated', details=f'id={artifact_id}')

    def set_stable_direct(self, artifact_id):
        rail = self.version_rail()
        old_stable = rail.get('stable_id')
        if old_stable and old_stable != artifact_id:
            self.archive_artifact(old_stable, quiet=True)
        rail['stable_id'] = int(artifact_id)
        if rail.get('candidate_id') == int(artifact_id):
            rail['candidate_id'] = None
        self.update_artifact(artifact_id, bucket='stable')
        self.set_setting('version_rail', rail)
        self.log('Stable updated', details=f'id={artifact_id}')

    def promote_candidate_to_stable(self):
        rail = self.version_rail()
        cid = rail.get('candidate_id')
        if not cid:
            return False, 'No candidate selected'
        self.set_stable_direct(cid)
        return True, f'Artifact {cid} promoted to stable'

    def archive_artifact(self, artifact_id, quiet=False):
        rail = self.version_rail()
        aid = int(artifact_id)
        self.update_artifact(aid, bucket='archive')
        arch = rail.setdefault('archive_ids', [])
        if aid not in arch:
            arch.insert(0, aid)
        if rail.get('candidate_id') == aid:
            rail['candidate_id'] = None
        if rail.get('stable_id') == aid:
            rail['stable_id'] = None
        self.set_setting('version_rail', rail)
        if not quiet:
            self.log('Artifact archived', details=f'id={aid}')

    # ----- export / import / packets ------------------------------

    def write_artifact_to_file(self, artifact_id, filename=None):
        row = self.get_artifact(artifact_id)
        if not row:
            return None
        title = row['title'] or f'artifact_{row["id"]}'
        filename = filename or (safe_name(title) + detect_extension(row['artifact_type']))
        path = EXPORT_DIR / filename
        with open(path, 'w', encoding='utf-8') as f:
            f.write(row['content'])
        rail = self.version_rail()
        rail['last_export_path'] = str(path)
        self.set_setting('version_rail', rail)
        self.log('Artifact exported to file', details=str(path))
        return path

    def export_bundle(self):
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        payload = {
            'exported_at': now_iso(),
            'version_rail': self.version_rail(),
            'workspace': self.get_setting('workspace'),
            'artifacts': [dict(r) for r in self.list_artifacts(None, '', 1000)],
            'logs': [dict(r) for r in self.list_logs(250)],
        }
        path = EXPORT_DIR / f'assistant_shell_bundle_{stamp}.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        self.log('Bundle exported', details=str(path))
        return path

    def import_bundle(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        imported = 0
        for a in payload.get('artifacts', []):
            self.add_artifact(
                title=a.get('title', ''),
                artifact_type=a.get('artifact_type', 'note'),
                bucket=a.get('bucket', 'inbox'),
                content=a.get('content', ''),
                source=a.get('source', ''),
                instructions=a.get('instructions', ''),
                tags=a.get('tags_json', []),
                meta=a.get('meta_json', {}),
            )
            imported += 1
        self.log('Bundle imported', details=f'path={filepath} artifacts={imported}')
        return imported

    def build_session_packet(self):
        rail = self.version_rail()
        stable = self.get_artifact(rail.get('stable_id'))
        candidate = self.get_artifact(rail.get('candidate_id'))
        latest = self.latest_artifact()
        workspace = self.get_setting('workspace', {})
        return {
            'packet_type': 'assistant_shell_session',
            'project': 'Assistant Shell',
            'current_time': now_iso(),
            'node_status': workspace.get('status', 'idle'),
            'next_action': workspace.get('next_action', ''),
            'stable': self.summarize_artifact(stable),
            'candidate': self.summarize_artifact(candidate),
            'latest_artifact': self.summarize_artifact(latest),
            'archive_count': len(rail.get('archive_ids', [])),
            'recent_logs': [dict(r) for r in self.list_logs(10)],
        }

    def build_versions_packet(self):
        rail = self.version_rail()
        arch_rows = [self.get_artifact(x) for x in rail.get('archive_ids', [])[:12]]
        return {
            'packet_type': 'assistant_shell_versions',
            'project': 'Assistant Shell',
            'stable': self.summarize_artifact(self.get_artifact(rail.get('stable_id'))),
            'candidate': self.summarize_artifact(self.get_artifact(rail.get('candidate_id'))),
            'archive': [self.summarize_artifact(x) for x in arch_rows if x],
        }

    def build_artifact_packet(self, artifact_id):
        row = self.get_artifact(artifact_id)
        if not row:
            return None
        return {
            'packet_type': 'artifact_detail',
            'project': 'Assistant Shell',
            'artifact': dict(row),
            'tags': self.get_artifact_tags(row),
            'meta': self.get_artifact_meta(row),
        }


# --- Data source ---------------------------------------------------

class ArtifactListDS(object):
    def __init__(self, items, on_select):
        self.items = items
        self.on_select = on_select

    def tableview_number_of_rows(self, tableview, section):
        return len(self.items)

    def tableview_cell_for_row(self, tableview, section, row):
        item = self.items[row]
        cell = ui.TableViewCell('subtitle')
        cell.background_color = THEME['panel']
        title = item['title'] or f'Artifact {item["id"]}'
        cell.text_label.text = title
        cell.text_label.text_color = THEME['text']
        cell.detail_text_label.text = f'#{item["id"]} · {item["artifact_type"]} · {item["bucket"]}'
        cell.detail_text_label.text_color = THEME['muted']
        cell.accessory_type = 'disclosure_indicator'
        return cell

    def tableview_did_select(self, tableview, section, row):
        self.on_select(self.items[row])


# --- Main shell ----------------------------------------------------

class ShellView(ui.View):
    def __init__(self):
        super().__init__()
        self.db = DB(DB_PATH)
        self.name = 'Assistant Shell v2'
        self.background_color = THEME['bg']
        self.current_tab = 'home'
        self.selected_artifact_id = None

        self.topbar = ui.View(frame=(0, 0, self.width, 58))
        self.topbar.flex = 'W'
        self.topbar.background_color = THEME['panel']
        self.add_subview(self.topbar)

        self.title_lbl = ui.Label(frame=(12, 8, 190, 20))
        self.title_lbl.text = 'ASSISTANT SHELL'
        self.title_lbl.font = ('Menlo-Bold', 14)
        self.title_lbl.text_color = THEME['accent']
        self.topbar.add_subview(self.title_lbl)

        self.status_chip = chip('NODE IDLE', 12, 30, 110, THEME['accent_2'])
        self.topbar.add_subview(self.status_chip)

        tab_defs = [
            ('Home', 62),
            ('Dock', 58),
            ('Artifacts', 76),
            ('Versions', 74),
            ('Packets', 68),
            ('Logs', 54),
        ]
        x = 145
        self.tab_buttons = []
        for title, w in tab_defs:
            b = make_button(title, x, 12, w, 32, self.switch_tab)
            b.name = title.lower()
            self.topbar.add_subview(b)
            self.tab_buttons.append(b)
            x += w + 6

        self.home_view = self.build_home_view()
        self.dock_view = self.build_dock_view()
        self.artifacts_view = self.build_artifacts_view()
        self.versions_view = self.build_versions_view()
        self.packets_view = self.build_packets_view()
        self.logs_view = self.build_logs_view()

        for view in [self.home_view, self.dock_view, self.artifacts_view, self.versions_view, self.packets_view, self.logs_view]:
            view.frame = (0, 58, self.width, self.height - 58)
            view.flex = 'WH'
            self.add_subview(view)

        self.show_tab('home')
        self.refresh_all()

    # ----- general -------------------------------------------------

    def layout(self):
        self.topbar.width = self.width
        for view in [self.home_view, self.dock_view, self.artifacts_view, self.versions_view, self.packets_view, self.logs_view]:
            view.frame = (0, 58, self.width, self.height - 58)

    def switch_tab(self, sender):
        self.show_tab(sender.name)

    def show_tab(self, name):
        self.current_tab = name
        views = {
            'home': self.home_view,
            'dock': self.dock_view,
            'artifacts': self.artifacts_view,
            'versions': self.versions_view,
            'packets': self.packets_view,
            'logs': self.logs_view,
        }
        for key, view in views.items():
            view.hidden = key != name
        self.refresh_current()

    def refresh_all(self):
        self.refresh_status_chip()
        self.refresh_home()
        self.refresh_dock_hint()
        self.refresh_artifacts()
        self.refresh_versions()
        self.refresh_packets()
        self.refresh_logs()

    def refresh_current(self):
        self.refresh_status_chip()
        if self.current_tab == 'home':
            self.refresh_home()
        elif self.current_tab == 'dock':
            self.refresh_dock_hint()
        elif self.current_tab == 'artifacts':
            self.refresh_artifacts()
        elif self.current_tab == 'versions':
            self.refresh_versions()
        elif self.current_tab == 'packets':
            self.refresh_packets()
        elif self.current_tab == 'logs':
            self.refresh_logs()

    def refresh_status_chip(self):
        ws = self.db.get_setting('workspace', {})
        status = ws.get('status', 'idle').upper()
        self.status_chip.text = f'  {status}'
        self.status_chip.text_color = THEME['accent_2'] if status in ('IDLE', 'STABLE') else THEME['warn']

    def set_workspace_status(self, status, next_action=None):
        ws = self.db.get_setting('workspace', {})
        ws['status'] = status
        if next_action is not None:
            ws['next_action'] = next_action
        self.db.set_setting('workspace', ws)

    def make_card(self, parent, x, y, w, h, title, accent=None):
        box = panel((x, y, w, h))
        parent.add_subview(box)
        hdr = ui.Label(frame=(12, 8, w - 24, 22))
        hdr.text = title
        hdr.font = FONT_SUBTITLE
        hdr.text_color = accent or THEME['accent']
        box.add_subview(hdr)
        return box

    def artifact_summary_lines(self, row):
        if not row:
            return ['(none)']
        tags = self.db.get_artifact_tags(row)
        summary = (row['content'] or '').replace('\n', ' ').strip()
        if len(summary) > 90:
            summary = summary[:87] + '...'
        out = [
            row['title'] or f'Artifact {row["id"]}',
            f'#{row["id"]} · {row["artifact_type"]} · {row["bucket"]}',
        ]
        if tags:
            out.append('tags: ' + ', '.join(tags[:4]))
        out.append(summary or '(empty)')
        return out

    # ----- home ----------------------------------------------------

    def build_home_view(self):
        return ui.ScrollView(background_color=THEME['bg'])

    def refresh_home(self):
        sv = self.home_view
        for s in list(sv.subviews):
            sv.remove_subview(s)

        rail = self.db.version_rail()
        ws = self.db.get_setting('workspace', {})
        stable = self.db.get_artifact(rail.get('stable_id'))
        candidate = self.db.get_artifact(rail.get('candidate_id'))
        latest = self.db.latest_artifact()

        y = 12
        hdr = title_label('Symbiosis Lab', (12, y, sv.width - 24, 30))
        sv.add_subview(hdr)
        y += 30

        sub = ui.Label(frame=(12, y, sv.width - 24, 18))
        sub.text = 'high-tech local shell for pasted intelligence'
        sub.font = FONT_BODY
        sub.text_color = THEME['muted']
        sv.add_subview(sub)
        y += 28

        quick = self.make_card(sv, 12, y, sv.width - 24, 110, 'Next Move', THEME['accent_2'])
        nx = ui.Label(frame=(12, 38, quick.width - 24, 36))
        nx.text = ws.get('next_action', 'Paste an artifact into the dock.')
        nx.number_of_lines = 2
        nx.font = FONT_BODY
        nx.text_color = THEME['text']
        quick.add_subview(nx)

        quick.add_subview(make_button('Open Dock', 12, 78, 88, 24, self.home_open_dock))
        quick.add_subview(make_button('Copy Session', 108, 78, 96, 24, self.copy_session_packet))
        quick.add_subview(make_button('Export Bundle', 212, 78, 98, 24, self.export_bundle))
        y += 122

        rows = [('Stable Rail', stable), ('Candidate Rail', candidate), ('Latest Ingest', latest)]
        for title, row in rows:
            box = self.make_card(sv, 12, y, sv.width - 24, 108, title)
            lines = self.artifact_summary_lines(row)
            yy = 36
            colors = [THEME['text'], THEME['muted'], THEME['muted'], THEME['text']]
            for i, line in enumerate(lines[:4]):
                lbl = ui.Label(frame=(12, yy, box.width - 24, 18))
                lbl.text = line
                lbl.font = FONT_SMALL if i else FONT_BODY
                lbl.text_color = colors[min(i, len(colors)-1)]
                box.add_subview(lbl)
                yy += 18
            y += 118

        sv.content_size = (sv.width, y + 16)

    def home_open_dock(self, sender):
        self.show_tab('dock')

    # ----- dock / ingest ------------------------------------------

    def build_dock_view(self):
        v = ui.View(background_color=THEME['bg'])

        hdr = title_label('Artifact Dock', (12, 10, 240, 28))
        v.add_subview(hdr)

        v.title_tf = style_tf(ui.TextField(frame=(12, 46, 220, 32)))
        v.title_tf.placeholder = 'Artifact title'
        v.add_subview(v.title_tf)

        v.source_tf = style_tf(ui.TextField(frame=(240, 46, 180, 32)))
        v.source_tf.placeholder = 'Source'
        v.add_subview(v.source_tf)

        v.instructions_tf = style_tf(ui.TextField(frame=(12, 86, 408, 32)))
        v.instructions_tf.placeholder = 'Instruction, e.g. store as candidate / replace stable / save as packet'
        v.add_subview(v.instructions_tf)

        v.tags_tf = style_tf(ui.TextField(frame=(12, 126, 408, 32)))
        v.tags_tf.placeholder = 'Tags (comma-separated)'
        v.add_subview(v.tags_tf)

        v.content_tv = ui.TextView(frame=(12, 168, 408, 208))
        style_tv(v.content_tv, mono=True)
        v.add_subview(v.content_tv)

        v.detect_lbl = ui.Label(frame=(12, 384, 408, 18))
        v.detect_lbl.font = FONT_SMALL
        v.detect_lbl.text_color = THEME['muted']
        v.add_subview(v.detect_lbl)

        v.bucket_seg = ui.SegmentedControl(frame=(12, 412, 320, 32))
        v.bucket_seg.segments = ['inbox', 'candidate', 'stable', 'note', 'packet']
        v.bucket_seg.selected_index = 0
        style_seg(v.bucket_seg)
        v.add_subview(v.bucket_seg)

        v.detect_btn = make_button('Detect', 340, 412, 80, 32, self.detect_artifact)
        v.add_subview(v.detect_btn)

        actions = [
            ('Store', 12, 452, 78, self.store_dock_artifact),
            ('To Candidate', 98, 452, 110, self.store_candidate_shortcut),
            ('To Stable', 216, 452, 90, self.store_stable_shortcut),
            ('Clear', 314, 452, 70, self.clear_dock),
        ]
        for t, x, y, w, fn in actions:
            v.add_subview(make_button(t, x, y, w, 30, fn))

        v.hint_panel = self.make_card(v, 12, 490, 408, 110, 'Digest Suggestion')
        v.hint_text = ui.Label(frame=(12, 36, 384, 56))
        v.hint_text.number_of_lines = 3
        v.hint_text.font = FONT_BODY
        v.hint_text.text_color = THEME['text']
        v.hint_panel.add_subview(v.hint_text)

        return v

    def detect_artifact(self, sender):
        self.refresh_dock_hint()
        console.hud_alert('Artifact scanned')

    def refresh_dock_hint(self):
        text = self.dock_view.content_tv.text.strip()
        if not text:
            self.dock_view.detect_lbl.text = 'Paste a script, patch, packet, note, or bug report.'
            self.dock_view.hint_text.text = 'The dock ingests artifacts, classifies them, and routes them into the shell.'
            return
        kind = self.db.classify_artifact(text)
        suggested_bucket = self.db.route_suggestion(kind)
        self.dock_view.detect_lbl.text = f'Detected: {kind} · suggested bucket: {suggested_bucket}'
        self.dock_view.hint_text.text = (
            f'This looks like {kind}. Suggested destination is {suggested_bucket}. '
            f'You can override the bucket, add tags, or give a routing instruction.'
        )

    def selected_bucket(self):
        seg = self.dock_view.bucket_seg
        return seg.segments[seg.selected_index]

    def clear_dock(self, sender):
        self.dock_view.title_tf.text = ''
        self.dock_view.source_tf.text = ''
        self.dock_view.instructions_tf.text = ''
        self.dock_view.tags_tf.text = ''
        self.dock_view.content_tv.text = ''
        self.refresh_dock_hint()
        self.set_workspace_status('idle', 'Paste an artifact into the dock.')

    def store_dock_artifact(self, sender):
        self._store_dock_artifact(self.selected_bucket())

    def store_candidate_shortcut(self, sender):
        self._store_dock_artifact('candidate')

    def store_stable_shortcut(self, sender):
        self._store_dock_artifact('stable')

    def _store_dock_artifact(self, bucket):
        content = self.dock_view.content_tv.text
        if not content.strip():
            console.hud_alert('Dock is empty', 'error')
            return
        detected = self.db.classify_artifact(content)
        title = self.dock_view.title_tf.text.strip() or f'{detected}_{datetime.datetime.now().strftime("%H%M%S")}'
        instructions = self.dock_view.instructions_tf.text.strip()
        tags = self.dock_view.tags_tf.text
        aid = self.db.add_artifact(
            title=title,
            artifact_type=detected,
            bucket=bucket,
            content=content,
            source=self.dock_view.source_tf.text,
            instructions=instructions,
            tags=tags,
            meta={'detected_type': detected, 'stored_via': 'dock'}
        )
        if bucket == 'candidate':
            self.db.set_candidate(aid)
            self.set_workspace_status('staged', 'Review the candidate rail or promote when ready.')
        elif bucket == 'stable':
            self.db.set_stable_direct(aid)
            self.set_workspace_status('stable', 'Stable rail updated. Consider exporting or backing up.')
        else:
            self.set_workspace_status('idle', f'Artifact #{aid} stored in {bucket}.')
        self.selected_artifact_id = aid
        self.refresh_all()
        console.hud_alert(f'Stored #{aid}')
        self.show_tab('versions')

    # ----- artifacts -----------------------------------------------

    def build_artifacts_view(self):
        v = ui.View(background_color=THEME['bg'])

        hdr = title_label('Artifacts', (12, 10, 200, 28))
        v.add_subview(hdr)

        v.search_tf = style_tf(ui.TextField(frame=(12, 48, 180, 32)))
        v.search_tf.placeholder = 'Search'
        v.search_tf.action = self.refresh_artifacts
        v.add_subview(v.search_tf)

        v.filter_seg = ui.SegmentedControl(frame=(200, 48, 220, 32))
        v.filter_seg.segments = ['all', 'candidate', 'stable', 'archive', 'packet']
        v.filter_seg.selected_index = 0
        v.filter_seg.action = self.refresh_artifacts
        style_seg(v.filter_seg)
        v.add_subview(v.filter_seg)

        v.table = ui.TableView(frame=(12, 90, 218, 420))
        v.add_subview(v.table)

        v.detail = ui.TextView(frame=(238, 90, 182, 340))
        style_tv(v.detail, mono=True)
        v.detail.editable = False
        v.add_subview(v.detail)

        btns = [
            ('Open pkt', 238, 438, 78, self.copy_selected_packet),
            ('Export', 324, 438, 70, self.export_selected_artifact),
            ('Archive', 238, 474, 78, self.archive_selected_artifact),
            ('Cand', 324, 474, 70, self.make_selected_candidate),
        ]
        for t, x, y, w, fn in btns:
            v.add_subview(make_button(t, x, y, w, 30, fn))

        return v

    def refresh_artifacts(self, sender=None):
        q = self.artifacts_view.search_tf.text.strip()
        seg = self.artifacts_view.filter_seg
        bucket = seg.segments[seg.selected_index]
        rows = self.db.list_artifacts(None if bucket == 'all' else bucket, q, 300)
        ds = ArtifactListDS(rows, self.select_artifact)
        self.artifacts_view.table.data_source = ds
        self.artifacts_view.table.delegate = ds
        self.artifacts_view.table.reload()
        if rows:
            self.select_artifact(rows[0])
        else:
            self.artifacts_view.detail.text = '(no artifacts)'

    def select_artifact(self, row):
        self.selected_artifact_id = row['id']
        tags = self.db.get_artifact_tags(row)
        meta = self.db.get_artifact_meta(row)
        text = [
            f'Title: {row["title"] or f"Artifact {row["id"]}"}',
            f'ID: {row["id"]}',
            f'Type: {row["artifact_type"]}',
            f'Bucket: {row["bucket"]}',
            f'Source: {row["source"] or "-"}',
            f'Updated: {row["updated_at"]}',
            f'Tags: {", ".join(tags) if tags else "-"}',
            '',
            'Instructions:',
            row['instructions'] or '-',
            '',
            'Meta:',
            json_text(meta, pretty=True),
            '',
            'Content:',
            row['content'] or '',
        ]
        self.artifacts_view.detail.text = '\n'.join(text)

    def require_selected_artifact(self):
        if not self.selected_artifact_id:
            console.hud_alert('Select an artifact first', 'error')
            return None
        row = self.db.get_artifact(self.selected_artifact_id)
        if not row:
            console.hud_alert('Artifact missing', 'error')
            return None
        return row

    def copy_selected_packet(self, sender):
        row = self.require_selected_artifact()
        if not row:
            return
        packet = self.db.build_artifact_packet(row['id'])
        console.set_clipboard(json_text(packet, pretty=True))
        self.db.log('Artifact packet copied', details=f'id={row["id"]}')
        self.refresh_logs()
        console.hud_alert('Packet copied')

    def export_selected_artifact(self, sender):
        row = self.require_selected_artifact()
        if not row:
            return
        path = self.db.write_artifact_to_file(row['id'])
        if path:
            self.set_workspace_status('idle', f'Exported {path.name}')
            self.refresh_all()
            console.hud_alert('Exported')
            dialogs.share_text(str(path))

    def archive_selected_artifact(self, sender):
        row = self.require_selected_artifact()
        if not row:
            return
        self.db.archive_artifact(row['id'])
        self.set_workspace_status('idle', 'Selected artifact archived.')
        self.refresh_all()
        console.hud_alert('Archived')

    def make_selected_candidate(self, sender):
        row = self.require_selected_artifact()
        if not row:
            return
        self.db.set_candidate(row['id'])
        self.set_workspace_status('staged', 'Selected artifact set as candidate.')
        self.refresh_all()
        console.hud_alert('Candidate set')

    # ----- versions ------------------------------------------------

    def build_versions_view(self):
        return ui.ScrollView(background_color=THEME['bg'])

    def refresh_versions(self):
        sv = self.versions_view
        for s in list(sv.subviews):
            sv.remove_subview(s)

        rail = self.db.version_rail()
        stable = self.db.get_artifact(rail.get('stable_id'))
        candidate = self.db.get_artifact(rail.get('candidate_id'))
        archive_rows = [self.db.get_artifact(x) for x in rail.get('archive_ids', [])[:10]]
        archive_rows = [x for x in archive_rows if x]

        y = 12
        for title, row, accent in [
            ('Stable Rail', stable, THEME['accent_2']),
            ('Candidate Rail', candidate, THEME['accent']),
        ]:
            box = self.make_card(sv, 12, y, sv.width - 24, 132, title, accent)
            lines = self.artifact_summary_lines(row)
            yy = 36
            colors = [THEME['text'], THEME['muted'], THEME['muted'], THEME['text']]
            for i, line in enumerate(lines[:4]):
                lbl = ui.Label(frame=(12, yy, box.width - 24, 18))
                lbl.text = line
                lbl.font = FONT_SMALL if i else FONT_BODY
                lbl.text_color = colors[min(i, len(colors)-1)]
                box.add_subview(lbl)
                yy += 18

            if row:
                btn_open = make_button('Open', 12, 98, 58, 24, self.version_open)
                btn_open.artifact_id = row['id']
                box.add_subview(btn_open)

                btn_export = make_button('Export', 76, 98, 68, 24, self.version_export)
                btn_export.artifact_id = row['id']
                box.add_subview(btn_export)

                if title == 'Candidate Rail':
                    promote = make_button('Promote', 150, 98, 78, 24, self.promote_candidate)
                    box.add_subview(promote)
                    archive = make_button('Archive', 234, 98, 76, 24, self.version_archive)
                    archive.artifact_id = row['id']
                    box.add_subview(archive)
            y += 144

        arc_h = max(110, 46 + len(archive_rows) * 22)
        box = self.make_card(sv, 12, y, sv.width - 24, arc_h, 'Archive')
        if archive_rows:
            yy = 38
            for row in archive_rows[:10]:
                lbl = ui.Label(frame=(12, yy, box.width - 24, 18))
                lbl.text = f'#{row["id"]} · {row["title"] or "Artifact"}'
                lbl.font = FONT_SMALL
                lbl.text_color = THEME['text']
                box.add_subview(lbl)
                yy += 22
        else:
            lbl = ui.Label(frame=(12, 42, box.width - 24, 20))
            lbl.text = '(archive empty)'
            lbl.text_color = THEME['muted']
            lbl.font = FONT_BODY
            box.add_subview(lbl)
        y += arc_h + 12
        sv.content_size = (sv.width, y + 16)

    def version_open(self, sender):
        row = self.db.get_artifact(sender.artifact_id)
        if row:
            self.select_artifact(row)
            self.show_tab('artifacts')

    def version_export(self, sender):
        row = self.db.get_artifact(sender.artifact_id)
        if not row:
            return
        path = self.db.write_artifact_to_file(row['id'])
        if path:
            self.set_workspace_status('idle', f'Exported {path.name}')
            self.refresh_all()
            console.hud_alert('Exported')
            dialogs.share_text(str(path))

    def version_archive(self, sender):
        self.db.archive_artifact(sender.artifact_id)
        self.set_workspace_status('idle', 'Candidate archived.')
        self.refresh_all()
        console.hud_alert('Archived')

    def promote_candidate(self, sender):
        ok, msg = self.db.promote_candidate_to_stable()
        if ok:
            self.set_workspace_status('stable', 'Candidate promoted to stable.')
        self.refresh_all()
        console.hud_alert(msg, 'success' if ok else 'error')

    # ----- packets -------------------------------------------------

    def build_packets_view(self):
        v = ui.View(background_color=THEME['bg'])

        hdr = title_label('Packets', (12, 10, 180, 28))
        v.add_subview(hdr)

        v.kind_seg = ui.SegmentedControl(frame=(12, 48, 220, 32))
        v.kind_seg.segments = ['session', 'versions', 'selected']
        v.kind_seg.selected_index = 0
        v.kind_seg.action = self.refresh_packets
        style_seg(v.kind_seg)
        v.add_subview(v.kind_seg)

        v.copy_btn = make_button('Copy', 240, 48, 70, 32, self.copy_packet_button)
        v.add_subview(v.copy_btn)

        v.save_btn = make_button('Save', 318, 48, 70, 32, self.save_packet_button)
        v.add_subview(v.save_btn)

        v.preview = ui.TextView(frame=(12, 92, 408, 420))
        style_tv(v.preview, mono=True)
        v.preview.editable = False
        v.add_subview(v.preview)

        self.current_packet_text = ''
        return v

    def refresh_packets(self, sender=None):
        seg = self.packets_view.kind_seg
        kind = seg.segments[seg.selected_index]
        payload = None
        if kind == 'session':
            payload = self.db.build_session_packet()
        elif kind == 'versions':
            payload = self.db.build_versions_packet()
        else:
            if self.selected_artifact_id:
                payload = self.db.build_artifact_packet(self.selected_artifact_id)
            else:
                payload = {'packet_type': 'artifact_detail', 'error': 'No artifact selected'}
        self.current_packet_text = json_text(payload, pretty=True)
        self.packets_view.preview.text = self.current_packet_text

    def copy_packet_button(self, sender):
        if not self.current_packet_text:
            self.refresh_packets()
        console.set_clipboard(self.current_packet_text)
        self.db.log('Packet copied from packet bay')
        self.refresh_logs()
        console.hud_alert('Packet copied')

    def save_packet_button(self, sender):
        if not self.current_packet_text:
            self.refresh_packets()
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        seg = self.packets_view.kind_seg
        kind = seg.segments[seg.selected_index]
        path = EXPORT_DIR / f'{kind}_packet_{stamp}.json'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.current_packet_text)
        self.db.log('Packet saved', details=str(path))
        self.refresh_logs()
        console.hud_alert('Packet saved')
        dialogs.share_text(str(path))

    def copy_session_packet(self, sender):
        packet = self.db.build_session_packet()
        text = json_text(packet, pretty=True)
        console.set_clipboard(text)
        self.db.log('Session packet copied')
        self.refresh_logs()
        console.hud_alert('Session packet copied')

    def export_bundle(self, sender):
        path = self.db.export_bundle()
        self.set_workspace_status('idle', f'Bundle exported: {path.name}')
        self.refresh_all()
        console.hud_alert('Bundle exported')
        dialogs.share_text(str(path))

    # ----- logs ----------------------------------------------------

    def build_logs_view(self):
        v = ui.View(background_color=THEME['bg'])

        hdr = title_label('Logs', (12, 10, 160, 28))
        v.add_subview(hdr)

        v.refresh_btn = make_button('Refresh', 340, 10, 80, 32, self.refresh_logs)
        v.add_subview(v.refresh_btn)

        v.text = ui.TextView(frame=(12, 52, 408, 460))
        style_tv(v.text, mono=True)
        v.text.editable = False
        v.add_subview(v.text)

        return v

    def refresh_logs(self, sender=None):
        rows = self.db.list_logs(120)
        lines = []
        for r in rows:
            lines.append(f'[{r["created_at"]}] {r["level"].upper()}  {r["message"]}')
            if r['details']:
                lines.append(f'  {r["details"]}')
            lines.append('')
        self.logs_view.text.text = '\n'.join(lines) if lines else '(no logs yet)'


if __name__ == '__main__':
    ShellView().present('fullscreen')
