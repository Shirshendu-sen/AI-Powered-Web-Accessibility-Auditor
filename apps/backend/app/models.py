"""Pydantic models mirroring the MongoDB collections locked in Section 2.3
of docs/guide.md. Field names must match the spec exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


ScanStatus = Literal["pending", "completed", "completed_with_errors", "failed"]
Severity = Literal["critical", "serious", "moderate", "minor"]


class AiFix(BaseModel):
    """Shape of the `ai_fix` sub-document on `violations`."""

    model_config = ConfigDict(extra="allow")

    type: str
    original: str
    fixed: Optional[str] = None
    explanation: str
    confidence: float


class Scan(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: Optional[Any] = Field(default=None, alias="_id")
    url: str
    scanned_at: datetime
    score_before: Optional[int] = None
    score_after: Optional[int] = None
    status: ScanStatus


class Violation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: Optional[Any] = Field(default=None, alias="_id")
    scan_id: Any
    rule_id: str
    severity: Severity
    wcag_ref: list[str] = Field(default_factory=list)
    dom_snippet: str
    ai_fix: Optional[AiFix] = None


class User(BaseModel):
    """Stub only — accounts are out of v1 scope (Section 2.4)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: Optional[Any] = Field(default=None, alias="_id")
    email: str
    password_hash: str
    created_at: datetime
