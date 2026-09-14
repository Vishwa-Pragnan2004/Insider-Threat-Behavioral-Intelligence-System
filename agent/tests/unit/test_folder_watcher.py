"""Snapshot diffing behind the removable-drive and downloads collectors."""
from __future__ import annotations

import os
import shutil

import pytest

from itbis_agent.collectors._snapshot import (
    FileChange,
    FileState,
    FolderWatcher,
    Snapshot,
    diff_snapshots,
    take_snapshot,
)


def _write(root, rel, size, mtime=1_700_000_000):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def root(tmp_path):
    return str(tmp_path / "drive")


@pytest.fixture
def watcher(root):
    os.makedirs(root)
    return FolderWatcher(root)


# ─── Baseline and settling ──────────────────────────────────


def test_existing_files_are_a_baseline_not_activity(root, watcher):
    _write(root, "already-there.docx", 100)
    assert watcher.scan() == []
    assert watcher.scan() == []


def test_new_file_is_reported_once_it_has_settled(root, watcher):
    watcher.scan()
    _write(root, "report.docx", 5_000)

    assert watcher.scan() == [], "not reported until its size is confirmed stable"
    assert watcher.scan() == [FileChange("created", "report.docx", 5_000)]
    assert watcher.scan() == [], "reported exactly once"


def test_file_still_being_copied_is_reported_with_its_final_size(root, watcher):
    watcher.scan()
    _write(root, "big.iso", 1_000, mtime=1_700_000_001)
    assert watcher.scan() == []
    _write(root, "big.iso", 9_000, mtime=1_700_000_002)  # copy still in progress
    assert watcher.scan() == []
    assert watcher.scan() == [FileChange("created", "big.iso", 9_000)]


def test_file_created_and_removed_before_settling_is_not_reported(root, watcher):
    watcher.scan()
    path = _write(root, "temp.txt", 10)
    assert watcher.scan() == []
    os.remove(path)
    assert watcher.scan() == []


# ─── Modify / delete / rename ───────────────────────────────


def test_modifying_an_existing_file(root, watcher):
    _write(root, "notes.txt", 10, mtime=1_700_000_000)
    watcher.scan()
    _write(root, "notes.txt", 25, mtime=1_700_000_500)
    assert watcher.scan() == [FileChange("modified", "notes.txt", 25)]


def test_deleting_a_file(root, watcher):
    path = _write(root, "secret.pdf", 42)
    watcher.scan()
    os.remove(path)
    assert watcher.scan() == [FileChange("deleted", "secret.pdf", 42)]


def test_rename_is_one_change_not_delete_plus_create(root, watcher):
    _write(root, "draft.docx", 300)
    watcher.scan()
    os.rename(os.path.join(root, "draft.docx"), os.path.join(root, "final.docx"))
    assert watcher.scan() == [FileChange("renamed", "final.docx", 300, old_path="draft.docx")]


def test_ambiguous_renames_fall_back_to_created_and_deleted():
    old = Snapshot({"a.txt": FileState(1, 5), "b.txt": FileState(1, 5)})
    new = Snapshot({"c.txt": FileState(1, 5), "d.txt": FileState(1, 5)})
    kinds = sorted(c.kind for c in diff_snapshots(old, new))
    assert kinds == ["created", "created", "deleted", "deleted"]


def test_renamed_while_settling_is_reported_as_created_at_the_final_name(root, watcher):
    """What a browser does: write to a temp name, then rename when finished."""
    watcher.scan()
    _write(root, "setup.exe.part", 700)
    assert watcher.scan() == []
    os.rename(os.path.join(root, "setup.exe.part"), os.path.join(root, "setup.exe"))
    assert watcher.scan() == []
    assert watcher.scan() == [FileChange("created", "setup.exe", 700)]


# ─── Scope and robustness ───────────────────────────────────


def test_subfolders_are_watched_when_recursive(root, watcher):
    watcher.scan()
    _write(root, os.path.join("projects", "q3", "budget.xlsx"), 64)
    watcher.scan()
    assert watcher.scan() == [
        FileChange("created", os.path.join("projects", "q3", "budget.xlsx"), 64)
    ]


def test_subfolders_are_ignored_when_not_recursive(root):
    os.makedirs(root)
    shallow = FolderWatcher(root, recursive=False)
    shallow.scan()
    _write(root, os.path.join("nested", "file.txt"), 5)
    _write(root, "top.txt", 5)
    shallow.scan()
    assert shallow.scan() == [FileChange("created", "top.txt", 5)]


def test_skip_file_excludes_matching_names(root):
    os.makedirs(root)
    downloads = FolderWatcher(root, skip_file=lambda name: name.endswith(".crdownload"))
    downloads.scan()
    _write(root, "video.mp4.crdownload", 10)
    downloads.scan()
    assert downloads.scan() == []


def test_volume_system_folders_are_not_scanned(root):
    _write(root, os.path.join("System Volume Information", "IndexerVolumeGuid"), 5)
    _write(root, os.path.join("$RECYCLE.BIN", "S-1-5-21", "$R123.txt"), 5)
    _write(root, "user-file.txt", 5)
    assert set(take_snapshot(root).files) == {"user-file.txt"}


def test_pulled_drive_does_not_report_every_file_as_deleted(root, watcher):
    for i in range(3):
        _write(root, f"file{i}.txt", 10)
    watcher.scan()
    shutil.rmtree(root)  # the drive disappears

    assert watcher.scan() == []


def test_truncated_snapshot_never_implies_deletion():
    old = Snapshot({"a": FileState(1, 1), "b": FileState(1, 2)})
    truncated = Snapshot({"a": FileState(1, 1)}, truncated=True)
    assert diff_snapshots(old, truncated) == []


def test_snapshot_stops_at_max_files(root):
    for i in range(10):
        _write(root, f"f{i:02}.txt", 1)
    snap = take_snapshot(root, max_files=4)
    assert len(snap.files) == 4
    assert snap.truncated is True
