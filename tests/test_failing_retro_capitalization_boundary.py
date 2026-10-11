"""INTENTIONAL FAILING TEST — DEMONSTRATING ARCHITECTURAL BOUNDARY OF IN-MEMORY LEDGER CORE.

========================================================================================
PART 1 DELIVERABLE REQUIREMENT:
"One failing test against your own design, inline-annotated with what it reveals."
========================================================================================

ARCHITECTURAL BOUNDARY EXPOSED:
--------------------------------
"The Closed-Period Capitalization Invariant vs. Unbounded Retroactive Back-Dated Entries"

WHAT THIS REVEALS ABOUT THE CURRENT DESIGN:
------------------------------------------
1. In the current in-memory ledger engine, interest is calculated daily and capitalized as a
   single credit at the close of Day 6 based on the state known up to Day 6 close.
   This finalized event (INT-CAP-D6) is written to the immutable append-only ledger and sums
   the exact daily accruals (e.g. AED 0.67 for ACC-001).

2. In production banking, accounting periods close (monthly statement generation, regulatory
   reporting to CBUAE, and tax/audit certification). Once a period closes, its financial
   results are legally immutable.

3. BUT WHAT HAPPENS IF AN UNNOTIFIED BACK-DATED DEBIT ARRIVES ON DAY 7 WITH VALUE_DATE = DAY 1?
   Suppose an interbank clearing file arrives on Day 7 containing an offline debit of AED 1,000.00
   with value_date = Day 1.
   
   If we re-evaluate historical balances retroactively:
   - Day 1 closing balance drops from +250.00 to -750.00 AED.
   - Day 2 closing balance drops from +250.00 to -750.00 AED.
   - Day 3 closing balance drops from +650.00 to -350.00 AED.
   - The customer was NEVER eligible for the AED 0.67 interest that was already capitalized!
   - In fact, the customer was in overdraft across Days 1, 2, and 3, meaning overdraft fees
     SHOULD have been assessed.

4. THE SYSTEM TENSION / CORE LIMITATION:
   - The ledger cannot mutate or delete `INT-CAP-D6` because the ledger is append-only (Rule 4).
   - If an external system or auditor asserts that:
       assert sum(daily_accruals_recalculated_post_facto) == capitalized_event.amount
     the assertion FAILS!
   - Recalculated interest becomes AED 0.00, but capitalized credit in the ledger is AED 0.67.
   - Discrepancy: AED 0.67 phantom interest posted in a closed period.

5. WHY THIS CANNOT BE RESOLVED WITHOUT AN ENTERPRISE "PRIOR PERIOD ADJUSTMENT" SUBSYSTEM:
   To fix this in production, a bank CANNOT simply rewrite the Day 6 interest credit.
   It must introduce:
     a) A "Value-Dating Window Cutoff" policy (e.g. reject value dates older than N days).
     b) A "Prior-Period Interest Clawback" event (booked on Day 7, value_date Day 7) that
        debits the customer for the excess interest paid in the prior period.
     c) Retroactive overdraft surcharge assessment booked in the current period.

This test explicitly asserts post-facto consistency between historical accruals and the
locked capitalization event, deliberately failing to prove this boundary.
"""

import unittest
from decimal import Decimal

from src.ledger.events import EventType
from src.ledger.money import Currency, Money
from src.ledger.replay import LedgerReplayEngine


class TestRetroactiveCapitalizationBoundary(unittest.TestCase):
    """Failing test demonstrating that append-only ledgers cannot preserve both:
    1. Perfect retroactive restatement of daily accruals, AND
    2. Immutability of finalized/capitalized closed-period interest credits,
    without an explicit Prior-Period Adjustment (PPA) subsystem.
    """

    def test_backdated_debit_post_capitalization_breaks_accrual_conservation(self):
        # 1. Run the canonical 6-day replay
        engine = LedgerReplayEngine()
        engine.run_replay()

        # Day 6 is finalized: Capitalization credit event is committed to the ledger
        cap_events = [
            e for e in engine.store.events
            if e.account_id == "ACC-001" and e.event_type == EventType.INTEREST_CREDIT
        ]
        self.assertEqual(len(cap_events), 1)
        capitalized_interest_event = cap_events[0]
        # On Day 6, interest capitalized was AED 0.67
        self.assertEqual(capitalized_interest_event.amount, Money.from_major("0.67", Currency.AED))

        # 2. On Day 7, an unnotified back-dated clearing debit arrives:
        #    Amount: AED 1,000.00, value_date: Day 1, booking_day: Day 7
        engine.store.append_event(
            event_id="E-LATE-CLEARING",
            event_type=EventType.DEBIT,
            account_id="ACC-001",
            booking_day=7,
            value_day=1,
            amount=Money.from_major("1000.00", Currency.AED),
            description="Late clearing presentment arriving after Day 6 EOD with value_date Day 1",
        )

        # 3. An auditor or regulatory probe recalculates what the daily interest accruals
        #    SHOULD have been across Days 1 to 6 in light of the new value-dated information:
        recalculated_accruals = []
        for d in range(1, 7):
            # Recalculate closing ledger balance for Day d with all entries known as of Day 7
            closing_bal = engine.eod.get_closing_ledger_balance(
                account_id="ACC-001",
                current_day=7,
                target_value_day=d,
            )
            # Days 1 to 5 are now all negative due to the -1000 AED debit with value_date Day 1!
            # Day 1: 1200 - 950 - 1000 = -750.00 AED -> 0.00 interest
            # Day 2: 1200 - 950 - 1000 = -750.00 AED -> 0.00 interest
            # Day 3: 1200 - 950 - 1000 + 400 = -350.00 AED -> 0.00 interest
            # Day 4: 1200 - 950 - 1000 + 400 - 185 - 180 = -715.00 AED -> 0.00 interest
            # Day 5: -715 - 620 = -1335.00 AED -> 0.00 interest
            # Day 6: -1335 + 620 (E9 reversal) = -715.00 AED -> 0.00 interest
            if closing_bal.is_positive():
                raw = closing_bal.amount * Decimal("0.0004")
                factor = Decimal(Currency.AED.subunit_factor)
                minor = int((raw * factor).to_integral_value())
                accrued = Money(subunits=minor, currency=Currency.AED)
            else:
                accrued = Money.zero(Currency.AED)
            recalculated_accruals.append(accrued)

        sum_of_true_accruals = sum(recalculated_accruals, Money.zero(Currency.AED))

        # Under the new reality, total accrued interest across Days 1-6 was exactly AED 0.00:
        self.assertEqual(sum_of_true_accruals, Money.zero(Currency.AED))

        # =====================================================================================
        # INTENTIONAL FAILURE POINT:
        # Rule 2 states: "The rounded daily accruals must sum exactly to the capitalized total."
        #
        # Here, the append-only ledger already committed INT-CAP-D6 = AED 0.67 on Day 6.
        # But the sum of true daily accruals evaluated post-facto is AED 0.00!
        #
        # Because historical events cannot be mutated or deleted (Rule 4), the ledger cannot
        # retroactively erase or resize INT-CAP-D6.
        #
        # Therefore, this assertion FAILS:
        #   AED 0.00 (sum of actual accruals) != AED 0.67 (committed capitalization event)
        #
        # This proves that value-dated banking ledgers REQUIRE an operational control:
        # Either a hard cutoff window for retroactive value-dating, or a formal
        # Prior-Period Adjustment (PPA) interest-clawback mechanism.
        # =====================================================================================
        self.assertEqual(
            sum_of_true_accruals,
            capitalized_interest_event.amount,
            msg=(
                f"ARCHITECTURAL INVARIANT BREACH: Sum of post-facto daily accruals ({sum_of_true_accruals.format()}) "
                f"does not match previously finalized capitalization event ({capitalized_interest_event.amount.format()}). "
                f"An append-only ledger without Prior-Period Adjustment cannot reconcile closed periods "
                f"when unnotified back-dated debits arrive post-capitalization."
            ),
        )


if __name__ == "__main__":
    unittest.main()
