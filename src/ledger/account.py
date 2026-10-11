"""Account state projection and hold management.

Maintains strict bifurcation between:
  1. Ledger Balance: Sum of all posted credits minus posted debits.
  2. Available Balance: Ledger Balance minus active authorization holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from src.ledger.money import Currency, Money


@dataclass
class AuthorizationHold:
    """Represents an active hold placed on an account's available funds."""
    auth_id: str
    account_id: str
    day_placed: int
    amount: Money
    is_active: bool = True
    settlement_event_id: Optional[str] = None


@dataclass
class Account:
    """Account projection tracking currency, opening balance, and active holds."""
    account_id: str
    currency: Currency
    opening_balance: Money

    # Active holds indexed by auth_id
    holds: Dict[str, AuthorizationHold] = field(default_factory=dict)

    @classmethod
    def create(cls, account_id: str, currency: Currency) -> Account:
        return cls(
            account_id=account_id,
            currency=currency,
            opening_balance=Money.zero(currency),
        )

    def total_active_holds(self) -> Money:
        """Sum of all currently active authorization holds."""
        total = Money.zero(self.currency)
        for hold in self.holds.values():
            if hold.is_active:
                total += hold.amount
        return total
