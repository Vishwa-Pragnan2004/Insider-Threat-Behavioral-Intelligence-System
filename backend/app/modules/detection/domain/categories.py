"""
ITBIS — Detection Module: anomaly categories and detection engines

The specification's Anomaly Detection Engine has four engines and five named
anomaly categories. Every finding carries exactly one category; the engine it
belongs to follows from the category.

    Engine               Categories
    behavioral           BEHAVIORAL_ANOMALY (the ML model), INSIDER_RISK_INDICATOR
    access               UNUSUAL_LOGIN_TIME, UNAUTHORIZED_ACCESS_ATTEMPT
    data_exfiltration    ABNORMAL_DATA_DOWNLOAD, EXCESSIVE_FILE_TRANSFER,
                         SUSPICIOUS_DEVICE_USAGE
    privilege_abuse      PRIVILEGE_ABUSE
"""

from __future__ import annotations

from enum import Enum


class DetectionEngine(str, Enum):
    BEHAVIORAL = "behavioral"
    ACCESS = "access"
    DATA_EXFILTRATION = "data_exfiltration"
    PRIVILEGE_ABUSE = "privilege_abuse"


class AnomalyCategory(str, Enum):
    BEHAVIORAL_ANOMALY = "BEHAVIORAL_ANOMALY"
    UNUSUAL_LOGIN_TIME = "UNUSUAL_LOGIN_TIME"
    UNAUTHORIZED_ACCESS_ATTEMPT = "UNAUTHORIZED_ACCESS_ATTEMPT"
    ABNORMAL_DATA_DOWNLOAD = "ABNORMAL_DATA_DOWNLOAD"
    EXCESSIVE_FILE_TRANSFER = "EXCESSIVE_FILE_TRANSFER"
    SUSPICIOUS_DEVICE_USAGE = "SUSPICIOUS_DEVICE_USAGE"
    PRIVILEGE_ABUSE = "PRIVILEGE_ABUSE"
    #: Context that raises concern without being misuse on its own
    #: (e.g. job-search browsing before a departure).
    INSIDER_RISK_INDICATOR = "INSIDER_RISK_INDICATOR"


CATEGORY_ENGINE: dict[AnomalyCategory, DetectionEngine] = {
    AnomalyCategory.BEHAVIORAL_ANOMALY: DetectionEngine.BEHAVIORAL,
    AnomalyCategory.INSIDER_RISK_INDICATOR: DetectionEngine.BEHAVIORAL,
    AnomalyCategory.UNUSUAL_LOGIN_TIME: DetectionEngine.ACCESS,
    AnomalyCategory.UNAUTHORIZED_ACCESS_ATTEMPT: DetectionEngine.ACCESS,
    AnomalyCategory.ABNORMAL_DATA_DOWNLOAD: DetectionEngine.DATA_EXFILTRATION,
    AnomalyCategory.EXCESSIVE_FILE_TRANSFER: DetectionEngine.DATA_EXFILTRATION,
    AnomalyCategory.SUSPICIOUS_DEVICE_USAGE: DetectionEngine.DATA_EXFILTRATION,
    AnomalyCategory.PRIVILEGE_ABUSE: DetectionEngine.PRIVILEGE_ABUSE,
}

CATEGORY_LABELS: dict[AnomalyCategory, str] = {
    AnomalyCategory.BEHAVIORAL_ANOMALY: "Behavioral anomaly",
    AnomalyCategory.UNUSUAL_LOGIN_TIME: "Unusual login time",
    AnomalyCategory.UNAUTHORIZED_ACCESS_ATTEMPT: "Unauthorized access attempt",
    AnomalyCategory.ABNORMAL_DATA_DOWNLOAD: "Abnormal data download / upload",
    AnomalyCategory.EXCESSIVE_FILE_TRANSFER: "Excessive file transfers",
    AnomalyCategory.SUSPICIOUS_DEVICE_USAGE: "Suspicious device usage",
    AnomalyCategory.PRIVILEGE_ABUSE: "Privilege abuse",
    AnomalyCategory.INSIDER_RISK_INDICATOR: "Insider risk indicator",
}
