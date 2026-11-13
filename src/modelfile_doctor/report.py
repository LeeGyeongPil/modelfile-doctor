"""Diagnostics, reports and the rule registry."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# Rule id -> severities it can produce. Descriptions live in the locale catalogs
# under the key ``rule.<ID>``.
RULES: dict[str, tuple[Severity, ...]] = {
    "MF001": (Severity.WARNING,),
    "MF002": (Severity.ERROR,),
    "MF003": (Severity.ERROR,),
    "MF004": (Severity.ERROR,),
    "MF010": (Severity.WARNING,),
    "MF011": (Severity.ERROR,),
    "MF012": (Severity.ERROR,),
    "MF013": (Severity.WARNING,),
    "MF014": (Severity.ERROR,),
    "MF015": (Severity.WARNING,),
    "MF016": (Severity.WARNING,),
    "MF020": (Severity.ERROR,),
    "MF021": (Severity.ERROR,),
    "TP001": (Severity.ERROR,),
    "TP002": (Severity.ERROR,),
    "TP003": (Severity.ERROR,),
    "TP004": (Severity.ERROR,),
    "TP005": (Severity.WARNING,),
    "TP006": (Severity.INFO,),
    "CT001": (Severity.WARNING,),
    "CT002": (Severity.WARNING,),
    "CT003": (Severity.ERROR, Severity.WARNING),
    "CT004": (Severity.WARNING,),
    "CT005": (Severity.WARNING,),
    "CT010": (Severity.INFO,),
    "CT011": (Severity.INFO,),
}


@dataclass(frozen=True)
class Diagnostic:
    """One finding. ``message_key``/``params`` are language independent."""

    rule: str
    severity: Severity
    line: int
    message_key: str
    params: dict[str, Any] = field(default_factory=dict)
    fixable: bool = False  # reserved for the automatic fixer (not implemented yet)


@dataclass
class Report:
    path: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    encoding: str = "utf-8"

    def count(self, severity: Severity) -> int:
        return sum(1 for d in self.diagnostics if d.severity is severity)

    @property
    def errors(self) -> int:
        return self.count(Severity.ERROR)

    @property
    def warnings(self) -> int:
        return self.count(Severity.WARNING)

    @property
    def infos(self) -> int:
        return self.count(Severity.INFO)


def sort_key(d: Diagnostic) -> tuple[int, str]:
    return (d.line, d.rule)
