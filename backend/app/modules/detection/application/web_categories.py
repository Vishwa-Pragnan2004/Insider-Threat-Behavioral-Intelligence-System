"""
ITBIS — Detection Module: web destination categories

Classifies a visited URL into the few categories that matter for insider
risk. Lists are deliberately short and made of well-known services; they are
a starting point an organisation is expected to extend.

    LEAK_SITE       whistle-blowing / paste sites used to publish stolen data
    CLOUD_STORAGE   personal file sharing, a common exfiltration channel
    JOB_SEARCH      job boards: a pre-departure indicator, not misuse
    HACKING_TOOLS   keyloggers / monitoring spyware vendors

Matching is by host (a listed domain or any of its subdomains) plus a few
keywords for tool downloads, whose hosts vary widely.
"""

from __future__ import annotations

from enum import Enum
from urllib.parse import urlsplit


class WebCategory(str, Enum):
    LEAK_SITE = "leak_site"
    CLOUD_STORAGE = "cloud_storage"
    JOB_SEARCH = "job_search"
    HACKING_TOOLS = "hacking_tools"


_DOMAINS: dict[WebCategory, frozenset[str]] = {
    WebCategory.LEAK_SITE: frozenset(
        {"wikileaks.org", "wikileaks.ch", "cryptome.org", "pastebin.com", "ghostbin.com"}
    ),
    WebCategory.CLOUD_STORAGE: frozenset(
        {
            "dropbox.com",
            "box.com",
            "drive.google.com",
            "docs.google.com",
            "onedrive.live.com",
            "1drv.ms",
            "mega.nz",
            "mega.io",
            "wetransfer.com",
            "mediafire.com",
            "sendspace.com",
            "4shared.com",
            "icloud.com",
            "pcloud.com",
        }
    ),
    WebCategory.JOB_SEARCH: frozenset(
        {
            "monster.com",
            "careerbuilder.com",
            "indeed.com",
            "glassdoor.com",
            "simplyhired.com",
            "dice.com",
            "hotjobs.yahoo.com",
            "jobhuntersbible.com",
            "ziprecruiter.com",
            "naukri.com",
            "job-hunt.org",
        }
    ),
    WebCategory.HACKING_TOOLS: frozenset(
        {
            "spectorsoft.com",
            "refog.com",
            "actualkeylogger.com",
            "keylogger.com",
            "spytech-web.com",
            "wolfeye.us",
            "kidlogger.net",
            "spyrix.com",
            "softactivity.com",
            "webwatchernow.com",
            "awarenesstech.com",
        }
    ),
}

#: Substrings of the host or path that identify a category regardless of host.
_KEYWORDS: dict[WebCategory, tuple[str, ...]] = {
    WebCategory.HACKING_TOOLS: ("keylog", "keystroke-logger", "keystrokelogger"),
    WebCategory.JOB_SEARCH: ("linkedin.com/jobs",),
}


def url_host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlsplit(url if "://" in url else f"http://{url}").hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def classify_url(url: str | None) -> WebCategory | None:
    host = url_host(url)
    if host is None:
        return None
    for category, domains in _DOMAINS.items():
        if host in domains or any(host.endswith("." + d) for d in domains):
            return category
    lowered = (url or "").lower()
    for category, keywords in _KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return category
    return None
