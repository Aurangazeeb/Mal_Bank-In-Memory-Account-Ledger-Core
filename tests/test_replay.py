import unittest
from decimal import Decimal

from src.ledger.events import AuthStatus, EventType
from src.ledger.money import Currency, Money
from src.ledger.replay import LedgerReplayEngine


class TestLedgerReplaySuite(unittest.TestCase):
    def setUp(self):
        self.engine = LedgerReplayEngine()
        self.reports = self.engine.run_replay()

    def test_day_1_closing_and_postings(self):
        # E1: Credit 1200, E2: Debit 950 -> Closing: 250.00
        snap1 = self.reports[1].snapshots["ACC-001"]
        self.assertEqual(snap1.closing_ledger_balance_after_fees, Money.from_major("250.00", Currency.AED))
        self.assertIsNone(snap1.overdraft_fee_assessed)
        # Interest on 250.00 at 0.04% = 0.10 AED
        self.assertEqual(snap1.interest_accrued, Money.from_major("0.10", Currency.AED))

    def test_day_2_auth_a_hold(self):
        # E3: Auth-A 200 hold placed
        snap2 = self.reports[2].snapshots["ACC-001"]
        self.assertEqual(snap2.closing_ledger_balance_after_fees, Money.from_major("250.00", Currency.AED))
        self.assertEqual(snap2.available_balance, Money.from_major("50.00", Currency.AED))
        self.assertIsNone(snap2.overdraft_fee_assessed)

        auth_a = self.reports[2].authorizations[0]
        self.assertEqual(auth_a.auth_id, "Auth-A")
        self.assertEqual(auth_a.status, AuthStatus.APPROVED)

    def test_day_3_credit_e4(self):
        # E4: Credit 400 -> Closing: 250 + 400 = 650.00
        snap3 = self.reports[3].snapshots["ACC-001"]
        self.assertEqual(snap3.closing_ledger_balance_after_fees, Money.from_major("650.00", Currency.AED))
        # Available: 650 - 200 (Auth-A hold) = 450.00
        self.assertEqual(snap3.available_balance, Money.from_major("450.00", Currency.AED))

    def test_day_4_settlement_e5_and_force_post_e6(self):
        # E5: Auth-A settles for 185 (hold 200 released)
        # E6: Auth-Z settles for 180 (force-post accepted)
        # Closing: 650 - 185 - 180 = 285.00
        snap4 = self.reports[4].snapshots["ACC-001"]
        self.assertEqual(snap4.closing_ledger_balance_after_fees, Money.from_major("285.00", Currency.AED))
        self.assertEqual(snap4.available_balance, Money.from_major("285.00", Currency.AED))

        # Check force-post notice in Day 4 report
        notices = self.reports[4].operational_notices
        self.assertTrue(any("FORCE_POST" in n and "Auth-Z" in n for n in notices))

    def test_day_5_e7_backdated_debit_auth_b_decline_and_fee(self):
        # E7: Debit 620 with value_date Day 2
        # Closing before fee: 285 - 620 = -335.00
        # Overdraft fee of 25.00 assessed -> Closing after fee: -360.00
        snap5 = self.reports[5].snapshots["ACC-001"]
        self.assertEqual(snap5.closing_ledger_balance_before_fees, Money.from_major("-335.00", Currency.AED))
        self.assertEqual(snap5.overdraft_fee_assessed, Money.from_major("25.00", Currency.AED))
        self.assertEqual(snap5.closing_ledger_balance_after_fees, Money.from_major("-360.00", Currency.AED))

        # Auth-B: declined because available balance (-335.00) - 90.00 < 0
        auth_b = self.reports[5].authorizations[0]
        self.assertEqual(auth_b.auth_id, "Auth-B")
        self.assertEqual(auth_b.status, AuthStatus.DECLINED)

        # Acceptance criterion: Day 2 closing balance evaluated at end of Day 5 before fee
        # Events with value_date <= Day 2 booked as of Day 5:
        # E1 (+1200), E2 (-950), E7 (-620) = 1200 - 950 - 620 = -370.00 AED
        day2_val_bal = self.engine.eod.get_closing_ledger_balance("ACC-001", current_day=5, target_value_day=2)
        self.assertEqual(day2_val_bal, Money.from_major("-370.00", Currency.AED))

    def test_day_5_e10_bhd_three_instalments_conservation(self):
        # ACC-002: E10 10.000 BHD posted as three instalments
        snap5_bhd = self.reports[5].snapshots["ACC-002"]
        self.assertEqual(snap5_bhd.closing_ledger_balance_after_fees, Money.from_major("10.000", Currency.BHD))

        # Check individual instalments in event store
        e10_events = [e for e in self.engine.store.events if e.account_id == "ACC-002" and e.booking_day == 5]
        self.assertEqual(len(e10_events), 3)
        self.assertEqual(e10_events[0].amount, Money.from_major("3.334", Currency.BHD))
        self.assertEqual(e10_events[1].amount, Money.from_major("3.333", Currency.BHD))
        self.assertEqual(e10_events[2].amount, Money.from_major("3.333", Currency.BHD))
        self.assertEqual(sum(e.amount.subunits for e in e10_events), 10000)

    def test_day_6_reversal_e9_and_interest_capitalization(self):
        # E9: Reversal of E7 (+620 credit with value_date Day 2)
        # Interest capitalized at end of Day 6
        snap6 = self.reports[6].snapshots["ACC-001"]
        # Pre-interest balance: -360 (from Day 5 post-fee) + 620 (E9) = 260.00 AED
        # Capitalized interest for Days 1-6 = 0.10 + 0.10 + 0.26 + 0.11 + 0.00 + 0.10 = 0.67 AED
        # Final closing balance = 260.00 + 0.67 = 260.67 AED
        self.assertEqual(snap6.closing_ledger_balance_after_fees, Money.from_major("260.67", Currency.AED))

        # Check BHD interest capitalized at end of Day 6
        # Day 5 interest: 10.000 * 0.0004 = 0.004 BHD
        # Day 6 interest: 10.000 * 0.0004 = 0.004 BHD
        # Capitalized: 0.008 BHD -> Final closing: 10.008 BHD
        snap6_bhd = self.reports[6].snapshots["ACC-002"]
        self.assertEqual(snap6_bhd.closing_ledger_balance_after_fees, Money.from_major("10.008", Currency.BHD))


if __name__ == "__main__":
    unittest.main()
