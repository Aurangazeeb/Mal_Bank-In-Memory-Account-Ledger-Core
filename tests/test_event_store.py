import unittest
from decimal import Decimal

from src.ledger.events import AuthStatus, EventType
from src.ledger.money import Currency, Money
from src.ledger.store import CurrencyMismatchError, EventStore


class TestEventStoreAndBalances(unittest.TestCase):
    def setUp(self):
        self.store = EventStore()
        self.store.register_account("ACC-001", Currency.AED)
        self.store.register_account("ACC-002", Currency.BHD)

    def test_account_creation_opening_balance(self):
        acc = self.store.get_account("ACC-001")
        self.assertEqual(acc.currency, Currency.AED)
        self.assertEqual(acc.opening_balance, Money.zero(Currency.AED))
        self.assertEqual(acc.total_active_holds(), Money.zero(Currency.AED))

    def test_append_only_event_stream_immutability(self):
        e1 = self.store.append_event(
            event_id="E1",
            event_type=EventType.CREDIT,
            account_id="ACC-001",
            booking_day=1,
            value_day=1,
            amount=Money.from_major("1200.00", Currency.AED),
        )
        self.assertEqual(e1.sequence_id, 1)
        self.assertEqual(len(self.store.events), 1)

        # Immutability check: cannot reassign frozen dataclass attribute
        with self.assertRaises(Exception):
            e1.amount = Money.from_major("1500.00", Currency.AED)  # type: ignore

    def test_credit_debit_ledger_balance(self):
        # E1: Credit 1200.00
        self.store.append_event(
            event_id="E1",
            event_type=EventType.CREDIT,
            account_id="ACC-001",
            booking_day=1,
            value_day=1,
            amount=Money.from_major("1200.00", Currency.AED),
        )
        # E2: Debit 950.00
        self.store.append_event(
            event_id="E2",
            event_type=EventType.DEBIT,
            account_id="ACC-001",
            booking_day=1,
            value_day=1,
            amount=Money.from_major("950.00", Currency.AED),
        )

        bal = self.store.calculate_ledger_balance("ACC-001")
        self.assertEqual(bal, Money.from_major("250.00", Currency.AED))

    def test_authorization_holds_affect_available_not_ledger(self):
        # Credit 1200, Debit 950 -> Ledger = 250
        self.store.append_event("E1", EventType.CREDIT, "ACC-001", 1, 1, Money.from_major("1200.00", Currency.AED))
        self.store.append_event("E2", EventType.DEBIT, "ACC-001", 1, 1, Money.from_major("950.00", Currency.AED))

        # E3: Auth-A hold 200.00
        res = self.store.request_authorization(
            auth_id="Auth-A",
            account_id="ACC-001",
            day=2,
            amount=Money.from_major("200.00", Currency.AED),
        )
        self.assertEqual(res.status, AuthStatus.APPROVED)
        self.assertEqual(res.available_after, Money.from_major("50.00", Currency.AED))

        # Ledger balance must remain 250.00 (holds do not affect ledger balance)
        ledger_bal = self.store.calculate_ledger_balance("ACC-001")
        self.assertEqual(ledger_bal, Money.from_major("250.00", Currency.AED))

        # Available balance must reflect hold deduction: 250 - 200 = 50.00
        avail_bal = self.store.calculate_available_balance("ACC-001")
        self.assertEqual(avail_bal, Money.from_major("50.00", Currency.AED))

    def test_rule_5_authorization_declined_when_insufficient_available(self):
        # Starting ledger: 250.00. Auth-A holds 200.00 -> Available = 50.00
        self.store.append_event("E1", EventType.CREDIT, "ACC-001", 1, 1, Money.from_major("1200.00", Currency.AED))
        self.store.append_event("E2", EventType.DEBIT, "ACC-001", 1, 1, Money.from_major("950.00", Currency.AED))
        self.store.request_authorization("Auth-A", "ACC-001", 2, Money.from_major("200.00", Currency.AED))

        # Request Auth-X for 60.00 (50.00 available - 60.00 = -10.00 < 0)
        res = self.store.request_authorization(
            auth_id="Auth-X",
            account_id="ACC-001",
            day=2,
            amount=Money.from_major("60.00", Currency.AED),
        )
        self.assertEqual(res.status, AuthStatus.DECLINED)
        self.assertEqual(res.available_after, Money.from_major("50.00", Currency.AED))

        # Account holds should not include Auth-X
        acc = self.store.get_account("ACC-001")
        self.assertNotIn("Auth-X", acc.holds)

    def test_currency_mismatch_rejected(self):
        with self.assertRaises(CurrencyMismatchError):
            self.store.append_event(
                "ERR-1",
                EventType.CREDIT,
                "ACC-001",
                1,
                1,
                Money.from_major("10.000", Currency.BHD),
            )


if __name__ == "__main__":
    unittest.main()
