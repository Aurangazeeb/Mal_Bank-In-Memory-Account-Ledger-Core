from decimal import Decimal
import unittest
from src.ledger.money import Currency, Money, allocate_instalments


class TestMoney(unittest.TestCase):
    def test_currency_precisions(self):
        self.assertEqual(Currency.AED.precision, 2)
        self.assertEqual(Currency.AED.subunit_factor, 100)
        self.assertEqual(Currency.BHD.precision, 3)
        self.assertEqual(Currency.BHD.subunit_factor, 1000)

    def test_money_creation_and_formatting(self):
        aed = Money.from_major("1200.00", Currency.AED)
        self.assertEqual(aed.subunits, 120000)
        self.assertEqual(aed.amount, Decimal("1200.00"))
        self.assertEqual(aed.format(), "AED 1,200.00")

        bhd = Money.from_major("10.000", Currency.BHD)
        self.assertEqual(bhd.subunits, 10000)
        self.assertEqual(bhd.amount, Decimal("10.000"))
        self.assertEqual(bhd.format(), "BHD 10.000")

    def test_money_arithmetic(self):
        m1 = Money.from_major("50.25", Currency.AED)
        m2 = Money.from_major("25.50", Currency.AED)

        self.assertEqual(m1 + m2, Money.from_major("75.75", Currency.AED))
        self.assertEqual(m1 - m2, Money.from_major("24.75", Currency.AED))
        self.assertEqual(-m1, Money.from_major("-50.25", Currency.AED))
        self.assertEqual(abs(-m1), m1)

    def test_currency_isolation(self):
        aed = Money.from_major("100.00", Currency.AED)
        bhd = Money.from_major("100.000", Currency.BHD)

        with self.assertRaises(TypeError):
            _ = aed + bhd

        with self.assertRaises(TypeError):
            _ = aed - bhd

        with self.assertRaises(TypeError):
            _ = aed < bhd

    def test_instalment_allocation_conservation_e10(self):
        # E10: ACC-002 BHD 10.000 posted as three equal instalments
        total = Money.from_major("10.000", Currency.BHD)
        parts = allocate_instalments(total, 3)

        self.assertEqual(len(parts), 3)
        # Check that subunits sum to exactly 10,000
        self.assertEqual(sum(p.subunits for p in parts), 10000)

        # First instalment takes the remainder (3.334), next two are 3.333
        self.assertEqual(parts[0], Money.from_major("3.334", Currency.BHD))
        self.assertEqual(parts[1], Money.from_major("3.333", Currency.BHD))
        self.assertEqual(parts[2], Money.from_major("3.333", Currency.BHD))

        # Refutation of flawed criterion: 3.334 * 3 = 10.002 BHD (+0.002 loss/creation of money)
        self.assertEqual(sum(p.amount for p in parts), Decimal("10.000"))


if __name__ == "__main__":
    unittest.main()
