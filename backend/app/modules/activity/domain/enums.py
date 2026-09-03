"""
ITBIS — Activity Module: Domain Enums
"""
from enum import Enum


class LogType(str, Enum):
    """CERT Insider Threat dataset log types."""
    LOGON = "logon"
    DEVICE = "device"
    FILE = "file"
    EMAIL = "email"
    HTTP = "http"
    LDAP = "ldap"
    PSYCHOMETRIC = "psychometric"
    UNKNOWN = "unknown"


class JobStatus(str, Enum):
    """Lifecycle states for an ingestion job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"   # Completed with some errors
