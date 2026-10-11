"""Event definitions and immutable ledger records.

Adheres to strict append-only constraints: no event record is ever mutated or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.ledger.money import Money


class EventType(str, Enum):
    """Categorization of ledger event types."""
    # Balance posting events (directly impact ledger balance)
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    SETTLEMENT = "SETTLEMENT"
    REVERSAL = "REVERSAL"
    FEE_ASSESSMENT = "FEE_ASSESSMENT"
    INTEREST_CREDIT = "INTEREST_CREDIT"

    # Authorization events (affect available balance via holds, never ledger balance)
    AUTHORIZATION = "AUTHORIZATION"


class AuthStatus(str, Enum):
    """Lifecycle status of an authorization request."""
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable record of an event in the ledger.
    
    Attributes:
        sequence_id: Monotonically increasing sequential index in the event store.
        event_id: Logical event identifier (e.g. 'E1', 'E2', 'FEE-D5-ACC001').
        event_type: Type of event.
        account_id: Account identifier ('ACC-001', 'ACC-002').
        booking_day: Calendar day on which the event arrived/was recorded into the ledger.
        value_day: Effective financial day for interest and balance calculations.
        amount: Exact monetary value.
        auth_id: Authorization identifier (e.g. 'Auth-A', 'Auth-B', 'Auth-Z') if applicable.
        reference_event_id: Target event ID for reversals (e.g. E9 references E7).
        description: Operational metadata / audit description.
    """
    sequence_id: int
    event_id: str
    event_type: EventType
    account_id: str
    booking_day: int
    value_day: int
    amount: Money
    auth_id: Optional[str] = None
    reference_event_id: Optional[str] = None
    description: str = ""
