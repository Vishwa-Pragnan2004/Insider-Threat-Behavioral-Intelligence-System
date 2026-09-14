"""The removable-drive file activity collector."""
from __future__ import annotations

import os

import pytest

from itbis_agent.collectors import removable_files as rf


def _write(root, rel, size, mtime=1_700_000_000):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def drive(tmp_path, monkeypatch):
    root = str(tmp_path / "usb")
    os.makedirs(root)
    mounted = [root]
    monkeypatch.setattr(rf, "list_removable_drives", lambda: list(mounted))
    monkeypatch.setattr(rf, "volume_label", lambda _root: "SANDISK")
    return root, mounted


@pytest.fixture
def collector():
    c = rf.RemovableFilesCollector()
    c.start()
    return c


def test_files_already_on_a_newly_inserted_drive_are_not_reported(drive, collector):
    root, _ = drive
    _write(root, "holiday-photos.zip", 10)
    assert collector._poll() == []
    assert collector._poll() == []


def test_copying_a_file_onto_the_drive(drive, collector):
    root, _ = drive
    collector._poll()
    _write(root, "exfil.zip", 4096)

    assert collector._poll() == [], "not reported until the copy has settled"
    created, transfer = collector._poll()

    assert created["source"] == "removable_files"
    assert created["kind"] == "created"
    assert created["path"] == os.path.join(root, "exfil.zip")
    assert created["size"] == 4096
    assert created["volume_name"] == "SANDISK"
    assert transfer["kind"] == "data_transfer"
    assert transfer["size"] == 4096
    assert transfer["file_count"] == 1


def test_several_files_in_one_scan_are_one_data_transfer(drive, collector):
    root, _ = drive
    collector._poll()
    for name, size in (("a.docx", 100), ("b.xlsx", 200), ("c.pdf", 300)):
        _write(root, name, size)
    collector._poll()

    events = collector._poll()

    assert [e["kind"] for e in events] == ["created", "created", "created", "data_transfer"]
    assert events[-1]["size"] == 600
    assert events[-1]["file_count"] == 3


def test_deleting_and_renaming_are_not_data_transfers(drive, collector):
    root, _ = drive
    _write(root, "a.txt", 10)
    _write(root, "b.txt", 20)
    collector._poll()
    collector._poll()
    os.remove(os.path.join(root, "a.txt"))
    os.rename(os.path.join(root, "b.txt"), os.path.join(root, "c.txt"))

    events = collector._poll()

    assert [e["kind"] for e in events] == ["deleted", "renamed"]
    assert events[1]["old_path"] == os.path.join(root, "b.txt")


def test_unplugged_drive_stops_being_watched(drive, collector):
    root, mounted = drive
    _write(root, "f.txt", 1)
    collector._poll()
    mounted.clear()

    assert collector._poll() == []
    assert collector._watchers == {}


def test_reinserted_drive_takes_a_fresh_baseline(drive, collector):
    """Files written to the drive on another computer aren't activity on this one."""
    root, mounted = drive
    collector._poll()
    mounted.clear()
    collector._poll()
    _write(root, "written-on-another-pc.txt", 5)
    mounted.append(root)

    assert collector._poll() == []
    assert collector._poll() == []


def test_idle_without_removable_drives(monkeypatch):
    monkeypatch.setattr(rf, "list_removable_drives", lambda: [])
    collector = rf.RemovableFilesCollector()
    collector.start()
    assert collector._poll() == []


def test_listing_drives_is_safe_on_any_platform():
    assert isinstance(rf.list_removable_drives(), list)
