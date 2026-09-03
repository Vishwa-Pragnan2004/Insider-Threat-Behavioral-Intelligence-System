"""
ITBIS — CERT Psychometric / HR Log Parser

Handles CERT dataset psychometric.csv or hr.csv variants.
These files contain organizational/HR data: employee info, role, department.
Typical columns: employee_id, user_id, name, email, role, department, team, manager
"""
from datetime import UTC
from typing import Any

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.shared.schemas.canonical_event import CanonicalEvent, EventType


class PsychometricParser(BaseParser):
    """Parses CERT HR/organizational/psychometric data records."""

    LOG_TYPE = LogType.PSYCHOMETRIC
    SOURCE_DATASET = "cert"
    REQUIRED_COLUMNS = {"employee_id"}

    COLUMN_ALIASES = {
        "employee_id": ["employee_id", "emp_id", "id", "user_id"],
        "user_id":     ["user_id", "user", "userid", "employee_id"],
        "name":        ["name", "full_name", "employee_name"],
        "email":       ["email", "email_address", "mail"],
        "role":        ["role", "job_title", "title", "position"],
        "department":  ["department", "dept", "team", "division"],
        "manager":     ["manager", "supervisor", "manager_id"],
        "start_date":  ["start_date", "hire_date", "employment_start"],
    }

    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        """
        HR records don't have activity timestamps — use current time.
        These events represent organizational context, not real-time activity.
        """
        from datetime import datetime
        employee_id = self.resolve_required(row, "employee_id", row_number)
        user_id = self.resolve_column(row, "user_id") or employee_id
        name = self.resolve_column(row, "name")
        email = self.resolve_column(row, "email")
        role = self.resolve_column(row, "role")
        department = self.resolve_column(row, "department")
        manager = self.resolve_column(row, "manager")
        start_date_raw = self.resolve_column(row, "start_date")

        ts = datetime.now(UTC)
        if start_date_raw:
            try:
                ts = self.parse_timestamp(start_date_raw, row_number)
            except Exception:
                pass

        return CanonicalEvent(
            event_id=self.new_event_id(),
            event_type=EventType.SYSTEM_EVENT,
            source_dataset=self.SOURCE_DATASET,
            raw_event_id=employee_id,
            timestamp=ts,
            user_id=user_id,
            username=user_id,
            user_email=email,
            employee_id=employee_id,
            department=department,
            action="hr_record",
            raw_payload={**row, "_job_id": job_id},
            enrichments={
                "full_name": name,
                "role": role,
                "manager": manager,
            },
            tags=[self.LOG_TYPE.value, "hr"],
        )
