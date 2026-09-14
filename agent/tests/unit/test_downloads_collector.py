"""The downloads collector."""
from __future__ import annotations

import os
import sys

import pytest

from itbis_agent.collectors import downloads as dl


def _write(root, name, size, mtime=1_700_000_000):
    path = os.path.join(root, name)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def folder(tmp_path, monkeypatch):
    path = tmp_path / "Downloads"
    path.mkdir()
    monkeypatch.setattr(dl, "downloads_folder", lambda: str(path))
    return str(path)


@pytest.fixture
def marks(monkeypatch):
    """Stand-in Mark-of-the-Web store: path -> Zone.Identifier fields."""
    table: dict[str, dict] = {}
    monkeypatch.setattr(dl, "read_mark_of_the_web", lambda path: table.get(path))
    return table


def _collector():
    collector = dl.DownloadsCollector()
    collector.start()
    return collector


def test_downloaded_file_is_reported_with_its_source(folder, marks):
    collector = _collector()
    collector._poll()
    path = _write(folder, "invoice.pdf", 2048)
    marks[path] = {
        "ZoneId": "3",
        "HostUrl": "https://files.example.com/invoice.pdf",
        "ReferrerUrl": "https://mail.example.com/",
    }

    assert collector._poll() == [], "waits for the file to settle"
    [event] = collector._poll()

    assert event["source"] == "downloads"
    assert event["path"] == path
    assert event["file_name"] == "invoice.pdf"
    assert event["size"] == 2048
    assert event["zone_id"] == "3"
    assert event["host_url"] == "https://files.example.com/invoice.pdf"
    assert event["referrer_url"] == "https://mail.example.com/"


def test_files_already_in_downloads_are_not_reported(folder, marks):
    path = _write(folder, "old-download.zip", 10)
    marks[path] = {"ZoneId": "3"}
    collector = _collector()
    assert collector._poll() == []
    assert collector._poll() == []


def test_file_without_a_mark_is_not_a_download(folder, marks):
    """Something copied into Downloads locally (e.g. off a USB stick)."""
    collector = _collector()
    collector._poll()
    _write(folder, "copied-from-usb.docx", 50)

    results = [collector._poll() for _ in range(6)]

    assert all(r == [] for r in results)
    assert collector._awaiting_mark == {}, "gives up after its retries"


def test_mark_written_shortly_after_the_file_is_still_found(folder, marks):
    collector = _collector()
    collector._poll()
    path = _write(folder, "report.xlsx", 70)
    collector._poll()
    assert collector._poll() == [], "settled, but the browser hasn't written the mark yet"

    marks[path] = {"ZoneId": "3"}
    [event] = collector._poll()
    assert event["file_name"] == "report.xlsx"


def test_in_progress_browser_download_is_reported_once_complete(folder, marks):
    collector = _collector()
    collector._poll()
    partial = _write(folder, "movie.mp4.crdownload", 900)
    assert collector._poll() == [], "temporary download names are ignored"

    final = os.path.join(folder, "movie.mp4")
    os.rename(partial, final)
    marks[final] = {"ZoneId": "3", "HostUrl": "https://videos.example.com/movie.mp4"}

    assert collector._poll() == []
    [event] = collector._poll()
    assert event["file_name"] == "movie.mp4"


def test_idle_when_there_is_no_downloads_folder(monkeypatch):
    monkeypatch.setattr(dl, "downloads_folder", lambda: None)
    collector = _collector()
    assert collector._poll() == []


@pytest.mark.parametrize(
    ("name", "temporary"),
    [
        ("movie.mp4.crdownload", True),
        ("archive.zip.PART", True),
        ("setup.exe.partial", True),
        ("setup.exe", False),
        ("notes.txt", False),
    ],
)
def test_is_temporary_download(name, temporary):
    assert dl.is_temporary_download(name) is temporary


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS alternate data streams")
def test_real_mark_of_the_web_is_parsed(tmp_path):
    target = tmp_path / "report.zip"
    target.write_bytes(b"PK")
    with open(str(target) + ":Zone.Identifier", "w", encoding="utf-8") as stream:
        stream.write("[ZoneTransfer]\nZoneId=3\nHostUrl=https://example.com/report.zip\n")

    assert dl.read_mark_of_the_web(str(target)) == {
        "ZoneId": "3",
        "HostUrl": "https://example.com/report.zip",
    }

    plain = tmp_path / "local.txt"
    plain.write_text("hello", encoding="utf-8")
    assert dl.read_mark_of_the_web(str(plain)) is None


def test_downloads_folder_is_an_existing_directory_or_none():
    folder = dl.downloads_folder()
    assert folder is None or os.path.isdir(folder)
