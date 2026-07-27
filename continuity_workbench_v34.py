# continuity_workbench_v31.py
# Pythonista local-first Continuity Workbench v3.1
# Added in v3.1:
# - Daily Cockpit
# - Focus system
# - Quick actions
# - Cockpit cards and control-room front page

import ui
import os
import json
import sqlite3
import datetime
import dialogs
import console
from pathlib import Path

APP_DIR = Path(os.path.expanduser('~/Documents'))
DB_PATH = APP_DIR / 'continuity_workbench_v2.db'
EXPORT_DIR = APP_DIR / 'ContinuityExports'
EXPORT_DIR.mkdir(exist_ok=True)


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat(sep=' ')


def safe_name(text):
    text = (text or 'branch').strip()
    keep = ''.join(ch if ch.isalnum() or ch in '-_ ' else '_' for ch in text)
    keep = '_'.join(keep.split())
    return keep or 'branch'


def style_textfield(tf):
    tf.border_width = 1
    tf.corner_radius = 8
    return tf


def set_frame(view, parent):
    view.frame = (0, 56, parent.width, parent.height - 56)
    view.flex = 'WH'


def make_button(title, x, y, w, h, action):
    b = ui.Button(title=title)
    b.frame = (x, y, w, h)
    b.corner_radius = 8
    b.border_width = 1
    b.action = action
    return b


class DB:
    def __init__(self, path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.setup()

    def setup(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT,
                body TEXT NOT NULL,
                branch TEXT,
                state_tag TEXT,
                priority INTEGER DEFAULT 2,
                must_not_lose INTEGER DEFAULT 0,
                paused INTEGER DEFAULT 0,
                links_json TEXT DEFAULT '[]'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                label TEXT,
                note TEXT,
                payload_json TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
        """)
        self.conn.commit()
        self.ensure_entry_meta_json_column()

    def add_entry(self, title, body, branch='', state_tag='', priority=2,
                  must_not_lose=False, paused=False, links=None, meta=None):
        links = links or []
        ts = now_iso()
        meta_json = json.dumps(self.normalize_meta(meta or {}), ensure_ascii=False)
        self.conn.execute("""
            INSERT INTO entries (
                created_at, updated_at, title, body, branch, state_tag,
                priority, must_not_lose, paused, links_json, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, ts, title.strip(), body.strip(), branch.strip(), state_tag.strip(),
            int(priority), int(bool(must_not_lose)), int(bool(paused)),
            json.dumps(links), meta_json
        ))
        self.conn.commit()

    def update_entry(self, entry_id, title, body, branch='', state_tag='', priority=2,
                     must_not_lose=False, paused=False, links=None, meta=None):
        links = links or []
        if meta is None:
            existing = self.get_entry(entry_id)
            if existing:
                meta = self.get_entry_meta(existing)
            else:
                meta = {}
        meta_json = json.dumps(self.normalize_meta(meta), ensure_ascii=False)
        self.conn.execute("""
            UPDATE entries
            SET updated_at=?, title=?, body=?, branch=?, state_tag=?, priority=?,
                must_not_lose=?, paused=?, links_json=?, meta_json=?
            WHERE id=?
        """, (
            now_iso(), title.strip(), body.strip(), branch.strip(), state_tag.strip(),
            int(priority), int(bool(must_not_lose)), int(bool(paused)),
            json.dumps(links), meta_json, int(entry_id)
        ))
        self.conn.commit()

    def delete_entry(self, entry_id):
        self.conn.execute('DELETE FROM entries WHERE id=?', (int(entry_id),))
        rows = self.conn.execute('SELECT id, links_json FROM entries').fetchall()
        for r in rows:
            try:
                links = json.loads(r['links_json'] or '[]')
            except Exception:
                links = []
            new_links = [x for x in links if int(x) != int(entry_id)]
            if new_links != links:
                self.conn.execute(
                    'UPDATE entries SET links_json=?, updated_at=? WHERE id=?',
                    (json.dumps(new_links), now_iso(), int(r['id']))
                )
        self.conn.commit()

    def get_entry(self, entry_id):
        return self.conn.execute('SELECT * FROM entries WHERE id=?', (int(entry_id),)).fetchone()

    def all_entries(self):
        return self.conn.execute('SELECT * FROM entries ORDER BY datetime(updated_at) DESC, id DESC').fetchall()

    def search_entries(self, query='', branch=''):
        sql = 'SELECT * FROM entries'
        clauses = []
        params = []
        if query.strip():
            q = f'%{query.strip()}%'
            clauses.append('(title LIKE ? OR body LIKE ? OR branch LIKE ? OR state_tag LIKE ?)')
            params.extend([q, q, q, q])
        if branch.strip():
            clauses.append('branch = ?')
            params.append(branch.strip())
        if clauses:
            sql += ' WHERE ' + ' AND '.join(clauses)
        sql += ' ORDER BY datetime(updated_at) DESC, id DESC'
        return self.conn.execute(sql, params).fetchall()

    def distinct_branches(self):
        return self.conn.execute("""
            SELECT branch, COUNT(*) as count
            FROM entries
            WHERE TRIM(COALESCE(branch, '')) != ''
            GROUP BY branch
            ORDER BY count DESC, branch COLLATE NOCASE
        """).fetchall()

    def parse_links_text(self, links_text):
        raw = [x.strip() for x in links_text.replace('\n', ',').split(',')]
        out = []
        seen = set()
        for x in raw:
            if not x:
                continue
            if x.isdigit():
                v = int(x)
                if v not in seen:
                    out.append(v)
                    seen.add(v)
        return out

    def linked_entries(self, entry_row):
        try:
            ids = json.loads(entry_row['links_json'] or '[]')
        except Exception:
            ids = []
        out = []
        for eid in ids:
            row = self.get_entry(eid)
            if row:
                out.append(row)
        return out

    def backlinks_for_entry(self, entry_id):
        out = []
        for row in self.all_entries():
            try:
                ids = json.loads(row['links_json'] or '[]')
            except Exception:
                ids = []
            if int(entry_id) in [int(x) for x in ids]:
                out.append(row)
        return out

    def get_setting(self, key, default=None):
        row = self.conn.execute(
            'SELECT value_json FROM settings WHERE key=?',
            (key,)
        ).fetchone()
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

    def clear_setting(self, key):
        self.conn.execute('DELETE FROM settings WHERE key=?', (key,))
        self.conn.commit()

    def get_focus(self):
        return self.get_setting('current_focus', {
            'title': '',
            'entry_id': None,
            'branch': '',
            'note': '',
            'status': 'active'
        })

    def set_focus(self, payload):
        focus = {
            'title': payload.get('title', ''),
            'entry_id': payload.get('entry_id', None),
            'branch': payload.get('branch', ''),
            'note': payload.get('note', ''),
            'status': payload.get('status', 'active')
        }
        self.set_setting('current_focus', focus)

    def clear_focus(self):
        self.clear_setting('current_focus')

    def ensure_entry_meta_json_column(self):
        cols = self.conn.execute("PRAGMA table_info(entries)").fetchall()
        names = [c[1] for c in cols]
        if 'meta_json' not in names:
            self.conn.execute("ALTER TABLE entries ADD COLUMN meta_json TEXT DEFAULT '{}'") 
            self.conn.commit()

    def default_meta(self):
        return {
            'entry_type': 'thought',
            'status': 'open',
            'intent': 'remember',
            'human_notes': '',
            'agent_notes': '',
            'machine_summary': '',
            'next_actions': [],
            'verification_state': 'mixed',
            'symbolic_weight': 2,
            'confidence': 3,
            'due_date': '',
            'recurrence_rrule': '',
            'tz': ''
        }

    def normalize_meta(self, meta):
        base = self.default_meta()
        if not isinstance(meta, dict):
            meta = {}
        out = dict(base)
        out.update(meta)
        if not isinstance(out.get('next_actions'), list):
            out['next_actions'] = []
        for key in ['human_notes', 'agent_notes', 'machine_summary', 'due_date', 'recurrence_rrule', 'tz']:
            if not isinstance(out.get(key), str):
                out[key] = ''
        for key in ['entry_type', 'status', 'intent', 'verification_state']:
            if not isinstance(out.get(key), str) or not out.get(key):
                out[key] = base[key]
        try:
            out['symbolic_weight'] = int(out.get('symbolic_weight', 2))
        except Exception:
            out['symbolic_weight'] = 2
        out['symbolic_weight'] = max(0, min(5, out['symbolic_weight']))
        try:
            out['confidence'] = int(out.get('confidence', 3))
        except Exception:
            out['confidence'] = 3
        out['confidence'] = max(0, min(5, out['confidence']))
        cleaned_actions = []
        for item in out.get('next_actions', []):
            if isinstance(item, str):
                item = item.strip()
                if item:
                    cleaned_actions.append(item)
        out['next_actions'] = cleaned_actions
        return out

    def get_entry_meta(self, row):
        raw = row['meta_json'] if 'meta_json' in row.keys() else '{}'
        try:
            meta = json.loads(raw or '{}')
        except Exception:
            meta = {}
        return self.normalize_meta(meta)

    def actions_text_to_list(self, text):
        lines = [x.strip() for x in (text or '').splitlines()]
        return [x for x in lines if x]

    def meta_to_actions_text(self, meta):
        return '\n'.join(self.normalize_meta(meta).get('next_actions', []))

    def app_version(self):
        return 'v3.4'

    def summarize_entry_for_packet(self, row, max_len=140):
        meta = self.get_entry_meta(row)
        summary = meta.get('machine_summary', '').strip()
        if not summary:
            summary = (row['body'] or '').replace('\n', ' ').strip()
        if len(summary) > max_len:
            summary = summary[:max_len - 3] + '...'
        return {
            'id': row['id'],
            'title': row['title'].strip() if row['title'] else f'Entry {row["id"]}',
            'branch': row['branch'] or '',
            'entry_type': meta['entry_type'],
            'status': meta['status'],
            'priority': int(row['priority']),
            'must_not_lose': bool(row['must_not_lose']),
            'summary': summary
        }

    def top_branches(self, limit=5):
        rows = self.distinct_branches()[:limit]
        return [{'branch': r['branch'], 'count': int(r['count'])} for r in rows]

    def important_entries_for_memory(self, limit=8):
        candidates = []
        for row in self.all_entries():
            meta = self.get_entry_meta(row)
            score = 0
            if row['must_not_lose']:
                score += 5
            score += int(row['priority'])
            if meta['entry_type'] in ('spec', 'anchor', 'memory', 'thread'):
                score += 3
            if meta['status'] in ('active', 'open'):
                score += 1
            candidates.append((score, row))
        candidates.sort(key=lambda x: (-x[0], -x[1]['id']))
        return [self.summarize_entry_for_packet(r) for _, r in candidates[:limit]]

    def packet_json_text(self, payload, compact=True):
        if compact:
            return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def build_session_packet(self, compact=True, assistant_notes='', next_request=''):
        focus = self.get_focus()
        priorities = [self.summarize_entry_for_packet(r) for r in self.get_what_matters(5)]
        resume = [self.summarize_entry_for_packet(r) for r in self.resume_candidates()[:5]]
        packet = {
            'packet_type': 'session_resume',
            'project': 'Continuity Workbench',
            'role': 'local-first shared sandbox for human and AI continuity',
            'current_version': self.app_version(),
            'schema_version': 1,
            'active_modules': [
                'cockpit', 'capture', 'entries', 'branches', 'return',
                'map', 'resume', 'snapshots', 'packets'
            ],
            'focus': focus,
            'current_priorities': priorities,
            'open_issues': [],
            'active_branches': self.top_branches(5),
            'resume_candidates': resume,
            'assistant_notes': [x.strip() for x in assistant_notes.splitlines() if x.strip()],
            'next_request': next_request.strip()
        }
        return packet

    def build_memory_packet(self, compact=True):
        important = self.important_entries_for_memory(10)
        stable_goals = []
        architecture_decisions = []
        anti_regression_notes = []
        for item in important:
            et = item.get('entry_type', '')
            if et in ('spec', 'thread'):
                architecture_decisions.append(item)
            elif et in ('anchor', 'memory'):
                anti_regression_notes.append(item)
            else:
                stable_goals.append(item)
        packet = {
            'packet_type': 'memory_continuity',
            'project': 'Continuity Workbench',
            'schema_version': 1,
            'stable_goals': stable_goals[:5],
            'architecture_decisions': architecture_decisions[:5],
            'naming_conventions': [],
            'shared_rules': [],
            'anti_regression_notes': anti_regression_notes[:5],
            'long_term_direction': [],
            'important_entries': important
        }
        return packet

    def build_update_packet(self, requested_change='', affected_modules=None,
                            constraints=None, migration_notes=None,
                            compatibility_notes=None, desired_output=''):
        packet = {
            'packet_type': 'update_request',
            'project': 'Continuity Workbench',
            'schema_version': 1,
            'current_version': self.app_version(),
            'requested_change': requested_change.strip(),
            'affected_modules': affected_modules or [],
            'constraints': constraints or [],
            'migration_notes': migration_notes or [],
            'compatibility_notes': compatibility_notes or [],
            'desired_output': desired_output.strip()
        }
        return packet

    def focus_from_entry(self, row):
        title = row['title'].strip() if row['title'] else f'Entry {row["id"]}'
        return {
            'title': title,
            'entry_id': row['id'],
            'branch': row['branch'] or '',
            'note': '',
            'status': 'active'
        }

    def get_what_matters(self, limit=5):
        return self.conn.execute("""
            SELECT * FROM entries
            WHERE priority >= 4
            ORDER BY must_not_lose DESC, priority DESC, datetime(updated_at) DESC
            LIMIT ?
        """, (limit,)).fetchall()

    def get_must_keep(self, limit=5):
        return self.conn.execute("""
            SELECT * FROM entries
            WHERE must_not_lose = 1
            ORDER BY priority DESC, datetime(updated_at) DESC
            LIMIT ?
        """, (limit,)).fetchall()

    def get_recent_entries(self, limit=5):
        return self.conn.execute("""
            SELECT * FROM entries
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    def return_bundle(self):
        return {
            'what_matters': self.conn.execute("""
                SELECT * FROM entries
                WHERE priority >= 4
                ORDER BY must_not_lose DESC, priority DESC, datetime(updated_at) DESC
                LIMIT 8
            """).fetchall(),
            'paused': self.conn.execute("""
                SELECT * FROM entries
                WHERE paused = 1
                ORDER BY datetime(updated_at) DESC
                LIMIT 8
            """).fetchall(),
            'must_not_lose': self.conn.execute("""
                SELECT * FROM entries
                WHERE must_not_lose = 1
                ORDER BY priority DESC, datetime(updated_at) DESC
                LIMIT 8
            """).fetchall(),
        }

    def create_snapshot(self, label='', note=''):
        payload = {'created_at': now_iso(), 'entries': [dict(r) for r in self.all_entries()]}
        self.conn.execute("""
            INSERT INTO snapshots (created_at, label, note, payload_json)
            VALUES (?, ?, ?, ?)
        """, (now_iso(), label.strip(), note.strip(), json.dumps(payload, ensure_ascii=False)))
        self.conn.commit()

    def list_snapshots(self):
        return self.conn.execute("""
            SELECT * FROM snapshots
            ORDER BY datetime(created_at) DESC, id DESC
        """).fetchall()

    def get_snapshot(self, snapshot_id):
        return self.conn.execute('SELECT * FROM snapshots WHERE id=?', (int(snapshot_id),)).fetchone()

    def restore_snapshot(self, snapshot_id, mode='replace'):
        snap = self.get_snapshot(snapshot_id)
        if not snap:
            return False
        payload = json.loads(snap['payload_json'])
        entries = payload.get('entries', [])
        if mode == 'replace':
            self.conn.execute('DELETE FROM entries')
        for e in entries:
            links_json = e.get('links_json', '[]')
            if isinstance(links_json, list):
                links_json = json.dumps(links_json)
            self.conn.execute("""
                INSERT INTO entries (
                    created_at, updated_at, title, body, branch, state_tag,
                    priority, must_not_lose, paused, links_json, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                e.get('created_at', now_iso()),
                e.get('updated_at', now_iso()),
                e.get('title', ''),
                e.get('body', ''),
                e.get('branch', ''),
                e.get('state_tag', ''),
                int(e.get('priority', 2)),
                int(bool(e.get('must_not_lose', 0))),
                int(bool(e.get('paused', 0))),
                links_json,
                json.dumps(self.normalize_meta(e.get('meta_json', {})), ensure_ascii=False) if isinstance(e.get('meta_json', {}), dict) else e.get('meta_json', '{}')
            ))
        self.conn.commit()
        return True

    def export_full_vault_json(self):
        payload = {
            'exported_at': now_iso(),
            'entries': [dict(r) for r in self.all_entries()],
            'snapshots': [dict(r) for r in self.list_snapshots()],
        }
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = EXPORT_DIR / f'full_vault_{stamp}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return filename

    def import_full_vault_json(self, filepath, mode='merge'):
        with open(filepath, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        if mode == 'replace':
            self.conn.execute('DELETE FROM entries')
            self.conn.execute('DELETE FROM snapshots')
        for e in payload.get('entries', []):
            links_json = e.get('links_json', '[]')
            if isinstance(links_json, list):
                links_json = json.dumps(links_json)
            self.conn.execute("""
                INSERT INTO entries (
                    created_at, updated_at, title, body, branch, state_tag,
                    priority, must_not_lose, paused, links_json, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                e.get('created_at', now_iso()),
                e.get('updated_at', now_iso()),
                e.get('title', ''),
                e.get('body', ''),
                e.get('branch', ''),
                e.get('state_tag', ''),
                int(e.get('priority', 2)),
                int(bool(e.get('must_not_lose', 0))),
                int(bool(e.get('paused', 0))),
                links_json,
                json.dumps(self.normalize_meta(e.get('meta_json', {})), ensure_ascii=False) if isinstance(e.get('meta_json', {}), dict) else e.get('meta_json', '{}')
            ))
        for s in payload.get('snapshots', []):
            self.conn.execute("""
                INSERT INTO snapshots (created_at, label, note, payload_json)
                VALUES (?, ?, ?, ?)
            """, (
                s.get('created_at', now_iso()),
                s.get('label', ''),
                s.get('note', ''),
                s.get('payload_json', '{}')
            ))
        self.conn.commit()

    def compress_branch(self, branch):
        rows = self.search_entries(branch=branch)
        if not rows:
            return '(no entries found for this branch)'
        must_keep = [r for r in rows if r['must_not_lose']]
        paused = [r for r in rows if r['paused']]
        high = [r for r in rows if r['priority'] >= 4]
        lines = [f'Branch: {branch}', f'Total entries: {len(rows)}', '', 'Most important:']
        if high:
            for r in high[:5]:
                title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
                snippet = (r['body'] or '').replace('\n', ' ').strip()
                lines.append(f'- {title}: {snippet[:140]}')
        else:
            lines.append('- none marked high priority yet')
        lines.extend(['', 'Paused:'])
        if paused:
            for r in paused[:5]:
                title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
                lines.append(f'- {title}')
        else:
            lines.append('- none')
        lines.extend(['', 'Must not lose:'])
        if must_keep:
            for r in must_keep[:5]:
                title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
                lines.append(f'- {title}')
        else:
            lines.append('- none')
        return '\n'.join(lines)

    def resume_candidates(self):
        rows = self.all_entries()
        scored = []
        for r in rows:
            score = 0
            if r['paused']:
                score += 5
            if r['must_not_lose']:
                score += 4
            score += int(r['priority'])
            backlinks = len(self.backlinks_for_entry(r['id']))
            links = len(self.linked_entries(r))
            score += min(links + backlinks, 4)
            meta = self.get_entry_meta(r)
            if meta['status'] == 'done':
                score -= 5
            if meta['status'] == 'active':
                score += 2
            if meta['entry_type'] == 'task':
                score += 1
            if meta['entry_type'] == 'anchor' and r['must_not_lose']:
                score += 1
            scored.append((score, r))
        scored.sort(key=lambda x: (-x[0], -(x[1]["id"])))
        return [r for _, r in scored[:12]]

    def branch_graph_text(self):
        branches = [r['branch'] for r in self.distinct_branches()]
        if not branches:
            return 'No branches yet.'
        lines = ['BRANCH MAP', '']
        for branch in branches:
            rows = self.search_entries(branch=branch)
            linked_branches = {}
            for r in rows:
                for linked in self.linked_entries(r):
                    lb = (linked['branch'] or '').strip()
                    if lb and lb != branch:
                        linked_branches[lb] = linked_branches.get(lb, 0) + 1
            lines.append(f'• {branch} ({len(rows)} entries)')
            if linked_branches:
                for lb, count in sorted(linked_branches.items(), key=lambda kv: (-kv[1], kv[0])):
                    lines.append(f'    -> {lb} ({count} links)')
            else:
                lines.append('    -> no outgoing branch links')
            lines.append('')
        return '\n'.join(lines)

    def entry_graph_text(self, limit=40):
        rows = self.all_entries()[:limit]
        if not rows:
            return 'No entries yet.'
        lines = ['ENTRY MAP', '']
        for r in rows:
            title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
            links = self.linked_entries(r)
            backlinks = self.backlinks_for_entry(r['id'])
            lines.append(f'[{r["id"]}] {title}')
            lines.append(f'    branch={r["branch"] or "-"} priority={r["priority"]} links={len(links)} backlinks={len(backlinks)}')
            if links:
                names = []
                for x in links[:4]:
                    nm = x['title'].strip() if x['title'] else f'Entry {x["id"]}'
                    names.append(f'{x["id"]}:{nm}')
                lines.append('    -> ' + ' | '.join(names))
            if backlinks:
                names = []
                for x in backlinks[:4]:
                    nm = x['title'].strip() if x['title'] else f'Entry {x["id"]}'
                    names.append(f'{x["id"]}:{nm}')
                lines.append('    <- ' + ' | '.join(names))
            lines.append('')
        return '\n'.join(lines)


class EntryForm(ui.View):
    def __init__(self, db, refresh_callback, entry_id=None):
        super().__init__()
        self.db = db
        self.refresh_callback = refresh_callback
        self.entry_id = entry_id
        self.name = 'Entry'
        self.background_color = 'white'

        self.scroll = ui.ScrollView(frame=self.bounds)
        self.scroll.flex = 'WH'
        self.add_subview(self.scroll)

        self.container = ui.View(frame=(0, 0, self.width, 1700))
        self.container.flex = 'W'
        self.scroll.add_subview(self.container)

        y = 12
        self.container.add_subview(ui.Label(frame=(12, y, 90, 24), text='Title'))
        self.title_tf = style_textfield(ui.TextField(frame=(12, y + 24, self.width - 24, 32)))
        self.title_tf.flex = 'W'
        self.container.add_subview(self.title_tf)

        y += 64
        self.container.add_subview(ui.Label(frame=(12, y, 90, 24), text='Branch'))
        self.branch_tf = style_textfield(ui.TextField(frame=(12, y + 24, 140, 32)))
        self.container.add_subview(self.branch_tf)

        self.container.add_subview(ui.Label(frame=(160, y, 90, 24), text='State tag'))
        self.state_tf = style_textfield(ui.TextField(frame=(160, y + 24, 100, 32)))
        self.container.add_subview(self.state_tf)

        self.container.add_subview(ui.Label(frame=(268, y, 70, 24), text='Priority'))
        self.priority_seg = ui.SegmentedControl(frame=(268, y + 24, 160, 32))
        self.priority_seg.segments = ['1', '2', '3', '4', '5']
        self.priority_seg.selected_index = 1
        self.container.add_subview(self.priority_seg)

        y += 72
        self.must_switch = ui.Switch(frame=(12, y, 60, 32))
        self.container.add_subview(self.must_switch)
        self.container.add_subview(ui.Label(frame=(72, y, 140, 32), text='Must not lose'))

        self.paused_switch = ui.Switch(frame=(210, y, 60, 32))
        self.container.add_subview(self.paused_switch)
        self.container.add_subview(ui.Label(frame=(270, y, 100, 32), text='Paused'))

        y += 44
        self.container.add_subview(ui.Label(frame=(12, y, 220, 24), text='Linked entry IDs'))
        self.links_tf = style_textfield(ui.TextField(frame=(12, y + 24, self.width - 24, 32)))
        self.links_tf.flex = 'W'
        self.links_tf.placeholder = 'Example: 4, 12, 19'
        self.container.add_subview(self.links_tf)

        y += 64
        self.container.add_subview(ui.Label(frame=(12, y, 120, 24), text='Body'))
        self.body_tv = ui.TextView(frame=(12, y + 24, self.width - 24, 180))
        self.body_tv.flex = 'WH'
        self.body_tv.border_width = 1
        self.body_tv.corner_radius = 8
        self.body_tv.font = ('<system>', 15)
        self.container.add_subview(self.body_tv)

        self.links_preview = ui.TextView(frame=(12, y + 214, self.width - 24, 70))
        self.links_preview.flex = 'WT'
        self.links_preview.editable = False
        self.links_preview.font = ('<system>', 12)
        self.links_preview.border_width = 1
        self.links_preview.corner_radius = 8
        self.container.add_subview(self.links_preview)

        self.backlinks_preview = ui.TextView(frame=(12, y + 292, self.width - 24, 70))
        self.backlinks_preview.flex = 'WT'
        self.backlinks_preview.editable = False
        self.backlinks_preview.font = ('<system>', 12)
        self.backlinks_preview.border_width = 1
        self.backlinks_preview.corner_radius = 8
        self.container.add_subview(self.backlinks_preview)

        self.sandbox_label = ui.Label(frame=(12, y + 370, self.width - 24, 24), text='Shared Sandbox Fields')
        self.sandbox_label.flex = 'W'
        self.sandbox_label.font = ('<system-bold>', 16)
        self.container.add_subview(self.sandbox_label)

        self.entry_type_tf = style_textfield(ui.TextField(frame=(12, y + 400, 100, 32)))
        self.entry_type_tf.placeholder = 'Type'
        self.container.add_subview(self.entry_type_tf)

        self.status_tf = style_textfield(ui.TextField(frame=(120, y + 400, 100, 32)))
        self.status_tf.placeholder = 'Status'
        self.container.add_subview(self.status_tf)

        self.intent_tf = style_textfield(ui.TextField(frame=(228, y + 400, 100, 32)))
        self.intent_tf.placeholder = 'Intent'
        self.container.add_subview(self.intent_tf)

        self.verification_tf = style_textfield(ui.TextField(frame=(336, y + 400, 100, 32)))
        self.verification_tf.placeholder = 'Verify'
        self.container.add_subview(self.verification_tf)

        self.symbolic_lbl = ui.Label(frame=(12, y + 438, 120, 20), text='Symbolic Weight')
        self.container.add_subview(self.symbolic_lbl)
        self.symbolic_weight_seg = ui.SegmentedControl(frame=(12, y + 460, 210, 32))
        self.symbolic_weight_seg.segments = ['0', '1', '2', '3', '4', '5']
        self.symbolic_weight_seg.selected_index = 2
        self.container.add_subview(self.symbolic_weight_seg)

        self.confidence_lbl = ui.Label(frame=(230, y + 438, 100, 20), text='Confidence')
        self.container.add_subview(self.confidence_lbl)
        self.confidence_seg = ui.SegmentedControl(frame=(230, y + 460, 206, 32))
        self.confidence_seg.segments = ['0', '1', '2', '3', '4', '5']
        self.confidence_seg.selected_index = 3
        self.container.add_subview(self.confidence_seg)

        self.human_notes_lbl = ui.Label(frame=(12, y + 500, 140, 20), text='Human Notes')
        self.container.add_subview(self.human_notes_lbl)
        self.human_notes_tv = ui.TextView(frame=(12, y + 522, self.width - 24, 72))
        self.human_notes_tv.flex = 'W'
        self.human_notes_tv.border_width = 1
        self.human_notes_tv.corner_radius = 8
        self.human_notes_tv.font = ('<system>', 12)
        self.container.add_subview(self.human_notes_tv)

        self.agent_notes_lbl = ui.Label(frame=(12, y + 602, 140, 20), text='Agent Notes')
        self.container.add_subview(self.agent_notes_lbl)
        self.agent_notes_tv = ui.TextView(frame=(12, y + 624, self.width - 24, 72))
        self.agent_notes_tv.flex = 'W'
        self.agent_notes_tv.border_width = 1
        self.agent_notes_tv.corner_radius = 8
        self.agent_notes_tv.font = ('<system>', 12)
        self.container.add_subview(self.agent_notes_tv)

        self.machine_summary_lbl = ui.Label(frame=(12, y + 704, 160, 20), text='Machine Summary')
        self.container.add_subview(self.machine_summary_lbl)
        self.machine_summary_tv = ui.TextView(frame=(12, y + 726, self.width - 24, 72))
        self.machine_summary_tv.flex = 'W'
        self.machine_summary_tv.border_width = 1
        self.machine_summary_tv.corner_radius = 8
        self.machine_summary_tv.font = ('<system>', 12)
        self.container.add_subview(self.machine_summary_tv)

        self.next_actions_lbl = ui.Label(frame=(12, y + 806, 160, 20), text='Next Actions')
        self.container.add_subview(self.next_actions_lbl)
        self.next_actions_tv = ui.TextView(frame=(12, y + 828, self.width - 24, 80))
        self.next_actions_tv.flex = 'W'
        self.next_actions_tv.border_width = 1
        self.next_actions_tv.corner_radius = 8
        self.next_actions_tv.font = ('<system>', 12)
        self.container.add_subview(self.next_actions_tv)

        self.due_date_lbl = ui.Label(frame=(12, y + 920, 120, 20), text='Due Date')
        self.container.add_subview(self.due_date_lbl)

        self.due_date_tf = style_textfield(ui.TextField(frame=(12, y + 942, self.width - 24, 32)))
        self.due_date_tf.placeholder = 'YYYY-MM-DD or YYYY-MM-DD HH:MM'
        self.container.add_subview(self.due_date_tf)

        self.due_date_status_lbl = ui.Label(frame=(12, y + 978, self.width - 24, 18), text='')
        self.due_date_status_lbl.font = ('<system>', 11)
        self.due_date_status_lbl.text_color = '#666'
        self.container.add_subview(self.due_date_status_lbl)

        self.recurrence_lbl = ui.Label(frame=(12, y + 1008, 120, 20), text='Recurrence')
        self.container.add_subview(self.recurrence_lbl)

        self.recurrence_tf = style_textfield(ui.TextField(frame=(12, y + 1030, self.width - 24, 32)))
        self.recurrence_tf.placeholder = 'RRULE:FREQ=WEEKLY'
        self.container.add_subview(self.recurrence_tf)

        self.recurrence_preview_lbl = ui.Label(frame=(12, y + 1066, self.width - 24, 34), text='')
        self.recurrence_preview_lbl.font = ('<system>', 11)
        self.recurrence_preview_lbl.text_color = '#666'
        self.recurrence_preview_lbl.number_of_lines = 2
        self.container.add_subview(self.recurrence_preview_lbl)

        self.tz_lbl = ui.Label(frame=(12, y + 1108, 120, 20), text='Timezone')
        self.container.add_subview(self.tz_lbl)

        self.tz_tf = style_textfield(ui.TextField(frame=(12, y + 1130, self.width - 110, 32)))
        self.tz_tf.placeholder = 'Timezone'
        self.tz_tf.editable = False
        self.container.add_subview(self.tz_tf)

        self.tz_pick_btn = make_button('Pick', self.width - 90, y + 1130, 78, 32, self.pick_timezone)
        self.container.add_subview(self.tz_pick_btn)

        self.save_btn = make_button('Save', 12, self.height - 52, 90, 40, self.save_tapped)
        self.save_btn.flex = 'T'
        self.container.add_subview(self.save_btn)

        self.preview_btn = make_button('Preview', 110, self.height - 52, 90, 40, self.preview_links_tapped)
        self.preview_btn.flex = 'T'
        self.container.add_subview(self.preview_btn)

        self.delete_btn = make_button('Delete', 208, self.height - 52, 90, 40, self.delete_tapped)
        self.delete_btn.flex = 'T'
        self.container.add_subview(self.delete_btn)

        self.cancel_btn = make_button('Close', 306, self.height - 52, 90, 40, self.close_tapped)
        self.cancel_btn.flex = 'T'
        self.container.add_subview(self.cancel_btn)

        self.load_if_needed()

    def layout(self):
        self.scroll.frame = self.bounds
        self.container.width = self.width

        self.title_tf.width = self.width - 24
        self.links_tf.width = self.width - 24
        self.body_tv.width = self.width - 24
        self.body_tv.height = 110
        self.links_preview.width = self.width - 24
        self.links_preview.y = self.body_tv.y + self.body_tv.height + 8
        self.backlinks_preview.width = self.width - 24
        self.backlinks_preview.y = self.links_preview.y + self.links_preview.height + 8

        base_y = self.backlinks_preview.y + self.backlinks_preview.height + 10
        self.sandbox_label.y = base_y
        self.entry_type_tf.y = base_y + 30
        self.status_tf.y = base_y + 30
        self.intent_tf.y = base_y + 30
        self.verification_tf.y = base_y + 30

        self.symbolic_lbl.y = base_y + 68
        self.symbolic_weight_seg.y = base_y + 90
        self.confidence_lbl.y = base_y + 68
        self.confidence_seg.y = base_y + 90

        self.human_notes_lbl.y = base_y + 130
        self.human_notes_tv.y = base_y + 152
        self.human_notes_tv.width = self.width - 24

        self.agent_notes_lbl.y = base_y + 232
        self.agent_notes_tv.y = base_y + 254
        self.agent_notes_tv.width = self.width - 24

        self.machine_summary_lbl.y = base_y + 334
        self.machine_summary_tv.y = base_y + 356
        self.machine_summary_tv.width = self.width - 24

        self.next_actions_lbl.y = base_y + 436
        self.next_actions_tv.y = base_y + 458
        self.next_actions_tv.width = self.width - 24

        self.due_date_lbl.y = base_y + 550
        self.due_date_tf.y = base_y + 572
        self.due_date_tf.width = self.width - 24
        self.due_date_status_lbl.y = base_y + 608
        self.due_date_status_lbl.width = self.width - 24

        self.recurrence_lbl.y = base_y + 638
        self.recurrence_tf.y = base_y + 660
        self.recurrence_tf.width = self.width - 24
        self.recurrence_preview_lbl.y = base_y + 696
        self.recurrence_preview_lbl.width = self.width - 24

        self.tz_lbl.y = base_y + 738
        self.tz_tf.y = base_y + 760
        self.tz_tf.width = self.width - 110
        self.tz_pick_btn.y = base_y + 760
        self.tz_pick_btn.x = self.width - 90

        btn_y = self.tz_tf.y + 50
        for btn in [self.save_btn, self.preview_btn, self.delete_btn, self.cancel_btn]:
            btn.y = btn_y

        self.container.height = btn_y + 80
        self.scroll.content_size = (self.width, self.container.height)

    def load_if_needed(self):
        if not self.entry_id:
            self.delete_btn.hidden = True
            self.links_preview.text = 'Outgoing links preview.'
            self.backlinks_preview.text = 'Backlinks preview.'
            meta = self.db.default_meta()
            self.entry_type_tf.text = meta['entry_type']
            self.status_tf.text = meta['status']
            self.intent_tf.text = meta['intent']
            self.verification_tf.text = meta['verification_state']
            self.symbolic_weight_seg.selected_index = meta['symbolic_weight']
            self.confidence_seg.selected_index = meta['confidence']
            self.human_notes_tv.text = meta['human_notes']
            self.agent_notes_tv.text = meta['agent_notes']
            self.machine_summary_tv.text = meta['machine_summary']
            self.next_actions_tv.text = self.db.meta_to_actions_text(meta)
            self.due_date_tf.text = meta.get('due_date', '')
            self.recurrence_tf.text = meta.get('recurrence_rrule', '')
            self.tz_tf.text = meta.get('tz', '')
            self.validate_due_date()
            self.validate_recurrence()
            return
        row = self.db.get_entry(self.entry_id)
        if not row:
            return
        self.title_tf.text = row['title'] or ''
        self.branch_tf.text = row['branch'] or ''
        self.state_tf.text = row['state_tag'] or ''
        self.priority_seg.selected_index = max(0, min(4, int(row['priority']) - 1))
        self.must_switch.value = bool(row['must_not_lose'])
        self.paused_switch.value = bool(row['paused'])
        self.body_tv.text = row['body'] or ''
        try:
            links = json.loads(row['links_json'] or '[]')
        except Exception:
            links = []
        self.links_tf.text = ', '.join(str(x) for x in links)
        meta = self.db.get_entry_meta(row)
        self.entry_type_tf.text = meta['entry_type']
        self.status_tf.text = meta['status']
        self.intent_tf.text = meta['intent']
        self.verification_tf.text = meta['verification_state']
        self.symbolic_weight_seg.selected_index = meta['symbolic_weight']
        self.confidence_seg.selected_index = meta['confidence']
        self.human_notes_tv.text = meta['human_notes']
        self.agent_notes_tv.text = meta['agent_notes']
        self.machine_summary_tv.text = meta['machine_summary']
        self.next_actions_tv.text = self.db.meta_to_actions_text(meta)
        self.due_date_tf.text = meta.get('due_date', '')
        self.recurrence_tf.text = meta.get('recurrence_rrule', '')
        self.tz_tf.text = meta.get('tz', '')
        self.validate_due_date()
        self.validate_recurrence()
        self.preview_links()

    def preview_links(self):
        ids = self.db.parse_links_text(self.links_tf.text)
        if not ids:
            self.links_preview.text = 'Outgoing: none'
        else:
            lines = ['Outgoing:']
            for eid in ids:
                r = self.db.get_entry(eid)
                if r:
                    title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
                    lines.append(f'{eid}: {title}')
                else:
                    lines.append(f'{eid}: (missing)')
            self.links_preview.text = '\n'.join(lines)
        if self.entry_id:
            backlinks = self.db.backlinks_for_entry(self.entry_id)
            if backlinks:
                lines = ['Backlinks:']
                for r in backlinks[:8]:
                    title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
                    lines.append(f'{r["id"]}: {title}')
                self.backlinks_preview.text = '\n'.join(lines)
            else:
                self.backlinks_preview.text = 'Backlinks: none'
        else:
            self.backlinks_preview.text = 'Backlinks: save first to see these'

    def preview_links_tapped(self, sender):
        self.preview_links()

    def validate_due_date(self):
        text = self.due_date_tf.text.strip()
        if not text:
            self.due_date_status_lbl.text = ''
            return True
        try:
            if ' ' in text or 'T' in text:
                datetime.datetime.fromisoformat(text.replace('T', ' '))
            else:
                datetime.date.fromisoformat(text)
            self.due_date_status_lbl.text = 'Valid due date'
            return True
        except Exception:
            self.due_date_status_lbl.text = 'Invalid due date format'
            return False

    def normalize_recurrence_text(self, text):
        text = (text or '').strip()
        if not text:
            return ''
        if not text.upper().startswith('RRULE:'):
            text = 'RRULE:' + text
        return text

    def validate_recurrence(self):
        text = self.normalize_recurrence_text(self.recurrence_tf.text)
        if not text:
            self.recurrence_preview_lbl.text = ''
            return True, ''
        try:
            from dateutil.rrule import rrulestr
            rrulestr(text.replace('RRULE:', ''))
            self.recurrence_preview_lbl.text = 'Valid recurrence rule'
            return True, text
        except Exception:
            self.recurrence_preview_lbl.text = 'Invalid recurrence rule'
            return False, text

    def pick_timezone(self, sender):
        choices = [
            'UTC',
            'Europe/London',
            'Europe/Berlin',
            'America/New_York',
            'America/Los_Angeles',
            'Asia/Tokyo',
            'Australia/Sydney'
        ]
        choice = dialogs.list_dialog('Pick timezone', choices)
        if choice:
            self.tz_tf.text = choice

    def save_tapped(self, sender):
        body = self.body_tv.text.strip()
        if not body:
            console.hud_alert('Body is empty', 'error')
            return
        links = self.db.parse_links_text(self.links_tf.text)

        if not self.validate_due_date():
            console.hud_alert('Fix due date first', 'error')
            return

        recurrence_ok, normalized_recurrence = self.validate_recurrence()
        if not recurrence_ok:
            console.hud_alert('Fix recurrence first', 'error')
            return

        meta = {
            'entry_type': self.entry_type_tf.text.strip() or 'thought',
            'status': self.status_tf.text.strip() or 'open',
            'intent': self.intent_tf.text.strip() or 'remember',
            'human_notes': self.human_notes_tv.text.strip(),
            'agent_notes': self.agent_notes_tv.text.strip(),
            'machine_summary': self.machine_summary_tv.text.strip(),
            'next_actions': self.db.actions_text_to_list(self.next_actions_tv.text),
            'verification_state': self.verification_tf.text.strip() or 'mixed',
            'symbolic_weight': self.symbolic_weight_seg.selected_index,
            'confidence': self.confidence_seg.selected_index,
            'due_date': self.due_date_tf.text.strip(),
            'recurrence_rrule': normalized_recurrence,
            'tz': self.tz_tf.text.strip(),
        }
        if self.entry_id:
            self.db.update_entry(
                self.entry_id, self.title_tf.text.strip(), body,
                self.branch_tf.text.strip(), self.state_tf.text.strip(),
                self.priority_seg.selected_index + 1,
                self.must_switch.value, self.paused_switch.value, links, meta=meta
            )
            console.hud_alert('Updated')
        else:
            self.db.add_entry(
                self.title_tf.text.strip(), body,
                self.branch_tf.text.strip(), self.state_tf.text.strip(),
                self.priority_seg.selected_index + 1,
                self.must_switch.value, self.paused_switch.value, links, meta=meta
            )
            console.hud_alert('Saved')
        self.refresh_callback()
        self.close()

    def delete_tapped(self, sender):
        if not self.entry_id:
            return
        ok = console.alert('Delete entry?', 'This cannot be undone.', 'Delete', 'Cancel', hide_cancel_button=False)
        if ok == 1:
            self.db.delete_entry(self.entry_id)
            self.refresh_callback()
            console.hud_alert('Deleted')
            self.close()

    def close_tapped(self, sender):
        self.close()


class EntriesDataSource(object):
    def __init__(self, items, on_select):
        self.items = items
        self.on_select = on_select

    def tableview_number_of_rows(self, tableview, section):
        return len(self.items)

    def tableview_cell_for_row(self, tableview, section, row):
        item = self.items[row]
        cell = ui.TableViewCell('subtitle')
        title = item['title'].strip() if item['title'] else '(untitled)'
        prefix = '★ ' if item['must_not_lose'] else ''
        cell.text_label.text = f'{prefix}{title}'
        try:
            link_count = len(json.loads(item['links_json'] or '[]'))
        except Exception:
            link_count = 0
        snippet = (item['body'] or '').replace('\n', ' ').strip()
        if len(snippet) > 48:
            snippet = snippet[:45] + '...'
        meta = ' / '.join([x for x in [item['branch'], item['state_tag'], f'P{item["priority"]}', f'L{link_count}'] if x])
        cell.detail_text_label.text = f'{meta} — {snippet}' if meta else snippet
        cell.accessory_type = 'disclosure_indicator'
        return cell

    def tableview_did_select(self, tableview, section, row):
        self.on_select(self.items[row])


class SnapshotsDataSource(object):
    def __init__(self, items, on_select):
        self.items = items
        self.on_select = on_select

    def tableview_number_of_rows(self, tableview, section):
        return len(self.items)

    def tableview_cell_for_row(self, tableview, section, row):
        item = self.items[row]
        cell = ui.TableViewCell('subtitle')
        cell.text_label.text = item['label'] or f'Snapshot {item["id"]}'
        note = item['note'] or ''
        if len(note) > 50:
            note = note[:47] + '...'
        cell.detail_text_label.text = f'{item["created_at"]} — {note}'
        cell.accessory_type = 'disclosure_indicator'
        return cell

    def tableview_did_select(self, tableview, section, row):
        self.on_select(self.items[row])


class SimpleListDS(object):
    def __init__(self, items, on_select):
        self.items = items
        self.on_select = on_select

    def tableview_number_of_rows(self, tableview, section):
        return len(self.items)

    def tableview_cell_for_row(self, tableview, section, row):
        item = self.items[row]
        cell = ui.TableViewCell('subtitle')
        title = item['title'].strip() if item['title'] else f'Entry {item["id"]}'
        cell.text_label.text = title
        cell.detail_text_label.text = f'#{item["id"]} / {item["branch"] or "-"} / P{item["priority"]}'
        cell.accessory_type = 'disclosure_indicator'
        return cell

    def tableview_did_select(self, tableview, section, row):
        self.on_select(self.items[row])


class MainView(ui.View):
    def __init__(self):
        super().__init__()
        self.db = DB(DB_PATH)
        self.name = 'Continuity Workbench v3.4'
        self.background_color = 'white'
        self.current_packet_payload = None
        self.current_packet_text = ''
        self.packet_assistant_notes = ''
        self.packet_next_request = ''
        self.packet_update_context = {
            'requested_change': '',
            'affected_modules': [],
            'constraints': [],
            'migration_notes': [],
            'compatibility_notes': [],
            'desired_output': ''
        }


        self.topbar = ui.View(frame=(0, 0, self.width, 56))
        self.topbar.flex = 'W'
        self.add_subview(self.topbar)

        labels = ['Cockpit', 'Capture', 'Entries', 'Branches', 'Return', 'Map', 'Resume', 'Snapshots', 'Packets']
        widths = [70, 70, 68, 74, 66, 54, 66, 66, 68]
        x = 8
        for label, width in zip(labels, widths):
            btn = make_button(label, x, 8, width, 40, self.switch_tab)
            btn.name = label.lower()
            self.topbar.add_subview(btn)
            x += width + 6

        self.cockpit_view = self.build_cockpit_view()
        self.capture_view = self.build_capture_view()
        self.entries_view = self.build_entries_view()
        self.branches_view = self.build_branches_view()
        self.return_view = self.build_return_view()
        self.map_view = self.build_map_view()
        self.resume_view = self.build_resume_view()
        self.snapshots_view = self.build_snapshots_view()
        self.packets_view = self.build_packets_view()

        for v in [self.cockpit_view, self.capture_view, self.entries_view, self.branches_view, self.return_view,
                  self.map_view, self.resume_view, self.snapshots_view, self.packets_view]:
            set_frame(v, self)
            self.add_subview(v)

        self.show_tab('cockpit')
        self.refresh_all()

    def layout(self):
        self.topbar.width = self.width
        for v in [self.cockpit_view, self.capture_view, self.entries_view, self.branches_view, self.return_view,
                  self.map_view, self.resume_view, self.snapshots_view, self.packets_view]:
            set_frame(v, self)

    def switch_tab(self, sender):
        self.show_tab(sender.name)

    def show_tab(self, name):
        views = {
            'cockpit': self.cockpit_view,
            'capture': self.capture_view,
            'entries': self.entries_view,
            'branches': self.branches_view,
            'return': self.return_view,
            'map': self.map_view,
            'resume': self.resume_view,
            'snapshots': self.snapshots_view,
            'packets': self.packets_view,
        }
        for key, view in views.items():
            view.hidden = key != name
        if name == 'cockpit':
            self.refresh_cockpit()
        elif name == 'map':
            self.refresh_map()
        elif name == 'resume':
            self.refresh_resume()
        elif name == 'packets':
            self.refresh_packets_preview()

    def build_cockpit_view(self):
        v = ui.ScrollView(background_color='white')
        v.flex = 'WH'
        return v

    def build_capture_view(self):
        v = ui.View(background_color='white')
        hdr = ui.Label(frame=(12, 10, 320, 24), text='Quick capture')
        hdr.font = ('<system-bold>', 20)
        v.add_subview(hdr)

        v.title_tf = style_textfield(ui.TextField(frame=(12, 42, 360, 32)))
        v.title_tf.placeholder = 'Title (optional)'
        v.title_tf.flex = 'W'
        v.add_subview(v.title_tf)

        v.branch_tf = style_textfield(ui.TextField(frame=(12, 84, 120, 32)))
        v.branch_tf.placeholder = 'Branch'
        v.add_subview(v.branch_tf)

        v.state_tf = style_textfield(ui.TextField(frame=(140, 84, 110, 32)))
        v.state_tf.placeholder = 'State tag'
        v.add_subview(v.state_tf)

        v.priority_seg = ui.SegmentedControl(frame=(260, 84, 150, 32))
        v.priority_seg.segments = ['1', '2', '3', '4', '5']
        v.priority_seg.selected_index = 1
        v.add_subview(v.priority_seg)

        v.must_switch = ui.Switch(frame=(12, 124, 60, 32))
        v.add_subview(v.must_switch)
        v.add_subview(ui.Label(frame=(74, 124, 130, 32), text='Must not lose'))

        v.paused_switch = ui.Switch(frame=(210, 124, 60, 32))
        v.add_subview(v.paused_switch)
        v.add_subview(ui.Label(frame=(270, 124, 110, 32), text='Paused'))

        v.links_tf = style_textfield(ui.TextField(frame=(12, 166, 400, 32)))
        v.links_tf.flex = 'W'
        v.links_tf.placeholder = 'Linked IDs (optional): 4, 12'
        v.add_subview(v.links_tf)

        v.body_tv = ui.TextView(frame=(12, 208, 400, 270))
        v.body_tv.flex = 'WH'
        v.body_tv.font = ('<system>', 16)
        v.body_tv.border_width = 1
        v.body_tv.corner_radius = 8
        v.add_subview(v.body_tv)

        v.save_btn = make_button('Capture entry', 12, 488, 130, 40, self.save_capture)
        v.save_btn.flex = 'T'
        v.add_subview(v.save_btn)
        v.clear_btn = make_button('Clear', 152, 488, 90, 40, self.clear_capture)
        v.clear_btn.flex = 'T'
        v.add_subview(v.clear_btn)
        return v

    def build_entries_view(self):
        v = ui.View(background_color='white')
        v.search_tf = style_textfield(ui.TextField(frame=(12, 12, 180, 32)))
        v.search_tf.placeholder = 'Search text'
        v.search_tf.action = self.refresh_entries
        v.add_subview(v.search_tf)

        v.branch_tf = style_textfield(ui.TextField(frame=(200, 12, 100, 32)))
        v.branch_tf.placeholder = 'Branch'
        v.branch_tf.action = self.refresh_entries
        v.add_subview(v.branch_tf)

        v.search_btn = make_button('Refresh', 308, 12, 70, 32, self.refresh_entries)
        v.add_subview(v.search_btn)
        v.new_btn = make_button('New', 386, 12, 60, 32, self.new_entry)
        v.add_subview(v.new_btn)

        v.table = ui.TableView(frame=(12, 52, 436, 490))
        v.table.flex = 'WH'
        v.add_subview(v.table)
        return v

    def build_branches_view(self):
        v = ui.View(background_color='white')
        hdr = ui.Label(frame=(12, 10, 320, 24), text='Branches')
        hdr.font = ('<system-bold>', 20)
        v.add_subview(hdr)

        v.table = ui.TableView(frame=(12, 42, 190, 470))
        v.table.flex = 'H'
        v.add_subview(v.table)

        v.info = ui.TextView(frame=(210, 42, 238, 290))
        v.info.flex = 'WH'
        v.info.editable = False
        v.info.font = ('<system>', 14)
        v.info.border_width = 1
        v.info.corner_radius = 8
        v.add_subview(v.info)

        v.export_btn = make_button('Compress', 210, 344, 78, 36, self.compress_branch)
        v.add_subview(v.export_btn)
        v.jump_btn = make_button('Open top', 294, 344, 70, 36, self.open_branch_top)
        v.add_subview(v.jump_btn)
        v.current_branch = None
        return v

    def build_return_view(self):
        v = ui.ScrollView(background_color='white')
        v.flex = 'WH'
        return v

    def build_map_view(self):
        v = ui.View(background_color='white')
        v.branch_btn = make_button('Branch map', 12, 12, 92, 32, self.show_branch_map)
        v.add_subview(v.branch_btn)
        v.entry_btn = make_button('Entry map', 112, 12, 82, 32, self.show_entry_map)
        v.add_subview(v.entry_btn)
        v.refresh_btn = make_button('Refresh', 202, 12, 72, 32, self.refresh_map_button)
        v.add_subview(v.refresh_btn)

        v.text = ui.TextView(frame=(12, 52, 436, 490))
        v.text.flex = 'WH'
        v.text.editable = False
        v.text.font = ('Menlo', 11)
        v.text.border_width = 1
        v.text.corner_radius = 8
        v.add_subview(v.text)
        v.mode = 'branch'
        return v

    def build_resume_view(self):
        v = ui.View(background_color='white')
        hdr = ui.Label(frame=(12, 10, 320, 24), text='Resume thread mode')
        hdr.font = ('<system-bold>', 20)
        v.add_subview(hdr)

        v.refresh_btn = make_button('Refresh', 340, 10, 84, 32, self.refresh_resume_button)
        v.add_subview(v.refresh_btn)

        v.table = ui.TableView(frame=(12, 42, 220, 470))
        v.table.flex = 'H'
        v.add_subview(v.table)

        v.info = ui.TextView(frame=(240, 42, 208, 290))
        v.info.flex = 'WH'
        v.info.editable = False
        v.info.font = ('<system>', 13)
        v.info.border_width = 1
        v.info.corner_radius = 8
        v.add_subview(v.info)

        v.open_btn = make_button('Open', 240, 344, 62, 36, self.resume_open_selected)
        v.add_subview(v.open_btn)
        v.unpause_btn = make_button('Unpause', 308, 344, 68, 36, self.resume_unpause_selected)
        v.add_subview(v.unpause_btn)
        v.current_entry_id = None
        return v

    def build_snapshots_view(self):
        v = ui.View(background_color='white')
        v.label_tf = style_textfield(ui.TextField(frame=(12, 12, 150, 32)))
        v.label_tf.placeholder = 'Snapshot label'
        v.add_subview(v.label_tf)

        v.note_tf = style_textfield(ui.TextField(frame=(170, 12, 190, 32)))
        v.note_tf.placeholder = 'Snapshot note'
        v.add_subview(v.note_tf)

        v.make_btn = make_button('Create', 368, 12, 80, 32, self.create_snapshot)
        v.add_subview(v.make_btn)

        v.table = ui.TableView(frame=(12, 52, 220, 490))
        v.table.flex = 'H'
        v.add_subview(v.table)

        v.info = ui.TextView(frame=(240, 52, 208, 240))
        v.info.flex = 'WH'
        v.info.editable = False
        v.info.font = ('<system>', 13)
        v.info.border_width = 1
        v.info.corner_radius = 8
        v.add_subview(v.info)

        v.restore_replace_btn = make_button('Restore replace', 240, 304, 98, 36, self.restore_snapshot_replace)
        v.add_subview(v.restore_replace_btn)
        v.restore_merge_btn = make_button('Restore merge', 344, 304, 98, 36, self.restore_snapshot_merge)
        v.add_subview(v.restore_merge_btn)
        v.export_vault_btn = make_button('Export vault', 240, 350, 98, 36, self.export_vault)
        v.add_subview(v.export_vault_btn)
        v.import_merge_btn = make_button('Import merge', 344, 350, 98, 36, self.import_vault_merge)
        v.add_subview(v.import_merge_btn)
        v.import_replace_btn = make_button('Import replace', 240, 396, 98, 36, self.import_vault_replace)
        v.add_subview(v.import_replace_btn)
        v.current_snapshot_id = None
        return v


    def build_packets_view(self):
        v = ui.View(background_color='white')

        hdr = ui.Label(frame=(12, 10, 320, 24), text='Packet Forge')
        hdr.font = ('<system-bold>', 20)
        v.add_subview(hdr)

        v.type_seg = ui.SegmentedControl(frame=(12, 42, 240, 32))
        v.type_seg.segments = ['Session', 'Memory', 'Update']
        v.type_seg.selected_index = 0
        v.type_seg.action = self.refresh_packets_preview
        v.add_subview(v.type_seg)

        v.format_seg = ui.SegmentedControl(frame=(260, 42, 120, 32))
        v.format_seg.segments = ['Compact', 'Full']
        v.format_seg.selected_index = 0
        v.format_seg.action = self.refresh_packets_preview
        v.add_subview(v.format_seg)

        v.refresh_btn = make_button('Build', 388, 42, 60, 32, self.refresh_packets_preview)
        v.add_subview(v.refresh_btn)

        v.preview = ui.TextView(frame=(12, 84, 436, 390))
        v.preview.flex = 'WH'
        v.preview.editable = False
        v.preview.font = ('Menlo', 11)
        v.preview.border_width = 1
        v.preview.corner_radius = 8
        v.add_subview(v.preview)

        v.copy_btn = make_button('Copy', 12, 486, 70, 36, self.copy_packet_to_clipboard)
        v.add_subview(v.copy_btn)

        v.save_btn = make_button('Save', 90, 486, 70, 36, self.save_packet_to_file)
        v.add_subview(v.save_btn)

        v.update_btn = make_button('Edit fields', 168, 486, 110, 36, self.prompt_update_packet_fields)
        v.add_subview(v.update_btn)

        return v

    def refresh_all(self):
        self.refresh_entries(None)
        self.refresh_branches()
        self.refresh_return()
        self.refresh_map()
        self.refresh_resume()
        self.refresh_snapshots()
        self.refresh_cockpit()
        self.refresh_packets_preview()

    def refresh_cockpit(self):
        sv = self.cockpit_view
        for sub in list(sv.subviews):
            sv.remove_subview(sub)

        y = 12

        title = ui.Label(frame=(12, y, sv.width - 24, 28), text='Daily Cockpit')
        title.flex = 'W'
        title.font = ('<system-bold>', 22)
        sv.add_subview(title)
        y += 32

        subtitle = ui.Label(frame=(12, y, sv.width - 24, 20), text='control room')
        subtitle.flex = 'W'
        subtitle.font = ('<system>', 12)
        subtitle.text_color = '#666'
        sv.add_subview(subtitle)
        y += 28

        y = self.add_focus_card(sv, y)
        y = self.add_quick_actions(sv, y + 8)
        y = self.add_cockpit_section(sv, y + 12, 'What matters now', self.db.get_what_matters(5), mode='matters')
        y = self.add_cockpit_section(sv, y + 8, 'Resume', self.db.resume_candidates()[:5], mode='resume')
        y = self.add_cockpit_section(sv, y + 8, 'Must not lose', self.db.get_must_keep(5), mode='must')
        y = self.add_cockpit_section(sv, y + 8, 'Recent captures', self.db.get_recent_entries(5), mode='recent')

        sv.content_size = (sv.width, y + 20)

    def add_focus_card(self, parent, y):
        focus = self.db.get_focus()
        box = ui.View(frame=(12, y, parent.width - 24, 130))
        box.flex = 'W'
        box.border_width = 1
        box.corner_radius = 8
        parent.add_subview(box)

        hdr = ui.Label(frame=(10, 8, box.width - 20, 22), text="Today's Focus")
        hdr.flex = 'W'
        hdr.font = ('<system-bold>', 17)
        box.add_subview(hdr)

        has_focus = bool(focus and (focus.get('title') or focus.get('entry_id')))

        if not has_focus:
            msg = ui.Label(frame=(10, 38, box.width - 20, 20), text='No focus set yet.')
            msg.flex = 'W'
            msg.font = ('<system>', 14)
            msg.text_color = '#666'
            box.add_subview(msg)

            btn1 = ui.Button(frame=(10, 72, 110, 32), title='Set manual')
            btn1.border_width = 1
            btn1.corner_radius = 8
            btn1.action = self.cockpit_set_focus_manual
            box.add_subview(btn1)

            btn2 = ui.Button(frame=(130, 72, 120, 32), title='From resume')
            btn2.border_width = 1
            btn2.corner_radius = 8
            btn2.action = self.cockpit_set_focus_from_resume
            box.add_subview(btn2)

            return y + 138

        title = ui.Label(frame=(10, 34, box.width - 20, 22), text=focus.get('title', '(untitled focus)'))
        title.flex = 'W'
        title.font = ('<system-bold>', 15)
        box.add_subview(title)

        meta_parts = [focus.get('status', 'active')]
        if focus.get('branch'):
            meta_parts.append(focus.get('branch'))
        if focus.get('entry_id'):
            meta_parts.append(f'entry #{focus.get("entry_id")}')
        meta = ui.Label(frame=(10, 58, box.width - 20, 18), text=' · '.join(meta_parts))
        meta.flex = 'W'
        meta.font = ('<system>', 12)
        meta.text_color = '#555'
        box.add_subview(meta)

        note = focus.get('note', '') or ''
        if note:
            note_lbl = ui.Label(frame=(10, 78, box.width - 20, 18), text=note[:80])
            note_lbl.flex = 'W'
            note_lbl.font = ('<system>', 12)
            box.add_subview(note_lbl)

        buttons = [
            ('Open', 10, self.cockpit_open_focus),
            ('Edit', 76, self.cockpit_set_focus_manual),
            ('Done', 142, self.cockpit_mark_focus_done),
            ('Clear', 208, self.cockpit_clear_focus),
        ]
        for title_text, x, action in buttons:
            btn = ui.Button(frame=(x, 96, 58, 24), title=title_text)
            btn.border_width = 1
            btn.corner_radius = 8
            btn.action = action
            box.add_subview(btn)

        return y + 138

    def add_quick_actions(self, parent, y):
        hdr = ui.Label(frame=(12, y, parent.width - 24, 22), text='Quick actions')
        hdr.flex = 'W'
        hdr.font = ('<system-bold>', 16)
        parent.add_subview(hdr)
        y += 28

        buttons = [
            ('New Capture', 12, y, 100, 32, self.cockpit_new_capture),
            ('Snapshot', 120, y, 90, 32, self.cockpit_snapshot_now),
            ('Set Focus', 218, y, 86, 32, self.cockpit_set_focus_manual),
            ('Resume', 312, y, 64, 32, self.cockpit_open_resume),
            ('Map', 384, y, 54, 32, self.cockpit_open_map),
        ]
        for title, x, yy, w, h, action in buttons:
            btn = make_button(title, x, yy, w, h, action)
            parent.add_subview(btn)
        return y + 40

    def add_cockpit_section(self, parent, y, title, rows, mode='default'):
        hdr = ui.Label(frame=(12, y, parent.width - 24, 24), text=title)
        hdr.flex = 'W'
        hdr.font = ('<system-bold>', 18)
        parent.add_subview(hdr)
        y += 30

        if not rows:
            lbl = ui.Label(frame=(18, y, parent.width - 36, 22), text='(none yet)')
            lbl.text_color = '#666'
            lbl.flex = 'W'
            parent.add_subview(lbl)
            return y + 28

        for row in rows:
            y = self.make_cockpit_entry_card(parent, row, y, mode=mode)
        return y

    def make_cockpit_entry_card(self, parent, row, y, mode='default'):
        box = ui.View(frame=(12, y, parent.width - 24, 92))
        box.flex = 'W'
        box.border_width = 1
        box.corner_radius = 8
        parent.add_subview(box)

        title_text = row['title'].strip() if row['title'] else f'Entry {row["id"]}'
        title_lbl = ui.Label(frame=(10, 8, box.width - 20, 22), text=title_text)
        title_lbl.flex = 'W'
        title_lbl.font = ('<system-bold>', 15)
        box.add_subview(title_lbl)

        links = len(self.db.linked_entries(row))
        backlinks = len(self.db.backlinks_for_entry(row['id']))
        entry_meta = self.db.get_entry_meta(row)
        meta_parts = [entry_meta['entry_type'], entry_meta['status'], row['branch'] or '-', row['state_tag'] or '-', f'P{row["priority"]}', f'out {links}', f'in {backlinks}']
        if row['paused']:
            meta_parts.append('PAUSED')
        if row['must_not_lose']:
            meta_parts.append('KEEP')
        if mode == 'resume':
            reasons = []
            if row['paused']:
                reasons.append('paused')
            if row['must_not_lose']:
                reasons.append('must keep')
            if row['priority'] >= 4:
                reasons.append('high priority')
            if links + backlinks >= 3:
                reasons.append('linked hub')
            if reasons:
                meta_parts.append(', '.join(reasons[:2]))
        meta_lbl = ui.Label(frame=(10, 30, box.width - 20, 18), text=' · '.join([x for x in meta_parts if x and x != '-']))
        meta_lbl.flex = 'W'
        meta_lbl.font = ('<system>', 12)
        meta_lbl.text_color = '#555'
        box.add_subview(meta_lbl)

        snippet = (row['body'] or '').replace('\n', ' ').strip()
        if len(snippet) > 95:
            snippet = snippet[:92] + '...'
        body_lbl = ui.Label(frame=(10, 50, box.width - 20, 18), text=snippet)
        body_lbl.flex = 'W'
        body_lbl.font = ('<system>', 12)
        box.add_subview(body_lbl)

        open_btn = ui.Button(frame=(10, 68, 48, 20), title='Open')
        open_btn.border_width = 1
        open_btn.corner_radius = 6
        open_btn.entry_id = row['id']
        open_btn.action = self.cockpit_open_entry
        box.add_subview(open_btn)

        focus_btn = ui.Button(frame=(64, 68, 50, 20), title='Focus')
        focus_btn.border_width = 1
        focus_btn.corner_radius = 6
        focus_btn.entry_id = row['id']
        focus_btn.action = self.cockpit_set_focus_button
        box.add_subview(focus_btn)

        if mode in ('matters', 'recent', 'must'):
            p_btn = ui.Button(frame=(120, 68, 34, 20), title='+P')
            p_btn.border_width = 1
            p_btn.corner_radius = 6
            p_btn.entry_id = row['id']
            p_btn.action = self.cockpit_bump_priority
            box.add_subview(p_btn)

        if mode in ('matters', 'recent', 'resume'):
            title_text = 'Unpause' if row['paused'] else 'Pause'
            width = 56 if row['paused'] else 46
            pause_btn = ui.Button(frame=(160, 68, width, 20), title=title_text)
            pause_btn.border_width = 1
            pause_btn.corner_radius = 6
            pause_btn.entry_id = row['id']
            pause_btn.action = self.cockpit_toggle_pause
            box.add_subview(pause_btn)

        return y + 100

    def save_capture(self, sender):
        body = self.capture_view.body_tv.text.strip()
        if not body:
            console.hud_alert('Nothing to capture', 'error')
            return
        links = self.db.parse_links_text(self.capture_view.links_tf.text)
        self.db.add_entry(
            self.capture_view.title_tf.text.strip(),
            body,
            self.capture_view.branch_tf.text.strip(),
            self.capture_view.state_tf.text.strip(),
            self.capture_view.priority_seg.selected_index + 1,
            self.capture_view.must_switch.value,
            self.capture_view.paused_switch.value,
            links
        )
        console.hud_alert('Captured')
        self.clear_capture(None)
        self.refresh_all()
        self.show_tab('entries')

    def clear_capture(self, sender):
        self.capture_view.title_tf.text = ''
        self.capture_view.branch_tf.text = ''
        self.capture_view.state_tf.text = ''
        self.capture_view.priority_seg.selected_index = 1
        self.capture_view.must_switch.value = False
        self.capture_view.paused_switch.value = False
        self.capture_view.links_tf.text = ''
        self.capture_view.body_tv.text = ''

    def refresh_entries(self, sender):
        q = self.entries_view.search_tf.text.strip()
        b = self.entries_view.branch_tf.text.strip()
        rows = self.db.search_entries(query=q, branch=b)
        ds = EntriesDataSource(rows, self.open_entry)
        self.entries_view.table.data_source = ds
        self.entries_view.table.delegate = ds
        self.entries_view.table.reload()

    def new_entry(self, sender):
        EntryForm(self.db, self.refresh_all).present('sheet')

    def open_entry(self, row):
        EntryForm(self.db, self.refresh_all, entry_id=row['id']).present('sheet')

    def refresh_branches(self):
        rows = self.db.distinct_branches()
        items = [{'title': r['branch'], 'count': r['count']} for r in rows]

        class BranchDS(object):
            def __init__(self, outer, items):
                self.outer = outer
                self.items = items
            def tableview_number_of_rows(self, tableview, section):
                return len(self.items)
            def tableview_cell_for_row(self, tableview, section, row):
                item = self.items[row]
                cell = ui.TableViewCell('subtitle')
                cell.text_label.text = item['title']
                cell.detail_text_label.text = f'{item["count"]} entries'
                cell.accessory_type = 'disclosure_indicator'
                return cell
            def tableview_did_select(self, tableview, section, row):
                self.outer.select_branch(self.items[row]['title'])

        ds = BranchDS(self, items)
        self.branches_view.table.data_source = ds
        self.branches_view.table.delegate = ds
        self.branches_view.table.reload()
        if self.branches_view.current_branch and any(x['title'] == self.branches_view.current_branch for x in items):
            self.select_branch(self.branches_view.current_branch)
        elif items:
            self.select_branch(items[0]['title'])
        else:
            self.branches_view.current_branch = None
            self.branches_view.info.text = 'No branches yet.'

    def select_branch(self, branch):
        rows = self.db.search_entries(branch=branch)
        self.branches_view.current_branch = branch
        lines = [f'BRANCH: {branch}', '', f'Count: {len(rows)}', '']
        for r in rows[:6]:
            title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
            backlinks = len(self.db.backlinks_for_entry(r['id']))
            links = len(self.db.linked_entries(r))
            lines.append(f'- {title} (P{r["priority"]}, out={links}, in={backlinks})')
        if len(rows) > 6:
            lines += ['', f'...and {len(rows)-6} more']
        self.branches_view.info.text = '\n'.join(lines)

    def compress_branch(self, sender):
        branch = self.branches_view.current_branch
        if not branch:
            console.hud_alert('No branch selected', 'error')
            return
        text = self.db.compress_branch(branch)
        dialogs.text_dialog('Compressed thread', text=text)
        try:
            console.set_clipboard(text)
        except Exception:
            pass
        console.hud_alert('Compressed')

    def open_branch_top(self, sender):
        branch = self.branches_view.current_branch
        if not branch:
            console.hud_alert('No branch selected', 'error')
            return
        rows = self.db.search_entries(branch=branch)
        if rows:
            self.open_entry(rows[0])

    def refresh_return(self):
        sv = self.return_view
        for sub in list(sv.subviews):
            sv.remove_subview(sub)
        bundle = self.db.return_bundle()
        y = 12
        y = self.add_return_section(sv, y, 'What matters most right now', bundle['what_matters'])
        y = self.add_return_section(sv, y + 8, 'What is paused', bundle['paused'])
        y = self.add_return_section(sv, y + 8, 'What must not be lost', bundle['must_not_lose'])
        sv.content_size = (sv.width, y + 20)

    def add_return_section(self, parent, y, title, rows):
        hdr = ui.Label(frame=(12, y, parent.width - 24, 24), text=title)
        hdr.flex = 'W'
        hdr.font = ('<system-bold>', 18)
        parent.add_subview(hdr)
        y += 30
        if not rows:
            lbl = ui.Label(frame=(18, y, parent.width - 36, 22), text='(none yet)')
            lbl.text_color = '#666'
            lbl.flex = 'W'
            parent.add_subview(lbl)
            return y + 28
        for r in rows:
            box = ui.View(frame=(12, y, parent.width - 24, 92))
            box.flex = 'W'
            box.border_width = 1
            box.corner_radius = 8
            parent.add_subview(box)

            title_text = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
            title_lbl = ui.Label(frame=(10, 8, box.width - 70, 22))
            title_lbl.flex = 'W'
            title_lbl.font = ('<system-bold>', 15)
            title_lbl.text = title_text
            box.add_subview(title_lbl)

            links = len(self.db.linked_entries(r))
            backlinks = len(self.db.backlinks_for_entry(r['id']))
            entry_meta = self.db.get_entry_meta(r)
            meta = ' · '.join([
                x for x in [
                    entry_meta['entry_type'],
                    entry_meta['status'],
                    r['branch'] or '',
                    r['state_tag'] or '',
                    f'P{r["priority"]}',
                    f'out {links}',
                    f'in {backlinks}',
                    'MUST KEEP' if r['must_not_lose'] else '',
                    'PAUSED' if r['paused'] else '',
                ] if x
            ])
            meta_lbl = ui.Label(frame=(10, 30, box.width - 20, 18))
            meta_lbl.flex = 'W'
            meta_lbl.font = ('<system>', 12)
            meta_lbl.text_color = '#555'
            meta_lbl.text = meta
            box.add_subview(meta_lbl)

            snippet = (r['body'] or '').replace('\n', ' ').strip()
            if len(snippet) > 110:
                snippet = snippet[:107] + '...'
            body_lbl = ui.Label(frame=(10, 50, box.width - 20, 20))
            body_lbl.flex = 'W'
            body_lbl.font = ('<system>', 13)
            body_lbl.text = snippet
            box.add_subview(body_lbl)

            btn = ui.Button(frame=(box.width - 58, 8, 48, 24), title='Open')
            btn.border_width = 1
            btn.corner_radius = 8
            btn.entry_id = r['id']
            btn.action = self.open_from_button
            box.add_subview(btn)
            y += 100
        return y

    def open_from_button(self, sender):
        row = self.db.get_entry(sender.entry_id)
        if row:
            self.open_entry(row)

    def show_branch_map(self, sender):
        self.map_view.mode = 'branch'
        self.refresh_map()

    def show_entry_map(self, sender):
        self.map_view.mode = 'entry'
        self.refresh_map()

    def refresh_map_button(self, sender):
        self.refresh_map()

    def refresh_map(self):
        if self.map_view.mode == 'entry':
            self.map_view.text.text = self.db.entry_graph_text()
        else:
            self.map_view.text.text = self.db.branch_graph_text()

    def refresh_resume_button(self, sender):
        self.refresh_resume()

    def refresh_resume(self):
        items = self.db.resume_candidates()
        ds = SimpleListDS(items, self.select_resume_candidate)
        self.resume_view.table.data_source = ds
        self.resume_view.table.delegate = ds
        self.resume_view.table.reload()
        if items:
            self.select_resume_candidate(items[0])
        else:
            self.resume_view.info.text = 'No entries yet.'
            self.resume_view.current_entry_id = None

    def select_resume_candidate(self, row):
        self.resume_view.current_entry_id = row['id']
        title = row['title'].strip() if row['title'] else f'Entry {row["id"]}'
        links = self.db.linked_entries(row)
        backlinks = self.db.backlinks_for_entry(row['id'])
        lines = [
            f'Title: {title}',
            f'ID: {row["id"]}',
            f'Branch: {row["branch"] or "-"}',
            f'State: {row["state_tag"] or "-"}',
            f'Priority: {row["priority"]}',
            f'Paused: {"yes" if row["paused"] else "no"}',
            f'Must keep: {"yes" if row["must_not_lose"] else "no"}',
            f'Outgoing links: {len(links)}',
            f'Backlinks: {len(backlinks)}',
            '',
            'Snippet:',
            (row['body'] or '')[:250]
        ]
        self.resume_view.info.text = '\n'.join(lines)

    def resume_open_selected(self, sender):
        eid = self.resume_view.current_entry_id
        if eid:
            row = self.db.get_entry(eid)
            if row:
                self.open_entry(row)

    def resume_unpause_selected(self, sender):
        eid = self.resume_view.current_entry_id
        if not eid:
            console.hud_alert('Select an entry first', 'error')
            return
        row = self.db.get_entry(eid)
        if not row:
            return
        try:
            links = json.loads(row['links_json'] or '[]')
        except Exception:
            links = []
        self.db.update_entry(
            row['id'], row['title'] or '', row['body'] or '',
            row['branch'] or '', row['state_tag'] or '',
            int(row['priority']), bool(row['must_not_lose']), False, links,
            meta=self.db.get_entry_meta(row)
        )
        self.refresh_all()
        console.hud_alert('Unpaused')

    def create_snapshot(self, sender):
        self.db.create_snapshot(self.snapshots_view.label_tf.text.strip(), self.snapshots_view.note_tf.text.strip())
        self.snapshots_view.label_tf.text = ''
        self.snapshots_view.note_tf.text = ''
        self.refresh_snapshots()
        console.hud_alert('Snapshot saved')

    def refresh_snapshots(self):
        rows = self.db.list_snapshots()
        ds = SnapshotsDataSource(rows, self.select_snapshot)
        self.snapshots_view.table.data_source = ds
        self.snapshots_view.table.delegate = ds
        self.snapshots_view.table.reload()
        if not rows:
            self.snapshots_view.info.text = 'No snapshots yet.'
            self.snapshots_view.current_snapshot_id = None

    def select_snapshot(self, row):
        self.snapshots_view.current_snapshot_id = row['id']
        payload = json.loads(row['payload_json'])
        count = len(payload.get('entries', []))
        label = row['label'] or f'Snapshot {row["id"]}'
        note = row['note'] or ''
        self.snapshots_view.info.text = '\n'.join([
            f'Label: {label}',
            f'Created: {row["created_at"]}',
            f'Entries inside: {count}',
            '',
            f'Note: {note}',
        ])

    def restore_snapshot_replace(self, sender):
        sid = self.snapshots_view.current_snapshot_id
        if not sid:
            console.hud_alert('Select a snapshot first', 'error')
            return
        ok = console.alert('Restore snapshot', 'Replace current entries?', 'Replace', 'Cancel', hide_cancel_button=False)
        if ok == 1:
            self.db.restore_snapshot(sid, mode='replace')
            self.refresh_all()
            console.hud_alert('Snapshot restored')

    def restore_snapshot_merge(self, sender):
        sid = self.snapshots_view.current_snapshot_id
        if not sid:
            console.hud_alert('Select a snapshot first', 'error')
            return
        self.db.restore_snapshot(sid, mode='merge')
        self.refresh_all()
        console.hud_alert('Snapshot merged')

    def export_vault(self, sender):
        path = self.db.export_full_vault_json()
        console.hud_alert('Vault exported')
        dialogs.share_text(str(path))

    def import_vault_merge(self, sender):
        path = dialogs.text_dialog('Import vault merge', text='')
        if not path:
            return
        try:
            self.db.import_full_vault_json(path.strip(), mode='merge')
            self.refresh_all()
            console.hud_alert('Vault merged')
        except Exception as e:
            console.hud_alert('Import failed', 'error')
            self.snapshots_view.info.text = f'Import failed:\n{e}'

    def import_vault_replace(self, sender):
        path = dialogs.text_dialog('Import vault replace', text='')
        if not path:
            return
        ok = console.alert('Import replace', 'This will replace current vault contents.', 'Replace', 'Cancel', hide_cancel_button=False)
        if ok == 1:
            try:
                self.db.import_full_vault_json(path.strip(), mode='replace')
                self.refresh_all()
                console.hud_alert('Vault replaced')
            except Exception as e:
                console.hud_alert('Import failed', 'error')
                self.snapshots_view.info.text = f'Import failed:\n{e}'


    def refresh_packets_preview(self, sender=None):
        type_idx = self.packets_view.type_seg.selected_index
        compact = self.packets_view.format_seg.selected_index == 0

        if type_idx == 0:
            payload = self.db.build_session_packet(
                compact=compact,
                assistant_notes=self.packet_assistant_notes,
                next_request=self.packet_next_request
            )
        elif type_idx == 1:
            payload = self.db.build_memory_packet(compact=compact)
        else:
            ctx = self.packet_update_context
            payload = self.db.build_update_packet(
                requested_change=ctx['requested_change'],
                affected_modules=ctx['affected_modules'],
                constraints=ctx['constraints'],
                migration_notes=ctx['migration_notes'],
                compatibility_notes=ctx['compatibility_notes'],
                desired_output=ctx['desired_output']
            )

        self.current_packet_payload = payload
        self.current_packet_text = self.db.packet_json_text(payload, compact=compact)
        self.packets_view.preview.text = self.current_packet_text

    def copy_packet_to_clipboard(self, sender):
        if not self.current_packet_text:
            self.refresh_packets_preview()
        try:
            console.set_clipboard(self.current_packet_text)
            console.hud_alert('Packet copied')
        except Exception:
            console.hud_alert('Copy failed', 'error')

    def save_packet_to_file(self, sender):
        if not self.current_packet_payload:
            self.refresh_packets_preview()

        type_idx = self.packets_view.type_seg.selected_index
        prefix = ['session_packet', 'memory_packet', 'update_packet'][type_idx]
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = EXPORT_DIR / f'{prefix}_{stamp}.json'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.current_packet_text)

        console.hud_alert('Packet saved')
        dialogs.share_text(str(path))

    def prompt_session_packet_fields(self, sender=None):
        notes = dialogs.text_dialog('Assistant notes', text=self.packet_assistant_notes or '')
        if notes is None:
            return
        req = dialogs.text_dialog('Next request', text=self.packet_next_request or '')
        if req is None:
            return
        self.packet_assistant_notes = notes
        self.packet_next_request = req
        self.refresh_packets_preview()

    def prompt_update_packet_fields(self, sender):
        type_idx = self.packets_view.type_seg.selected_index

        if type_idx == 0:
            self.prompt_session_packet_fields()
            return

        if type_idx == 1:
            console.hud_alert('Memory packet has no manual fields')
            return

        requested_change = dialogs.text_dialog(
            'Requested change',
            text=self.packet_update_context.get('requested_change', '')
        )
        if requested_change is None:
            return

        affected_modules = dialogs.text_dialog(
            'Affected modules (comma-separated)',
            text=', '.join(self.packet_update_context.get('affected_modules', []))
        )
        if affected_modules is None:
            return

        constraints = dialogs.text_dialog(
            'Constraints (one per line)',
            text='\n'.join(self.packet_update_context.get('constraints', []))
        )
        if constraints is None:
            return

        desired_output = dialogs.text_dialog(
            'Desired output',
            text=self.packet_update_context.get('desired_output', '')
        )
        if desired_output is None:
            return

        self.packet_update_context = {
            'requested_change': requested_change.strip(),
            'affected_modules': [x.strip() for x in affected_modules.split(',') if x.strip()],
            'constraints': [x.strip() for x in constraints.splitlines() if x.strip()],
            'migration_notes': [],
            'compatibility_notes': [],
            'desired_output': desired_output.strip()
        }

        self.refresh_packets_preview()

    # Cockpit actions

    def cockpit_new_capture(self, sender):
        self.show_tab('capture')

    def cockpit_open_resume(self, sender):
        self.show_tab('resume')

    def cockpit_open_map(self, sender):
        self.show_tab('map')

    def cockpit_snapshot_now(self, sender):
        label = 'quick_' + datetime.datetime.now().strftime('%Y-%m-%d_%H%M')
        self.db.create_snapshot(label=label, note='Created from cockpit')
        self.refresh_all()
        console.hud_alert('Snapshot saved')

    def cockpit_set_focus_manual(self, sender):
        current = self.db.get_focus() or {}
        title = dialogs.text_dialog('Set focus title', text=current.get('title', '') or '')
        if title is None:
            return
        note = dialogs.text_dialog('Set focus note', text=current.get('note', '') or '')
        if note is None:
            note = current.get('note', '') or ''
        self.db.set_focus({
            'title': title.strip(),
            'entry_id': None,
            'branch': current.get('branch', ''),
            'note': note.strip(),
            'status': current.get('status', 'active') or 'active'
        })
        self.refresh_all()
        console.hud_alert('Focus set')

    def cockpit_set_focus_from_row(self, row):
        self.db.set_focus(self.db.focus_from_entry(row))
        self.refresh_all()
        console.hud_alert('Focus updated')

    def cockpit_set_focus_button(self, sender):
        row = self.db.get_entry(sender.entry_id)
        if row:
            self.cockpit_set_focus_from_row(row)

    def cockpit_set_focus_from_resume(self, sender):
        rows = self.db.resume_candidates()
        if not rows:
            console.hud_alert('No resume candidates', 'error')
            return
        self.cockpit_set_focus_from_row(rows[0])

    def cockpit_clear_focus(self, sender):
        self.db.clear_focus()
        self.refresh_all()
        console.hud_alert('Focus cleared')

    def cockpit_mark_focus_done(self, sender):
        focus = self.db.get_focus()
        if not focus:
            return
        focus['status'] = 'done'
        self.db.set_focus(focus)
        self.refresh_all()
        console.hud_alert('Focus marked done')

    def cockpit_open_focus(self, sender):
        focus = self.db.get_focus()
        eid = focus.get('entry_id') if focus else None
        if eid:
            row = self.db.get_entry(eid)
            if row:
                self.open_entry(row)

    def cockpit_open_entry(self, sender):
        row = self.db.get_entry(sender.entry_id)
        if row:
            self.open_entry(row)

    def cockpit_bump_priority(self, sender):
        row = self.db.get_entry(sender.entry_id)
        if not row:
            return
        try:
            links = json.loads(row['links_json'] or '[]')
        except Exception:
            links = []
        new_priority = min(5, int(row['priority']) + 1)
        self.db.update_entry(
            row['id'], row['title'] or '', row['body'] or '',
            row['branch'] or '', row['state_tag'] or '',
            new_priority, bool(row['must_not_lose']), bool(row['paused']), links,
            meta=self.db.get_entry_meta(row)
        )
        self.refresh_all()
        console.hud_alert(f'Priority {new_priority}')

    def cockpit_toggle_pause(self, sender):
        row = self.db.get_entry(sender.entry_id)
        if not row:
            return
        try:
            links = json.loads(row['links_json'] or '[]')
        except Exception:
            links = []
        new_paused = not bool(row['paused'])
        self.db.update_entry(
            row['id'], row['title'] or '', row['body'] or '',
            row['branch'] or '', row['state_tag'] or '',
            int(row['priority']), bool(row['must_not_lose']), new_paused, links,
            meta=self.db.get_entry_meta(row)
        )
        self.refresh_all()
        console.hud_alert('Paused' if new_paused else 'Unpaused')


if __name__ == '__main__':
    MainView().present('fullscreen')
