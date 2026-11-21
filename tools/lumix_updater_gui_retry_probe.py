#!/usr/bin/env python3
"""Check real Tk retry controls with a declared offline workflow, never USB.

The GUI's actual button, background thread and event queue execute. Camera
outcomes are explicit test inputs; this is not a camera/write-protocol test.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from apps.lumix_updater.gui import App
from apps.lumix_updater import __version__


def probe(report_path, assets):
    results = []
    with tempfile.TemporaryDirectory(prefix='lumix-gui-retry-') as temporary:
        class OfflineWorkflow:
            inspection = object()
            output = Path(temporary)
            manifest = dict(temporary_flag_needed=True)

            def __init__(self):
                self.calls = 0
                self.allow_finish = threading.Event()

            def enable(self, *, card_inserted_with_power_off, progress):
                if not card_inserted_with_power_off:
                    raise AssertionError('The card confirmation was lost')
                self.calls += 1
                if not self.allow_finish.wait(5):
                    raise AssertionError('The GUI probe did not release its worker')
                if self.calls == 2:
                    raise RuntimeError('Declared disconnected-camera fixture')
                return dict(wrote_ram=True)

        workflow = OfflineWorkflow()
        root = tk.Tk()
        try:
            app = App(root, assets=assets, workflow=workflow)
            app.tabs.select(2)
            app.enable_button.configure(state='normal')
            app.card_check.configure(state='normal')
            app.card.set(True)
            errors = []
            with patch('apps.lumix_updater.gui.messagebox.showerror', side_effect=lambda *a, **k: errors.append(a)):
                for attempt in range(1, 4):
                    workflow.allow_finish.clear()
                    app.enable_button.invoke()
                    root.update()
                    if app.busy != 'enable' or str(app.enable_button.cget('state')) != 'disabled':
                        raise AssertionError('An active enable attempt did not lock the button')
                    app.enable_button.invoke()
                    workflow.allow_finish.set()
                    deadline = time.monotonic()+10
                    while app.busy and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.005)
                    if (app.busy or workflow.calls != attempt or not app.card.get()
                            or str(app.enable_button.cget('state')) != 'normal'
                            or str(app.card_check.cget('state')) != 'normal'
                            or workflow.output != Path(temporary)):
                        raise AssertionError('Completed attempt lost retry readiness/prepared state')
                    results.append(dict(attempt=attempt, declared_result='error' if attempt == 2 else 'success',
                        button_enabled_after_completion=True, duplicate_click_ignored=True,
                        card_confirmation_and_prepared_folder_preserved=True))
            if len(errors) != 1:
                raise AssertionError('Declared failure did not show exactly one error')
        finally:
            root.destroy()
    result = dict(schema=1, time_utc=datetime.now(timezone.utc).isoformat(), passed=True,
        version=__version__, cases=results, real_tk_button_thread_and_poll_used=True,
        explicit_offline_camera_outcomes=True, camera_contacted=False,
        source_sha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest())
    report_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with report_path.open('x') as stream:
        stream.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(passed=True, attempts=len(results), camera_contacted=False)))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    probe(a.report, a.assets)
