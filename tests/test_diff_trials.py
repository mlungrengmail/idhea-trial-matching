"""Tests for fetch_trials diff mode."""

import json
import tempfile
from pathlib import Path

from scripts.fetch_trials import diff_trials


def _make_trial(nct_id, status="RECRUITING", enrollment=100):
    return {
        "nct_id": nct_id,
        "title": f"Trial {nct_id}",
        "status": status,
        "enrollment": enrollment,
    }


class TestDiffTrials:
    def test_no_existing_file(self):
        new_trials = [_make_trial("NCT00000001")]
        result = diff_trials(new_trials, old_path=Path("/nonexistent/path.json"))
        assert result["added"] == ["NCT00000001"]
        assert result["removed"] == []
        assert result["old_count"] == 0
        assert result["new_count"] == 1

    def test_added_and_removed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([_make_trial("NCT00000001"), _make_trial("NCT00000002")], f)
            old_path = Path(f.name)

        new_trials = [_make_trial("NCT00000001"), _make_trial("NCT00000003")]
        result = diff_trials(new_trials, old_path=old_path)
        assert result["added"] == ["NCT00000003"]
        assert result["removed"] == ["NCT00000002"]
        assert result["old_count"] == 2
        assert result["new_count"] == 2
        old_path.unlink()

    def test_status_changed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([_make_trial("NCT00000001", status="RECRUITING")], f)
            old_path = Path(f.name)

        new_trials = [_make_trial("NCT00000001", status="COMPLETED")]
        result = diff_trials(new_trials, old_path=old_path)
        assert len(result["status_changed"]) == 1
        assert result["status_changed"][0]["old_status"] == "RECRUITING"
        assert result["status_changed"][0]["new_status"] == "COMPLETED"
        old_path.unlink()

    def test_enrollment_changed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([_make_trial("NCT00000001", enrollment=100)], f)
            old_path = Path(f.name)

        new_trials = [_make_trial("NCT00000001", enrollment=200)]
        result = diff_trials(new_trials, old_path=old_path)
        assert len(result["enrollment_changed"]) == 1
        assert result["enrollment_changed"][0]["old_enrollment"] == 100
        assert result["enrollment_changed"][0]["new_enrollment"] == 200
        old_path.unlink()

    def test_no_changes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([_make_trial("NCT00000001")], f)
            old_path = Path(f.name)

        new_trials = [_make_trial("NCT00000001")]
        result = diff_trials(new_trials, old_path=old_path)
        assert result["added"] == []
        assert result["removed"] == []
        assert result["status_changed"] == []
        assert result["enrollment_changed"] == []
        old_path.unlink()
