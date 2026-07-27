# mycelium_bridge_launcher_v0_1.py
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import ui

BG = "#07101a"
PANEL = "#0d1622"
TEXT = "#eef7ff"
MUTED = "#8fb7c9"
ACCENT = "#6fe7ff"
GOOD = "#8cffcf"
WARN = "#ffd27a"
BAD = "#ff8ea8"

HERE = Path(__file__).resolve().parent
SEED_PATH = HERE / "mycelium_bridge_seed_v0_1.py"
SHELL_PATH = HERE / "mycelium_bridge_shell_v0_1.py"

def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

class Launcher(ui.View):
    def __init__(self):
        super().__init__(name="Mycelium Bridge Launcher")
        self.background_color = BG
        self.flex = "WH"
        self.seed = load_module(SEED_PATH, "mb_seed")
        self.setup_ui()

    def setup_ui(self):
        self.title_label = ui.Label(frame=(20, 30, 600, 34))
        self.title_label.text = "Mycelium Bridge"
        self.title_label.text_color = TEXT
        self.title_label.font = ("<System-Bold>", 28)
        self.add_subview(self.title_label)

        self.sub_label = ui.Label(frame=(20, 64, 700, 22))
        self.sub_label.text = "Launcher • safe buttons • no code editing"
        self.sub_label.text_color = MUTED
        self.sub_label.font = ("<System>", 14)
        self.add_subview(self.sub_label)

        self.status = ui.TextView(frame=(20, 100, self.width - 40, 170))
        self.status.flex = "W"
        self.status.background_color = PANEL
        self.status.text_color = TEXT
        self.status.editable = False
        self.status.font = ("Menlo", 12)
        self.status.corner_radius = 12
        self.status.border_width = 1
        self.add_subview(self.status)

        buttons = [
            ("Initialize", self.do_init, GOOD),
            ("Verify", self.do_verify, ACCENT),
            ("Repair", self.do_repair, WARN),
            ("Export", self.do_export, ACCENT),
            ("Snapshot", self.do_snapshot, ACCENT),
            ("Open Shell", self.open_shell, GOOD),
        ]
        self.btns = []
        y = 286
        for i, (title, action, color) in enumerate(buttons):
            btn = ui.Button(title=title)
            row = i // 2
            col = i % 2
            btn.frame = (20 + col * ((self.width - 60) / 2), y + row * 58, (self.width - 60) / 2, 46)
            btn.flex = "W"
            btn.background_color = PANEL
            btn.tint_color = color
            btn.corner_radius = 12
            btn.border_width = 1
            btn.action = action
            self.add_subview(btn)
            self.btns.append(btn)

        self.help = ui.Label(frame=(20, y + 3 * 58, self.width - 40, 60))
        self.help.flex = "WT"
        self.help.number_of_lines = 0
        self.help.text_color = MUTED
        self.help.font = ("<System>", 13)
        self.help.text = "Recommended order: Initialize → Open Shell. Verify is optional."
        self.add_subview(self.help)

        self.set_status("Ready.\n\nTap Initialize first.\nAfter that, tap Open Shell.")

    def layout(self):
        self.status.frame = (20, 100, self.width - 40, 170)
        y = 286
        half = (self.width - 60) / 2
        for i, btn in enumerate(self.btns):
            row = i // 2
            col = i % 2
            btn.frame = (20 + col * (half + 20), y + row * 58, half, 46)
        self.help.frame = (20, y + 3 * 58, self.width - 40, 60)

    def set_status(self, text):
        self.status.text = text

    def fmt_result(self, title, result):
        return title + "\n\n" + json.dumps(result, indent=2, ensure_ascii=False)

    def do_init(self, sender):
        try:
            result = self.seed.run("init", self.seed.DEFAULT_ROOT)
            self.set_status(self.fmt_result("Initialize complete", result))
        except Exception as e:
            self.set_status(f"Initialize failed\n\n{e}")

    def do_verify(self, sender):
        try:
            result = self.seed.run("verify", self.seed.DEFAULT_ROOT)
            self.set_status(self.fmt_result("Verify complete", result))
        except Exception as e:
            self.set_status(f"Verify failed\n\n{e}")

    def do_repair(self, sender):
        try:
            result = self.seed.run("repair", self.seed.DEFAULT_ROOT)
            self.set_status(self.fmt_result("Repair complete", result))
        except Exception as e:
            self.set_status(f"Repair failed\n\n{e}")

    def do_export(self, sender):
        try:
            result = self.seed.run("export", self.seed.DEFAULT_ROOT)
            self.set_status(self.fmt_result("Export complete", result))
        except Exception as e:
            self.set_status(f"Export failed\n\n{e}")

    def do_snapshot(self, sender):
        try:
            result = self.seed.run("snapshot", self.seed.DEFAULT_ROOT)
            self.set_status(self.fmt_result("Snapshot complete", result))
        except Exception as e:
            self.set_status(f"Snapshot failed\n\n{e}")

    def open_shell(self, sender):
        try:
            shell = load_module(SHELL_PATH, "mb_shell")
            self.set_status("Opening shell…")
            shell.main()
        except Exception as e:
            self.set_status(f"Open Shell failed\n\n{e}")

def main():
    v = Launcher()
    v.present("fullscreen", hide_title_bar=False)

if __name__ == "__main__":
    main()
