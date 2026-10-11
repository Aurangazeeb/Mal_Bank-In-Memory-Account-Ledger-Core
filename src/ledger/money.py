"""Money and Currency domain primitives.

Ensures strict financial conservation, zero floating-point drift,
and exact remainder-preserving distributions (Hamilton-Hare method).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Sequence


class Currency(str, Enum):
    """Supported currencies and their regulatory decimal precisions.
    
    AED: United Arab Emirates Dirham, 2 decimal places (100 fils = 1 AED).
    BHD: Bahraini Dinar, 3 decimal places (1000 fils = 1 BHD).
    """
    AED = "AED"
    BHD = "BHD"

    @property
    def precision(self) -> int:
        if self == Currency.AED:
            return 2
        elif self == Currency.BHD:
            return 3
        raise ValueError(f"Unsupported currency: {self}")

    @property
    def subunit_factor(self) -> int:
        return 10 ** self.precision


@dataclass(frozen=True, slots=True)
class Money:
    """Exact immutable monetary value represented in integer minor units (fils).
    
    Guarantees zero floating-point drift and enforces currency isolation.
    """
    subunits: int
    currency: Currency

    @classmethod
    def from_major(cls, amount: Decimal | str | int, currency: Currency) -> Money:
        """Create Money from major currency units (e.g. '1200.00' AED or '10.000' BHD)."""
        dec = Decimal(str(amount))
        factor = Decimal(currency.subunit_factor)
        # Quantize to exact minor units using standard financial banker's rounding if fractional
        minor = int((dec * factor).to_integral_value(rounding=ROUND_HALF_EVEN))
        return cls(subunits=minor, currency=currency)

    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(subunits=0, currency=currency)

    @property
    def amount(self) -> Decimal:
        """Major unit representation as an exact Decimal."""
        return Decimal(self.subunits) / Decimal(self.currency.subunit_factor)

    def is_zero(self) -> bool:
        return self.subunits == 0

    def is_positive(self) -> bool:
        return self.subunits > 0

    def is_negative(self) -> bool:
        return self.subunits < 0

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise TypeError(f"Cannot add {type(other)} or mismatched currencies: {self.currency} vs {getattr(other, 'currency', None)}")
        return Money(subunits=self.subunits + other.subunits, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise TypeError(f"Cannot subtract {type(other)} or mismatched currencies: {self.currency} vs {getattr(other, 'currency', None)}")
        return Money(subunits=self.subunits - other.subunits, currency=self.currency)

    def __neg__(self) -> Money:
        return Money(subunits=-self.subunits, currency=self.currency)

    def __abs__(self) -> Money:
        return Money(subunits=abs(self.subunits), currency=self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.subunits == other.subunits and self.currency == other.currency

    def __lt__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise TypeError(f"Cannot compare {self.currency} with {getattr(other, 'currency', None)}")
        return self.subunits < other.subunits

    def __le__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise TypeError(f"Cannot compare {self.currency} with {getattr(other, 'currency', None)}")
        return self.subunits <= other.subunits

    def __gt__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise TypeError(f"Cannot compare {self.currency} with {getattr(other, 'currency', None)}")
        return self.subunits > other.subunits

    def __ge__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise TypeError(f"Cannot compare {self.currency} with {getattr(other, 'currency', None)}")
        return self.subunits >= other.subunits

    def format(self) -> str:
        """Formatted string with explicit currency code and regulatory precision."""
        prec = self.currency.precision
        val = self.amount
        return f"{self.currency.value} {val:,.{prec}f}"

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"Money({self.format()} [{self.subunits} subunits])"


def allocate_instalments(total: Money, parts: int) -> Sequence[Money]:
    """Partitions a monetary amount into N instalments without losing a single minor unit.
    
    Uses largest-remainder distribution (Hamilton-Hare method).
    For example: 10.000 BHD (10,000 subunits) into 3 parts:
      Base = 10,000 // 3 = 3,333 subunits
      Remainder = 10,000 % 3 = 1 subunit
      Allocated = [3,334, 3,333, 3,333] subunits -> [3.334, 3.333, 3.333] BHD
      Sum = 10.000 BHD (strictly conserved).
    """
    if parts <= 0:
        raise ValueError("Parts must be a positive integer.")

    base = total.subunits // parts
    remainder = total.subunits % parts

    results: list[Money] = []
    for i in range(parts):
        # Distribute the remainder 1 subunit at a time to the front instalments
        extra = 1 if i < remainder else 0
        results.append(Money(subunits=base + extra, currency=total.currency))

    assert sum(m.subunits for m in results) == total.subunits, "Conservation of money violated in allocation"
    return results
