import unittest
from decimal import Decimal

from src.ledger.clearing import ClearingEngine, ReversalError
from src.ledger.eod import EODEngine
from src.ledger.events import AuthStatus, EventType
from src.ledger.money import Currency, Money
from src.ledger.store import EventStore


class TestClearingEngine(unittest.TestCase):
    def setUp(self):
        self.store = EventStore()
        self.store.register_account("ACC-001", Currency.AED)
        self.clearing = ClearingEngine(self.store)
        self.eod = EODEngine(self.store)

    def test_partial_settlement_releases_full_hold_e5(self):
        # Initial credit 1200.00
        self.store.append_event("E1", EventType.CREDIT, "ACC-001", 1, 1, Money.from_major("1200.00", Currency.AED))

        # E3: Auth-A for 200.00
        auth_res = self.store.request_authorization("Auth-A", "ACC-001", 2, Money.from_major("200.00", Currency.AED))
        self.assertEqual(auth_res.status, AuthStatus.APPROVED)

        acc = self.store.get_account("ACC-001")
        self.assertEqual(acc.total_active_holds(), Money.from_major("200.00", Currency.AED))

        # E5: Auth-A settles for 185.00 on Day 4
        settle_res = self.clearing.process_settlement(
            event_id="E5",
            account_id="ACC-001",
            auth_id="Auth-A",
            booking_day=4,
            value_day=4,
            amount=Money.from_major("185.00", Currency.AED),
        )

        self.assertFalse(settle_res.is_force_post)
        self.assertEqual(settle_res.hold_amount_released, Money.from_major("200.00", Currency.AED))
        self.assertEqual(settle_res.settled_amount, Money.from_major("185.00", Currency.AED))

        # Hold is no longer active
        self.assertEqual(acc.total_active_holds(), Money.zero(Currency.AED))

        # Ledger balance reflects 1200 - 185 = 1015.00
        bal = self.store.calculate_ledger_balance("ACC-001")
        self.assertEqual(bal, Money.from_major("1015.00", Currency.AED))

    def test_force_post_settlement_without_prior_auth_e6(self):
        # E6: Auth-Z settles for 180.00 on Day 4 with NO prior auth
        settle_res = self.clearing.process_settlement(
            event_id="E6",
            account_id="ACC-001",
            auth_id="Auth-Z",
            booking_day=4,
            value_day=4,
            amount=Money.from_major("180.00", Currency.AED),
        )

        self.assertTrue(settle_res.is_force_post)
        self.assertIsNotNone(settle_res.operational_alert)
        self.assertIn("FORCE_POST", settle_res.operational_alert)

        # Funds MUST leave the account (debit posted) per clearing obligations
        bal = self.store.calculate_ledger_balance("ACC-001")
        self.assertEqual(bal, Money.from_major("-180.00", Currency.AED))

    def test_reversal_append_only_e9_reversing_e7(self):
        # Day 1: Credit 1200.00
        self.store.append_event("E1", EventType.CREDIT, "ACC-001", 1, 1, Money.from_major("1200.00", Currency.AED))
        # Day 5: E7 Debit 620.00 with value_date Day 2
        e7 = self.store.append_event("E7", EventType.DEBIT, "ACC-001", 5, 2, Money.from_major("620.00", Currency.AED))

        # Balance before reversal: 1200 - 620 = 580
        self.assertEqual(self.store.calculate_ledger_balance("ACC-001"), Money.from_major("580.00", Currency.AED))

        # Day 6: E9 reverses E7 with value_date Day 2
        rev_res = self.clearing.process_reversal(
            event_id="E9",
            account_id="ACC-001",
            target_event_id="E7",
            booking_day=6,
            value_day=2,
        )

        self.assertEqual(rev_res.target_event_id, "E7")
        self.assertEqual(rev_res.reversed_amount, Money.from_major("620.00", Currency.AED))

        # E7 is still in the store (immutability preserved)
        e7_lookup = [e for e in self.store.events if e.event_id == "E7"]
        self.assertEqual(len(e7_lookup), 1)

        # Final ledger balance restored to 1200.00
        self.assertEqual(self.store.calculate_ledger_balance("ACC-001"), Money.from_major("1200.00", Currency.AED))

    def test_reversal_invalid_target_raises_error(self):
        with self.assertRaises(ReversalError):
            self.clearing.process_reversal(
                event_id="E-REV-FAIL",
                account_id="ACC-001",
                target_event_id="NON_EXISTENT",
                booking_day=6,
                value_day=2,
            )


if __name__ == "__main__":
    unittest.main()
