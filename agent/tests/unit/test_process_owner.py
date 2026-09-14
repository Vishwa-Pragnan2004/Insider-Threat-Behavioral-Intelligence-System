"""
Process owner resolution.

Previously every process launch was attributed to "SYSTEM" because the owner
was never looked up.
"""
from __future__ import annotations

from types import SimpleNamespace

from itbis_agent.collectors.process import _resolve_owner

USER_SID = "S-1-5-21-823331484-1016666011-1433572944-1001"


def _instance(
    user="vishw",
    domain="VISHWA",
    return_value=0,
    sid=USER_SID,
    owner_fails=False,
    sid_fails=False,
    parent_pid=7,
):
    def exec_method(name):
        if name == "GetOwner":
            if owner_fails:
                raise RuntimeError("the process has exited")
            return SimpleNamespace(ReturnValue=return_value, User=user, Domain=domain)
        if name == "GetOwnerSid":
            if sid_fails:
                raise RuntimeError("access denied")
            return SimpleNamespace(ReturnValue=0, Sid=sid)
        raise AssertionError(f"unexpected WMI method {name}")

    return SimpleNamespace(ExecMethod_=exec_method, ParentProcessId=parent_pid)


class FakeWmi:
    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.requests: list[str] = []

    def Get(self, path):  # noqa: N802 - mirrors the WMI COM method name
        self.requests.append(path)
        if self.parent is None:
            raise RuntimeError("not found")
        return self.parent


def test_owner_comes_from_the_process_itself():
    wmi = FakeWmi()
    assert _resolve_owner(wmi, _instance()) == ("VISHWA\\vishw", USER_SID)
    assert wmi.requests == [], "the parent must not be queried when the process answers"


def test_exited_process_falls_back_to_its_parent():
    wmi = FakeWmi(parent=_instance(user="vishw"))
    target = _instance(owner_fails=True, parent_pid=7)

    assert _resolve_owner(wmi, target) == ("VISHWA\\vishw", USER_SID)
    assert wmi.requests == ["Win32_Process.Handle='7'"]


def test_nonzero_return_value_is_treated_as_a_failure():
    wmi = FakeWmi(parent=_instance(user="parent-user"))
    target = _instance(return_value=2)  # 2 = access denied

    assert _resolve_owner(wmi, target) == ("VISHWA\\parent-user", USER_SID)


def test_unresolvable_owner_returns_none():
    wmi = FakeWmi(parent=None)
    assert _resolve_owner(wmi, _instance(owner_fails=True)) == (None, None)


def test_missing_sid_still_returns_the_name():
    assert _resolve_owner(FakeWmi(), _instance(sid_fails=True)) == ("VISHWA\\vishw", None)


def test_owner_without_a_domain():
    assert _resolve_owner(FakeWmi(), _instance(domain="")) == ("vishw", USER_SID)
