import unittest
from decimal import Decimal

from src.ledger.eod import EODEngine, OVERDRAFT_FEE_AED
from src.ledger.events import EventType
from src.ledger.money import Currency, Money
from src.ledger.store import EventStore


class TestEODEngine(unittest.TestCase):
    def setUp(self):
        self.store = EventStore()
        self.store.register_account("ACC-001", Currency.AED)
        self.store.register_account("ACC-002", Currency.BHD)
        self.eod = EODEngine(self.store)

    def test_overdraft_fee_assessed_when_closing_balance_negative(self):
        # Day 1: Debit 100.00 -> balance -100.00
        self.store.append_event("E-NEG", EventType.DEBIT, "ACC-001", 1, 1, Money.from_major("100.00", Currency.AED))

        snap = self.eod.execute_eod("ACC-001", day=1)

        self.assertEqual(snap.closing_ledger_balance_before_fees, Money.from_major("-100.00", Currency.AED))
        self.assertEqual(snap.overdraft_fee_assessed, OVERDRAFT_FEE_AED)
        # After fee: -100 - 25 = -125.00
        self.assertEqual(snap.closing_ledger_balance_after_fees, Money.from_major("-125.00", Currency.AED))
        # No interest on negative balance
        self.assertEqual(snap.interest_accrued, Money.zero(Currency.AED))

    def test_overdraft_fee_assessed_at_most_once_per_day(self):
        # Balance is negative
        self.store.append_event("E-NEG", EventType.DEBIT, "ACC-001", 1, 1, Money.from_major("100.00", Currency.AED))

        # First evaluation assesses fee
        fee1 = self.eod.process_daily_overdraft_fee("ACC-001", day=1)
        self.assertIsNotNone(fee1)

        # Second evaluation on same day must be idempotent (None)
        fee2 = self.eod.process_daily_overdraft_fee("ACC-001", day=1)
        self.assertIsNone(fee2)

    def test_daily_interest_accrual_and_exact_capitalization_reconciliation(self):
        # Credit 10,000.00 AED on Day 1
        self.store.append_event("E-CR", EventType.CREDIT, "ACC-001", 1, 1, Money.from_major("10000.00", Currency.AED))

        # Run Days 1 to 6
        daily_accruals = []
        for d in range(1, 7):
            snap = self.eod.execute_eod("ACC-001", day=d)
            daily_accruals.append(snap.interest_accrued)

        # 10,000 * 0.0004 = 4.00 AED daily
        for acc in daily_accruals:
            self.assertEqual(acc, Money.from_major("4.00", Currency.AED))

        # Sum of 6 daily accruals = 24.00 AED
        expected_total = sum(daily_accruals, Money.zero(Currency.AED))
        self.assertEqual(expected_total, Money.from_major("24.00", Currency.AED))

        # Check capitalized event in store
        cap_events = [e for e in self.store.events if e.event_type == EventType.INTEREST_CREDIT]
        self.assertEqual(len(cap_events), 1)
        self.assertEqual(cap_events[0].amount, expected_total)
        # Verify exact sum rule
        self.assertEqual(cap_events[0].amount.subunits, sum(a.subunits for a in daily_accruals))

    def test_value_dated_closing_balance_temporal_isolation(self):
        # Event booked on Day 1 with value_date Day 3 (future value date)
        self.store.append_event("E-FUT", EventType.CREDIT, "ACC-001", 1, 3, Money.from_major("500.00", Currency.AED))

        # At Day 1 EOD (value_date <= 1), the future value-dated entry must NOT be counted
        bal_day1 = self.eod.get_closing_ledger_balance("ACC-001", current_day=1, target_value_day=1)
        self.assertEqual(bal_day1, Money.zero(Currency.AED))

        # At Day 3 EOD (value_date <= 3), it is now effective
        bal_day3 = self.eod.get_closing_ledger_balance("ACC-001", current_day=3, target_value_day=3)
        self.assertEqual(bal_day3, Money.from_major("500.00", Currency.AED))


if __name__ == "__main__":
    unittest.main()
