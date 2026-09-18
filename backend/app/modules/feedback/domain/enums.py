"""
ITBIS — Feedback Module: Domain Enums
"""

from enum import Enum


class Verdict(str, Enum):
    """An analyst's judgement of what an alert turned out to be.

    This is deliberately separate from `AlertStatus`.  Status says where
    the alert is in the queue; a verdict says what the person actually
    did.  Only the latter is evidence about whether the system was right,
    so only the latter is usable as a training label.

    CONFIRMED_THREAT
        The behaviour was what the alert claimed: an insider acting
        against the organisation.
    POLICY_VIOLATION
        Real misconduct, but not an insider threat — shadow IT, personal
        use of a work machine, sloppy handling of data.  The alert found
        something; it did not find what it said it found.
    BENIGN
        Ordinary work that the system misread.  A false positive.
    INCONCLUSIVE
        Investigated and still unclear.  Recorded honestly rather than
        forced into one of the other three.
    """

    CONFIRMED_THREAT = "CONFIRMED_THREAT"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    BENIGN = "BENIGN"
    INCONCLUSIVE = "INCONCLUSIVE"


#: How a verdict maps to a supervised training label.
#:
#: POLICY_VIOLATION and INCONCLUSIVE map to None — they are *excluded* from
#: training rather than guessed at.  A policy violation is genuinely neither
#: class: calling it a threat teaches the model to chase shadow IT, calling
#: it benign teaches it to ignore behaviour an analyst thought was worth
#: writing up.  They are still stored, because "the alert found something
#: real but mislabelled it" is worth measuring on its own.
TRAINING_LABEL: dict[Verdict, bool | None] = {
    Verdict.CONFIRMED_THREAT: True,
    Verdict.BENIGN: False,
    Verdict.POLICY_VIOLATION: None,
    Verdict.INCONCLUSIVE: None,
}


#: Verdicts that say the system was right or wrong about *this* alert.
#: Precision-to-date is measured over these two only.
DECISIVE = (Verdict.CONFIRMED_THREAT, Verdict.BENIGN)
