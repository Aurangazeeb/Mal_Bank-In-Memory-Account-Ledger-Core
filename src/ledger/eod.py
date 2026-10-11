"""End-of-Day (EOD) processing, overdraft fee assessment, and interest engine.

Rules enforced:
1. Closing Ledger Balance: Evaluated per day as all posted entries with value_date <= that day,
   which have been booked on or before the evaluation time (booking_day <= current_day).
2. Overdraft fee: AED 25.00, assessed once per day per account when that day's closing
   ledger balance is negative. Booked with value_date equal to the day assessed (current_day).
3. Daily interest: 0.04% per day on the closing ledger balance, positive balances only.
   Accruals capitalize as a single credit at end of Day 6.
   The rounded daily accruals must sum exactly to the capitalized total.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Dict, List, Optional

from src.ledger.events import Event, EventType
from src.ledger.money import Currency, Money
from src.ledger.store import EventStore


OVERDRAFT_FEE_AED = Money.from_major("25.00", Currency.AED)
DAILY_INTEREST_RATE = Decimal("0.0004")  # 0.04% per day


@dataclass
class DailyAccrualRecord:
    """Record of daily interest accrued for an account."""
    day: int
    account_id: str
    closing_balance: Money
    accrued_interest: Money


@dataclass
class DailyEODSnapshot:
    """End-of-day state summary for an account."""
    day: int
    account_id: str
    currency: Currency
    closing_ledger_balance_before_fees: Money
    overdraft_fee_assessed: Optional[Money]
    closing_ledger_balance_after_fees: Money
    interest_accrued: Money
    available_balance: Money


class EODEngine:
    """Orchestrates end-of-day procedures: balance evaluation, fee assessment, and interest."""

    def __init__(self, store: EventStore) -> None:
        self.store = store
        # Track daily accruals: account_id -> list of DailyAccrualRecord
        self._accruals: Dict[str, List[DailyAccrualRecord]] = {}
        # Track fee assessments to prevent duplicate assessments per day: (account_id, day) -> Event
        self._assessed_fees: Dict[tuple[str, int], Event] = {}

    def get_closing_ledger_balance(
        self,
        account_id: str,
        current_day: int,
        target_value_day: Optional[int] = None,
    ) -> Money:
        """Computes closing ledger balance.
        
        Considers all entries booked on or before `current_day` with `value_day` <= `target_value_day`.
        If target_value_day is not provided, defaults to current_day.
        """
        val_day = target_value_day if target_value_day is not None else current_day
        return self.store.calculate_ledger_balance(
            account_id=account_id,
            as_of_booking_day=current_day,
            as_of_value_day=val_day,
        )

    def process_daily_overdraft_fee(self, account_id: str, day: int) -> Optional[Event]:
        """Assess overdraft fee if that day's closing ledger balance is negative.
        
        Rule: "Overdraft fee: AED 25.00, assessed once per day per account when that day's
        closing ledger balance (all entries with value_date <= that day) is negative.
        Booked with value_date equal to the day assessed."
        """
        account = self.store.get_account(account_id)
        if account.currency != Currency.AED:
            # Overdraft fee rule specifically states AED 25.00
            return None

        key = (account_id, day)
        if key in self._assessed_fees:
            # Assessed at most once per day per account
            return None

        # Check closing ledger balance before assessing fee
        closing_bal = self.get_closing_ledger_balance(account_id, current_day=day, target_value_day=day)

        if closing_bal.is_negative():
            fee_event = self.store.append_event(
                event_id=f"FEE-D{day}-{account_id}",
                event_type=EventType.FEE_ASSESSMENT,
                account_id=account_id,
                booking_day=day,
                value_day=day,
                amount=OVERDRAFT_FEE_AED,
                description=f"Overdraft fee assessed on Day {day} (closing balance: {closing_bal.format()})",
            )
            self._assessed_fees[key] = fee_event
            return fee_event

        return None

    def accrue_daily_interest(self, account_id: str, day: int) -> DailyAccrualRecord:
        """Calculates and records daily interest on positive closing ledger balance.
        
        Rule: "Daily interest: 0.04% per day on the closing ledger balance, positive balances only.
        The rounded daily accruals must sum exactly to the capitalized total."
        """
        account = self.store.get_account(account_id)
        closing_bal = self.get_closing_ledger_balance(account_id, current_day=day, target_value_day=day)

        if closing_bal.is_positive():
            # Calculate raw interest in major currency units
            raw_interest = closing_bal.amount * DAILY_INTEREST_RATE
            # Round to currency precision using standard banker's rounding (ROUND_HALF_EVEN)
            factor = Decimal(account.currency.subunit_factor)
            minor_units = int((raw_interest * factor).to_integral_value(rounding=ROUND_HALF_EVEN))
            accrued = Money(subunits=minor_units, currency=account.currency)
        else:
            accrued = Money.zero(account.currency)

        record = DailyAccrualRecord(
            day=day,
            account_id=account_id,
            closing_balance=closing_bal,
            accrued_interest=accrued,
        )
        self._accruals.setdefault(account_id, []).append(record)
        return record

    def capitalize_interest(self, account_id: str, day: int) -> Optional[Event]:
        """Capitalizes accumulated daily interest as a single credit at end of Day 6.
        
        Enforces non-negotiable rule: "The rounded daily accruals must sum exactly to the capitalized total."
        """
        accrual_list = self._accruals.get(account_id, [])
        if not accrual_list:
            return None

        account = self.store.get_account(account_id)
        # Sum of rounded daily accruals
        total_subunits = sum(rec.accrued_interest.subunits for rec in accrual_list)
        total_interest = Money(subunits=total_subunits, currency=account.currency)

        if total_interest.is_positive():
            event = self.store.append_event(
                event_id=f"INT-CAP-D{day}-{account_id}",
                event_type=EventType.INTEREST_CREDIT,
                account_id=account_id,
                booking_day=day,
                value_day=day,
                amount=total_interest,
                description=f"Interest capitalized at end of Day {day} summing {len(accrual_list)} daily accruals.",
            )
            return event

        return None

    def execute_eod(self, account_id: str, day: int) -> DailyEODSnapshot:
        """Executes full End-of-Day sequence for an account on a given day.
        
        Sequence:
          1. Evaluate closing ledger balance before fees (value_date <= day, booking_day <= day).
          2. Assess daily overdraft fee if balance is negative.
          3. Evaluate closing ledger balance after fee.
          4. Accrue daily interest on positive closing balance.
          5. If day == 6, capitalize accumulated interest as single credit.
          6. Return complete snapshot.
        """
        account = self.store.get_account(account_id)

        # 1. Closing ledger balance before fees
        bal_before = self.get_closing_ledger_balance(account_id, current_day=day, target_value_day=day)

        # 2. Overdraft fee assessment
        fee_event = self.process_daily_overdraft_fee(account_id, day)
        fee_amount = fee_event.amount if fee_event else None

        # 3. Closing ledger balance after fee
        bal_after = self.get_closing_ledger_balance(account_id, current_day=day, target_value_day=day)

        # 4. Accrue daily interest on post-fee closing balance
        accrual_record = self.accrue_daily_interest(account_id, day)

        # 5. Day 6 Capitalization
        if day == 6:
            self.capitalize_interest(account_id, day)
            # Recompute closing balance after interest credit capitalization
            bal_after = self.get_closing_ledger_balance(account_id, current_day=day, target_value_day=day)

        # 6. Available balance at EOD
        avail = self.store.calculate_available_balance(account_id, as_of_booking_day=day)

        return DailyEODSnapshot(
            day=day,
            account_id=account_id,
            currency=account.currency,
            closing_ledger_balance_before_fees=bal_before,
            overdraft_fee_assessed=fee_amount,
            closing_ledger_balance_after_fees=bal_after,
            interest_accrued=accrual_record.accrued_interest,
            available_balance=avail,
        )
