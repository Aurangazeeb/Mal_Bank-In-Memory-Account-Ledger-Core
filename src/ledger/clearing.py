"""Clearing and settlement engine, handling:
1. Matching settlements: partial and full settlement against existing authorization holds (e.g. E5 for Auth-A).
2. Force-post settlements: settlements referencing an unknown authorization ID (e.g. E6 for Auth-Z).
   Card payment schemes (Visa/Mastercard) and banking network rules mandate posting the clearing debit
   to avoid network fines, while logging an operational alert.
3. Back-dated debits (e.g. E7).
4. Reversals: append-only compensating entries (e.g. E9 reversing E7) preserving full auditability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.ledger.events import AuthStatus, Event, EventType
from src.ledger.money import Money
from src.ledger.store import EventStore, LedgerError


class SettlementError(LedgerError):
    pass


class ReversalError(LedgerError):
    pass


@dataclass
class SettlementResult:
    settlement_event: Event
    auth_id: str
    is_force_post: bool
    hold_amount_released: Optional[Money]
    settled_amount: Money
    operational_alert: Optional[str] = None


@dataclass
class ReversalResult:
    reversal_event: Event
    target_event_id: str
    reversed_amount: Money


class ClearingEngine:
    """Manages authorization settlement, force-posting presentments, and transaction reversals."""

    def __init__(self, store: EventStore) -> None:
        self.store = store

    def process_settlement(
        self,
        event_id: str,
        account_id: str,
        auth_id: str,
        booking_day: int,
        value_day: int,
        amount: Money,
        description: str = "",
    ) -> SettlementResult:
        """Processes a clearing settlement presentment.
        
        If matching authorization hold exists:
          - Release the hold completely (even if partial settlement, per card scheme rules).
          - Post the SETTLEMENT debit event with the actual presentment amount.
          
        If no matching authorization exists (Force-Post / Unmatched Presentment):
          - In real-world banking operations, a presentment from the card network is a legal clearing
            obligation. The bank cannot unilaterally reject it without violating scheme rules and incurring fines.
          - The debit is POSTED to the account, and an operational warning is logged.
        """
        account = self.store.get_account(account_id)
        hold = account.holds.get(auth_id)

        is_force_post = hold is None or not hold.is_active
        hold_released: Optional[Money] = None
        alert: Optional[str] = None

        if not is_force_post and hold is not None:
            # Matching hold found: release the active hold
            hold.is_active = False
            hold.settlement_event_id = event_id
            hold_released = hold.amount
            desc = description or f"Settlement for {auth_id} (hold {hold.amount.format()} released, settled {amount.format()})"
        else:
            # Force-post / unmatched presentment
            is_force_post = True
            alert = f"FORCE_POST: Settlement {event_id} for {auth_id} has no preceding active authorization. Posted per clearing network obligation."
            desc = description or f"Force-post settlement for {auth_id} (no prior authorization hold)."

        # Append SETTLEMENT debit event
        settlement_event = self.store.append_event(
            event_id=event_id,
            event_type=EventType.SETTLEMENT,
            account_id=account_id,
            booking_day=booking_day,
            value_day=value_day,
            amount=amount,
            auth_id=auth_id,
            description=desc,
        )

        return SettlementResult(
            settlement_event=settlement_event,
            auth_id=auth_id,
            is_force_post=is_force_post,
            hold_amount_released=hold_released,
            settled_amount=amount,
            operational_alert=alert,
        )

    def process_reversal(
        self,
        event_id: str,
        account_id: str,
        target_event_id: str,
        booking_day: int,
        value_day: int,
        description: str = "",
    ) -> ReversalResult:
        """Processes an append-only transaction reversal (e.g. E9 reversing E7).
        
        In an append-only ledger:
          - The original event (E7) is NEVER mutated or deleted.
          - A compensating REVERSAL event is appended with the exact amount and the original value_date.
        """
        # Find target event
        target_event: Optional[Event] = None
        for ev in self.store.events:
            if ev.event_id == target_event_id and ev.account_id == account_id:
                target_event = ev
                break

        if target_event is None:
            raise ReversalError(f"Target event {target_event_id} not found for account {account_id}.")

        if target_event.event_type not in (EventType.DEBIT, EventType.SETTLEMENT, EventType.CREDIT):
            raise ReversalError(f"Cannot reverse event of type {target_event.event_type}.")

        desc = description or f"Reversal of {target_event_id} ({target_event.event_type.value} {target_event.amount.format()})"

        # If original was DEBIT/SETTLEMENT, reversal is a compensating credit (REVERSAL event)
        # Inherits target event's value_date if not explicitly overridden
        rev_event = self.store.append_event(
            event_id=event_id,
            event_type=EventType.REVERSAL,
            account_id=account_id,
            booking_day=booking_day,
            value_day=value_day,
            amount=target_event.amount,
            reference_event_id=target_event_id,
            description=desc,
        )

        return ReversalResult(
            reversal_event=rev_event,
            target_event_id=target_event_id,
            reversed_amount=target_event.amount,
        )
