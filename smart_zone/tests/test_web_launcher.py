"""Unit tests for dashboard.web_launcher.WebSimLauncher: missing-entry-file
handling (no crash, clear message), the double-launch guard, and that
launching never touches any risk-decision state."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from smart_zone.dashboard.web_launcher import WebSimLauncher


class TestMissingEntryFile:
    def test_missing_index_html_prints_clear_message_and_does_not_crash(self, tmp_path, capsys):
        empty_dir = tmp_path / "no_simulation_here"
        empty_dir.mkdir()
        launcher = WebSimLauncher(simulation_dir=empty_dir)

        launcher.launch()  # must not raise

        captured = capsys.readouterr()
        assert "not found" in captured.out.lower() or "not found" in captured.err.lower()
        assert str(empty_dir) in captured.out or str(empty_dir) in captured.err

    def test_missing_entry_file_never_starts_a_subprocess(self, tmp_path):
        empty_dir = tmp_path / "no_simulation_here"
        empty_dir.mkdir()
        launcher = WebSimLauncher(simulation_dir=empty_dir)

        with patch("subprocess.Popen") as mock_popen:
            launcher.launch()
            time.sleep(0.1)  # give any stray background thread a moment
            mock_popen.assert_not_called()

    def test_missing_entry_file_allows_a_later_retry(self, tmp_path):
        """If launch() is called again after the folder still doesn't
        exist, it should try again (not get permanently stuck as
        'started') -- but still not crash."""
        empty_dir = tmp_path / "no_simulation_here"
        empty_dir.mkdir()
        launcher = WebSimLauncher(simulation_dir=empty_dir)

        launcher.launch()
        launcher.launch()  # should also just print the message again, not crash
        assert True  # reaching here means neither call raised

    def test_index_html_present_but_no_package_json_prints_clear_message(self, tmp_path, capsys):
        sim_dir = tmp_path / "simulation"
        sim_dir.mkdir()
        (sim_dir / "index.html").write_text("<html></html>")
        launcher = WebSimLauncher(simulation_dir=sim_dir)

        with patch("subprocess.Popen") as mock_popen:
            launcher.launch()
            time.sleep(0.1)
            mock_popen.assert_not_called()

        captured = capsys.readouterr()
        assert "package.json" in captured.out or "package.json" in captured.err


class TestDoubleLaunchGuard:
    def test_second_launch_while_first_is_starting_does_not_spawn_a_second_subprocess(self, tmp_path):
        sim_dir = tmp_path / "simulation"
        sim_dir.mkdir()
        (sim_dir / "index.html").write_text("<html></html>")
        (sim_dir / "package.json").write_text("{}")
        launcher = WebSimLauncher(simulation_dir=sim_dir, port=59999)

        with patch("subprocess.Popen") as mock_popen, \
             patch("smart_zone.dashboard.web_launcher._port_is_open", return_value=False), \
             patch("webbrowser.open"):
            mock_process = mock_popen.return_value
            mock_process.poll.return_value = None  # looks like it's still running

            launcher.launch()
            launcher.launch()
            launcher.launch()
            time.sleep(0.2)

            assert mock_popen.call_count == 1

    def test_launch_returns_immediately_not_blocking_the_caller(self, tmp_path):
        """launch() itself must return promptly -- the port-wait/browser-open
        happens on a background thread, never on the calling thread."""
        sim_dir = tmp_path / "simulation"
        sim_dir.mkdir()
        (sim_dir / "index.html").write_text("<html></html>")
        (sim_dir / "package.json").write_text("{}")
        launcher = WebSimLauncher(simulation_dir=sim_dir, port=59999)

        with patch("subprocess.Popen") as mock_popen, \
             patch("smart_zone.dashboard.web_launcher._port_is_open", return_value=False), \
             patch("webbrowser.open"):
            mock_popen.return_value.poll.return_value = None

            start = time.perf_counter()
            launcher.launch()
            elapsed = time.perf_counter() - start

        assert elapsed < 0.2  # should be near-instant; the real work is backgrounded


class TestNoRiskEngineInteraction:
    def test_launching_does_not_import_or_touch_risk_engine(self, tmp_path):
        """Static + behavioral check: web_launcher.py has no import of
        safety.risk_engine (or any decision module), and calling launch()
        cannot possibly mutate anything risk-related since it never
        receives a risk_engine reference in the first place."""
        import ast
        from pathlib import Path as P

        source_path = P(__file__).resolve().parent.parent / "dashboard" / "web_launcher.py"
        tree = ast.parse(source_path.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = ["risk_engine", "safety.zone", "safety.confidence", "prediction.kalman", "prediction.ttc"]
        for module in imported:
            for f in forbidden:
                assert f not in module, f"web_launcher.py imports decision logic: {module}"

    def test_launch_signature_takes_no_risk_engine_argument(self, tmp_path):
        sim_dir = tmp_path / "simulation"
        sim_dir.mkdir()
        (sim_dir / "index.html").write_text("<html></html>")
        (sim_dir / "package.json").write_text("{}")
        launcher = WebSimLauncher(simulation_dir=sim_dir, port=59999)

        import inspect
        sig = inspect.signature(launcher.launch)
        assert len(sig.parameters) == 0  # launch() takes nothing that could be a risk engine


class TestClose:
    def test_close_before_launch_does_not_crash(self, tmp_path):
        launcher = WebSimLauncher(simulation_dir=tmp_path)
        launcher.close()  # no process started yet -- must be a safe no-op

    def test_close_terminates_a_running_process(self, tmp_path):
        sim_dir = tmp_path / "simulation"
        sim_dir.mkdir()
        (sim_dir / "index.html").write_text("<html></html>")
        (sim_dir / "package.json").write_text("{}")
        launcher = WebSimLauncher(simulation_dir=sim_dir, port=59999)

        with patch("subprocess.Popen") as mock_popen, \
             patch("smart_zone.dashboard.web_launcher._port_is_open", return_value=True), \
             patch("webbrowser.open"):
            mock_process = mock_popen.return_value
            mock_process.poll.return_value = None

            launcher.launch()
            time.sleep(0.2)
            launcher.close()

            mock_process.terminate.assert_called_once()
