"""Append-only EventStore and projection engine.

Guarantees:
  1. Immutability: Events are appended sequentially; never modified or deleted.
  2. Point-in-time and value-dated balance projections.
  3. Strict Rule 5 enforcement: An authorization is approved ONLY if
     available balance (ledger balance minus active holds) remains >= 0 after hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.ledger.account import Account, AuthorizationHold
from src.ledger.events import AuthStatus, Event, EventType
from src.ledger.money import Currency, Money


class LedgerError(Exception):
    """Base exception for ledger operations."""
    pass


class AccountNotFoundError(LedgerError):
    pass


class CurrencyMismatchError(LedgerError):
    pass


@dataclass
class AuthorizationResult:
    status: AuthStatus
    auth_id: str
    account_id: str
    requested_amount: Money
    available_before: Money
    available_after: Money
    reason: str = ""


class EventStore:
    """In-memory append-only event store and balance projector."""

    def __init__(self) -> None:
        self._events: List[Event] = []
        self._accounts: Dict[str, Account] = {}
        self._auth_log: List[AuthorizationResult] = []
        self._next_sequence_id: int = 1

    @property
    def events(self) -> Tuple[Event, ...]:
        """Immutable view of the append-only event log."""
        return tuple(self._events)

    def register_account(self, account_id: str, currency: Currency) -> Account:
        """Register a new account with opening balance 0."""
        if account_id in self._accounts:
            raise LedgerError(f"Account {account_id} already exists.")
        account = Account.create(account_id, currency)
        self._accounts[account_id] = account
        return account

    def get_account(self, account_id: str) -> Account:
        if account_id not in self._accounts:
            raise AccountNotFoundError(f"Account {account_id} not found.")
        return self._accounts[account_id]

    def has_account(self, account_id: str) -> bool:
        return account_id in self._accounts

    def append_event(
        self,
        event_id: str,
        event_type: EventType,
        account_id: str,
        booking_day: int,
        value_day: int,
        amount: Money,
        auth_id: Optional[str] = None,
        reference_event_id: Optional[str] = None,
        description: str = "",
    ) -> Event:
        """Append an immutable event to the ledger."""
        account = self.get_account(account_id)
        if amount.currency != account.currency:
            raise CurrencyMismatchError(
                f"Amount currency {amount.currency} does not match account {account.currency}"
            )

        seq = self._next_sequence_id
        self._next_sequence_id += 1

        event = Event(
            sequence_id=seq,
            event_id=event_id,
            event_type=event_type,
            account_id=account_id,
            booking_day=booking_day,
            value_day=value_day,
            amount=amount,
            auth_id=auth_id,
            reference_event_id=reference_event_id,
            description=description,
        )
        self._events.append(event)
        return event

    def request_authorization(
        self,
        auth_id: str,
        account_id: str,
        day: int,
        amount: Money,
    ) -> AuthorizationResult:
        """Process an authorization request under Rule 5.
        
        Rule 5: An authorization is approved only if the account's available balance —
        ledger balance minus active holds — remains at or above zero after the hold is applied.
        """
        account = self.get_account(account_id)
        if amount.currency != account.currency:
            raise CurrencyMismatchError("Currency mismatch on authorization request.")

        # Compute current ledger balance booked up to this day
        # In real-time authorization, balance is evaluated against all posted entries known on `day`
        current_ledger = self.calculate_ledger_balance(account_id=account_id, as_of_booking_day=day)
        current_active_holds = account.total_active_holds()
        available_before = current_ledger - current_active_holds

        available_after = available_before - amount

        if available_after.subunits >= 0:
            # Approved: Place hold
            hold = AuthorizationHold(
                auth_id=auth_id,
                account_id=account_id,
                day_placed=day,
                amount=amount,
                is_active=True,
            )
            account.holds[auth_id] = hold

            # Append authorization event for audit trail
            self.append_event(
                event_id=f"AUTH-{auth_id}",
                event_type=EventType.AUTHORIZATION,
                account_id=account_id,
                booking_day=day,
                value_day=day,
                amount=amount,
                auth_id=auth_id,
                description=f"Authorization approved: hold {amount.format()} placed.",
            )

            res = AuthorizationResult(
                status=AuthStatus.APPROVED,
                auth_id=auth_id,
                account_id=account_id,
                requested_amount=amount,
                available_before=available_before,
                available_after=available_after,
                reason="Sufficient available balance.",
            )
        else:
            # Declined: Insufficient available funds
            res = AuthorizationResult(
                status=AuthStatus.DECLINED,
                auth_id=auth_id,
                account_id=account_id,
                requested_amount=amount,
                available_before=available_before,
                available_after=available_before,  # Unchanged
                reason=f"Insufficient funds: available {available_before.format()} < hold {amount.format()}",
            )

        self._auth_log.append(res)
        return res

    def calculate_ledger_balance(
        self,
        account_id: str,
        as_of_booking_day: Optional[int] = None,
        as_of_value_day: Optional[int] = None,
    ) -> Money:
        """Calculate posted ledger balance for an account.
        
        Filtering options:
          - as_of_booking_day: Consider only events booked on or before this day.
          - as_of_value_day: Consider only events with value_day on or before this day.
        """
        account = self.get_account(account_id)
        balance = account.opening_balance

        for ev in self._events:
            if ev.account_id != account_id:
                continue

            if as_of_booking_day is not None and ev.booking_day > as_of_booking_day:
                continue

            if as_of_value_day is not None and ev.value_day > as_of_value_day:
                continue

            # Event impact on ledger balance
            if ev.event_type in (EventType.CREDIT, EventType.REVERSAL, EventType.INTEREST_CREDIT):
                balance += ev.amount
            elif ev.event_type in (EventType.DEBIT, EventType.SETTLEMENT, EventType.FEE_ASSESSMENT):
                balance -= ev.amount
            elif ev.event_type == EventType.AUTHORIZATION:
                # Holds NEVER affect ledger balance directly
                pass

        return balance

    def calculate_available_balance(
        self,
        account_id: str,
        as_of_booking_day: Optional[int] = None,
    ) -> Money:
        """Calculate available balance: ledger balance minus active authorization holds."""
        account = self.get_account(account_id)
        ledger = self.calculate_ledger_balance(account_id=account_id, as_of_booking_day=as_of_booking_day)
        return ledger - account.total_active_holds()
