# continuity_workbench_v2.py
# Pythonista local-first Continuity Workbench v2
# Added:
# - linked entries
# - snapshots
# - full vault export/import
# - branch compression helper

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


class DB:
    def __init__(self, path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
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
        c.execute('CREATE INDEX IF NOT EXISTS idx_entries_created ON entries(created_at DESC)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_entries_branch ON entries(branch)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_entries_state ON entries(state_tag)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_created ON snapshots(created_at DESC)')
        self.conn.commit()

    def add_entry(self, title, body, branch='', state_tag='', priority=2,
                  must_not_lose=False, paused=False, links=None):
        links = links or []
        ts = now_iso()
        self.conn.execute("""
            INSERT INTO entries (
                created_at, updated_at, title, body, branch, state_tag,
                priority, must_not_lose, paused, links_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, ts, title.strip(), body.strip(), branch.strip(), state_tag.strip(),
            int(priority), int(bool(must_not_lose)), int(bool(paused)),
            json.dumps(links)
        ))
        self.conn.commit()

    def update_entry(self, entry_id, title, body, branch='', state_tag='', priority=2,
                     must_not_lose=False, paused=False, links=None):
        links = links or []
        self.conn.execute("""
            UPDATE entries
            SET updated_at=?, title=?, body=?, branch=?, state_tag=?, priority=?,
                must_not_lose=?, paused=?, links_json=?
            WHERE id=?
        """, (
            now_iso(), title.strip(), body.strip(), branch.strip(), state_tag.strip(),
            int(priority), int(bool(must_not_lose)), int(bool(paused)),
            json.dumps(links), int(entry_id)
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

    def compress_branch(self, branch):
        rows = self.search_entries(branch=branch)
        if not rows:
            return '(no entries found for this branch)'
        must_keep = [r for r in rows if r['must_not_lose']]
        paused = [r for r in rows if r['paused']]
        high = [r for r in rows if r['priority'] >= 4]
        lines = [
            f'Branch: {branch}',
            f'Total entries: {len(rows)}',
            '',
            'Most important:'
        ]
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

    def create_snapshot(self, label='', note=''):
        payload = {
            'created_at': now_iso(),
            'entries': [dict(r) for r in self.all_entries()]
        }
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
                    priority, must_not_lose, paused, links_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                links_json
            ))
        self.conn.commit()
        return True

    def export_branch_json(self, branch):
        rows = self.search_entries(branch=branch)
        payload = [dict(r) for r in rows]
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = EXPORT_DIR / f'{safe_name(branch)}_{stamp}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return filename

    def export_branch_markdown(self, branch):
        rows = self.search_entries(branch=branch)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = EXPORT_DIR / f'{safe_name(branch)}_{stamp}.md'
        parts = [f'# Branch Export: {branch}', '']
        for r in rows:
            title = r['title'].strip() or f'Entry {r["id"]}'
            parts.append(f'## {title}')
            parts.append(f'- ID: {r["id"]}')
            parts.append(f'- Created: {r["created_at"]}')
            parts.append(f'- Updated: {r["updated_at"]}')
            parts.append(f'- Branch: {r["branch"] or "(none)"}')
            parts.append(f'- State: {r["state_tag"] or "(none)"}')
            parts.append(f'- Priority: {r["priority"]}')
            parts.append(f'- Must not lose: {"yes" if r["must_not_lose"] else "no"}')
            parts.append(f'- Paused: {"yes" if r["paused"] else "no"}')
            parts.append(f'- Links: {r["links_json"]}')
            parts.append('')
            parts.append(r['body'])
            parts.append('')
            parts.append('---')
            parts.append('')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(parts))
        return filename

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
                    priority, must_not_lose, paused, links_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                links_json
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


class EntryForm(ui.View):
    def __init__(self, db, refresh_callback, entry_id=None):
        super().__init__()
        self.db = db
        self.refresh_callback = refresh_callback
        self.entry_id = entry_id
        self.name = 'Entry'
        self.background_color = 'white'

        y = 12
        self.add_subview(ui.Label(frame=(12, y, 90, 24), text='Title'))
        self.title_tf = ui.TextField(frame=(12, y + 24, self.width - 24, 32))
        self.title_tf.flex = 'W'
        self.title_tf.border_style = ui.BORDER_ROUNDED
        self.add_subview(self.title_tf)

        y += 64
        self.add_subview(ui.Label(frame=(12, y, 90, 24), text='Branch'))
        self.branch_tf = ui.TextField(frame=(12, y + 24, 140, 32))
        self.branch_tf.border_style = ui.BORDER_ROUNDED
        self.add_subview(self.branch_tf)

        self.add_subview(ui.Label(frame=(160, y, 90, 24), text='State tag'))
        self.state_tf = ui.TextField(frame=(160, y + 24, 100, 32))
        self.state_tf.border_style = ui.BORDER_ROUNDED
        self.add_subview(self.state_tf)

        self.add_subview(ui.Label(frame=(268, y, 70, 24), text='Priority'))
        self.priority_seg = ui.SegmentedControl(frame=(268, y + 24, 160, 32))
        self.priority_seg.segments = ['1', '2', '3', '4', '5']
        self.priority_seg.selected_index = 1
        self.add_subview(self.priority_seg)

        y += 72
        self.must_switch = ui.Switch(frame=(12, y, 60, 32))
        self.add_subview(self.must_switch)
        self.add_subview(ui.Label(frame=(72, y, 140, 32), text='Must not lose'))

        self.paused_switch = ui.Switch(frame=(210, y, 60, 32))
        self.add_subview(self.paused_switch)
        self.add_subview(ui.Label(frame=(270, y, 100, 32), text='Paused'))

        y += 44
        self.add_subview(ui.Label(frame=(12, y, 220, 24), text='Linked entry IDs'))
        self.links_tf = ui.TextField(frame=(12, y + 24, self.width - 24, 32))
        self.links_tf.flex = 'W'
        self.links_tf.border_style = ui.BORDER_ROUNDED
        self.links_tf.placeholder = 'Example: 4, 12, 19'
        self.add_subview(self.links_tf)

        y += 64
        self.add_subview(ui.Label(frame=(12, y, 120, 24), text='Body'))
        self.body_tv = ui.TextView(frame=(12, y + 24, self.width - 24, 220))
        self.body_tv.flex = 'WH'
        self.body_tv.border_width = 1
        self.body_tv.corner_radius = 8
        self.body_tv.font = ('<system>', 15)
        self.add_subview(self.body_tv)

        self.linked_preview = ui.TextView(frame=(12, y + 252, self.width - 24, 90))
        self.linked_preview.flex = 'WT'
        self.linked_preview.editable = False
        self.linked_preview.font = ('<system>', 13)
        self.linked_preview.border_width = 1
        self.linked_preview.corner_radius = 8
        self.add_subview(self.linked_preview)

        self.save_btn = make_button('Save', 12, self.height - 52, 90, 40, self.save_tapped)
        self.save_btn.flex = 'T'
        self.add_subview(self.save_btn)

        self.links_btn = make_button('Preview links', 110, self.height - 52, 110, 40, self.preview_links_tapped)
        self.links_btn.flex = 'T'
        self.add_subview(self.links_btn)

        self.delete_btn = make_button('Delete', 228, self.height - 52, 90, 40, self.delete_tapped)
        self.delete_btn.flex = 'T'
        self.add_subview(self.delete_btn)

        self.cancel_btn = make_button('Close', 326, self.height - 52, 90, 40, self.close_tapped)
        self.cancel_btn.flex = 'T'
        self.add_subview(self.cancel_btn)

        self.load_if_needed()

    def layout(self):
        self.title_tf.width = self.width - 24
        self.links_tf.width = self.width - 24
        self.body_tv.width = self.width - 24
        self.body_tv.height = self.height - 390
        self.linked_preview.width = self.width - 24
        self.linked_preview.y = self.body_tv.y + self.body_tv.height + 8
        self.linked_preview.height = 90
        btn_y = self.height - 52
        for btn in [self.save_btn, self.links_btn, self.delete_btn, self.cancel_btn]:
            btn.y = btn_y

    def load_if_needed(self):
        if not self.entry_id:
            self.delete_btn.hidden = True
            self.linked_preview.text = 'Linked entries preview appears here.'
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
        self.preview_links()

    def preview_links(self):
        ids = self.db.parse_links_text(self.links_tf.text)
        if not ids:
            self.linked_preview.text = 'No linked entries.'
            return
        lines = []
        for eid in ids:
            r = self.db.get_entry(eid)
            if r:
                title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
                lines.append(f'{eid}: {title}')
            else:
                lines.append(f'{eid}: (missing)')
        self.linked_preview.text = '\n'.join(lines)

    def preview_links_tapped(self, sender):
        self.preview_links()

    def save_tapped(self, sender):
        body = self.body_tv.text.strip()
        if not body:
            console.hud_alert('Body is empty', 'error')
            return
        links = self.db.parse_links_text(self.links_tf.text)
        title = self.title_tf.text.strip()
        branch = self.branch_tf.text.strip()
        state_tag = self.state_tf.text.strip()
        priority = self.priority_seg.selected_index + 1
        if self.entry_id:
            self.db.update_entry(
                self.entry_id, title, body, branch, state_tag, priority,
                self.must_switch.value, self.paused_switch.value, links
            )
            console.hud_alert('Updated')
        else:
            self.db.add_entry(
                title, body, branch, state_tag, priority,
                self.must_switch.value, self.paused_switch.value, links
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
        if len(snippet) > 52:
            snippet = snippet[:49] + '...'
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


class MainView(ui.View):
    def __init__(self):
        super().__init__()
        self.db = DB(DB_PATH)
        self.name = 'Continuity Workbench v2'
        self.background_color = 'white'

        self.topbar = ui.View(frame=(0, 0, self.width, 56))
        self.topbar.flex = 'W'
        self.add_subview(self.topbar)

        labels = ['Capture', 'Entries', 'Branches', 'Return', 'Snapshots']
        for i, label in enumerate(labels):
            btn = make_button(label, 8 + i * 88, 8, 80, 40, self.switch_tab)
            btn.name = label.lower()
            self.topbar.add_subview(btn)

        self.capture_view = self.build_capture_view()
        self.entries_view = self.build_entries_view()
        self.branches_view = self.build_branches_view()
        self.return_view = self.build_return_view()
        self.snapshots_view = self.build_snapshots_view()

        for v in [self.capture_view, self.entries_view, self.branches_view, self.return_view, self.snapshots_view]:
            set_frame(v, self)
            self.add_subview(v)

        self.show_tab('capture')
        self.refresh_all()

    def layout(self):
        self.topbar.width = self.width
        for v in [self.capture_view, self.entries_view, self.branches_view, self.return_view, self.snapshots_view]:
            set_frame(v, self)

    def switch_tab(self, sender):
        self.show_tab(sender.name)

    def show_tab(self, name):
        views = {
            'capture': self.capture_view,
            'entries': self.entries_view,
            'branches': self.branches_view,
            'return': self.return_view,
            'snapshots': self.snapshots_view,
        }
        for key, view in views.items():
            view.hidden = key != name

    def build_capture_view(self):
        v = ui.View(background_color='white')
        lbl = ui.Label(frame=(12, 10, 320, 24), text='Quick capture')
        lbl.font = ('<system-bold>', 20)
        v.add_subview(lbl)

        v.title_tf = ui.TextField(frame=(12, 42, 360, 32))
        v.title_tf.placeholder = 'Title (optional)'
        v.title_tf.border_style = ui.BORDER_ROUNDED
        v.title_tf.flex = 'W'
        v.add_subview(v.title_tf)

        v.branch_tf = ui.TextField(frame=(12, 84, 120, 32))
        v.branch_tf.placeholder = 'Branch'
        v.branch_tf.border_style = ui.BORDER_ROUNDED
        v.add_subview(v.branch_tf)

        v.state_tf = ui.TextField(frame=(140, 84, 110, 32))
        v.state_tf.placeholder = 'State tag'
        v.state_tf.border_style = ui.BORDER_ROUNDED
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

        v.links_tf = ui.TextField(frame=(12, 166, 400, 32))
        v.links_tf.flex = 'W'
        v.links_tf.placeholder = 'Linked IDs (optional): 4, 12'
        v.links_tf.border_style = ui.BORDER_ROUNDED
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
        v.search_tf = ui.TextField(frame=(12, 12, 180, 32))
        v.search_tf.placeholder = 'Search text'
        v.search_tf.border_style = ui.BORDER_ROUNDED
        v.search_tf.action = self.refresh_entries
        v.add_subview(v.search_tf)

        v.branch_tf = ui.TextField(frame=(200, 12, 100, 32))
        v.branch_tf.placeholder = 'Branch'
        v.branch_tf.border_style = ui.BORDER_ROUNDED
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

        v.export_md_btn = make_button('Export MD', 210, 344, 74, 36, self.export_branch_md)
        v.add_subview(v.export_md_btn)
        v.export_json_btn = make_button('Export JSON', 290, 344, 86, 36, self.export_branch_json)
        v.add_subview(v.export_json_btn)
        v.compress_btn = make_button('Compress', 382, 344, 66, 36, self.compress_branch)
        v.add_subview(v.compress_btn)

        v.current_branch = None
        return v

    def build_return_view(self):
        v = ui.ScrollView(background_color='white')
        v.flex = 'WH'
        return v

    def build_snapshots_view(self):
        v = ui.View(background_color='white')
        v.label_tf = ui.TextField(frame=(12, 12, 150, 32))
        v.label_tf.placeholder = 'Snapshot label'
        v.label_tf.border_style = ui.BORDER_ROUNDED
        v.add_subview(v.label_tf)

        v.note_tf = ui.TextField(frame=(170, 12, 190, 32))
        v.note_tf.placeholder = 'Snapshot note'
        v.note_tf.border_style = ui.BORDER_ROUNDED
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

    def refresh_all(self):
        self.refresh_entries(None)
        self.refresh_branches()
        self.refresh_return()
        self.refresh_snapshots()

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
        self.refresh_branches()
        self.refresh_return()

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
        for r in rows[:8]:
            title = r['title'].strip() if r['title'] else f'Entry {r["id"]}'
            try:
                links = json.loads(r['links_json'] or '[]')
            except Exception:
                links = []
            lines.append(f'- {title} (P{r["priority"]}, links={len(links)})')
        if len(rows) > 8:
            lines += ['', f'...and {len(rows)-8} more']
        self.branches_view.info.text = '\n'.join(lines)

    def export_branch_md(self, sender):
        branch = self.branches_view.current_branch
        if not branch:
            console.hud_alert('No branch selected', 'error')
            return
        path = self.db.export_branch_markdown(branch)
        console.hud_alert('Exported MD')
        dialogs.share_text(str(path))

    def export_branch_json(self, sender):
        branch = self.branches_view.current_branch
        if not branch:
            console.hud_alert('No branch selected', 'error')
            return
        path = self.db.export_branch_json(branch)
        console.hud_alert('Exported JSON')
        dialogs.share_text(str(path))

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
            box = ui.View(frame=(12, y, parent.width - 24, 86))
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

            try:
                link_count = len(json.loads(r['links_json'] or '[]'))
            except Exception:
                link_count = 0
            meta = ' · '.join([
                x for x in [
                    r['branch'] or '',
                    r['state_tag'] or '',
                    f'P{r["priority"]}',
                    f'L{link_count}',
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
            btn.flex = 'L'
            btn.entry_id = r['id']
            btn.action = self.open_from_button
            box.add_subview(btn)
            y += 94
        return y

    def open_from_button(self, sender):
        EntryForm(self.db, self.refresh_all, entry_id=sender.entry_id).present('sheet')

    def create_snapshot(self, sender):
        self.db.create_snapshot(
            self.snapshots_view.label_tf.text.strip(),
            self.snapshots_view.note_tf.text.strip()
        )
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


if __name__ == '__main__':
    MainView().present('fullscreen')
