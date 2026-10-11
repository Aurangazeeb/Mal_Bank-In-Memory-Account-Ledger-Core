"""Six-day event stream replay engine and daily reporting.

Replays events E1 through E10 across Day 1 to Day 6 in exact specification order:
E1 — Day 1 — CREDIT — ACC-001 AED 1,200.00 — value_date Day 1
E2 — Day 1 — DEBIT — ACC-001 AED 950.00 — value_date Day 1
E3 — Day 2 — AUTHORIZATION — ACC-001 Auth-A hold AED 200.00 — value_date Day 2
E4 — Day 3 — CREDIT — ACC-001 AED 400.00 — value_date Day 3
E5 — Day 4 — SETTLEMENT — ACC-001 Auth-A settles for AED 185.00 — value_date Day 4
E6 — Day 4 — SETTLEMENT — ACC-001 Auth-Z settles for AED 180.00 — value_date Day 4 (Auth-Z has no preceding auth)
E7 — Day 5 — DEBIT — ACC-001 AED 620.00 — value_date Day 2
E8 — Day 5 — AUTHORIZATION — ACC-001 Auth-B hold AED 90.00 — value_date Day 5
E9 — Day 6 — REVERSAL — ACC-001 reverses E7 — value_date Day 2
E10 — Day 5 — CREDIT — ACC-002 BHD 10.000, posted as three equal instalments — value_date Day 5

Auth-B is never settled inside the window.

Per-day reporting:
- Closing ledger balance
- Fee assessments
- Authorization states
- Errors / warnings
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.ledger.clearing import ClearingEngine
from src.ledger.eod import DailyEODSnapshot, EODEngine
from src.ledger.events import AuthStatus, Event, EventType
from src.ledger.money import Currency, Money, allocate_instalments
from src.ledger.store import AuthorizationResult, EventStore


@dataclass
class DailyReport:
    day: int
    snapshots: Dict[str, DailyEODSnapshot]
    authorizations: List[AuthorizationResult]
    operational_notices: List[str]
    booked_events: List[Event]


class LedgerReplayEngine:
    """Executes the canonical six-day event stream replay and prints daily reports."""

    def __init__(self) -> None:
        self.store = EventStore()
        self.clearing = ClearingEngine(self.store)
        self.eod = EODEngine(self.store)

        # Accounts setup
        self.store.register_account("ACC-001", Currency.AED)
        self.store.register_account("ACC-002", Currency.BHD)

        self.reports: Dict[int, DailyReport] = {}

    def run_replay(self) -> Dict[int, DailyReport]:
        """Runs the 6-day replay from Day 1 through Day 6."""
        for day in range(1, 7):
            self.replay_day(day)
        return self.reports

    def replay_day(self, day: int) -> DailyReport:
        notices: List[str] = []
        auth_results: List[AuthorizationResult] = []
        events_booked: List[Event] = []

        if day == 1:
            # E1 — Day 1 — CREDIT — ACC-001 AED 1,200.00 — value_date Day 1
            e1 = self.store.append_event(
                event_id="E1",
                event_type=EventType.CREDIT,
                account_id="ACC-001",
                booking_day=1,
                value_day=1,
                amount=Money.from_major("1200.00", Currency.AED),
                description="Opening cash credit",
            )
            events_booked.append(e1)

            # E2 — Day 1 — DEBIT — ACC-001 AED 950.00 — value_date Day 1
            e2 = self.store.append_event(
                event_id="E2",
                event_type=EventType.DEBIT,
                account_id="ACC-001",
                booking_day=1,
                value_day=1,
                amount=Money.from_major("950.00", Currency.AED),
                description="POS purchase debit",
            )
            events_booked.append(e2)

        elif day == 2:
            # E3 — Day 2 — AUTHORIZATION — ACC-001 Auth-A hold AED 200.00 — value_date Day 2
            auth_a = self.store.request_authorization(
                auth_id="Auth-A",
                account_id="ACC-001",
                day=2,
                amount=Money.from_major("200.00", Currency.AED),
            )
            auth_results.append(auth_a)

        elif day == 3:
            # E4 — Day 3 — CREDIT — ACC-001 AED 400.00 — value_date Day 3
            e4 = self.store.append_event(
                event_id="E4",
                event_type=EventType.CREDIT,
                account_id="ACC-001",
                booking_day=3,
                value_day=3,
                amount=Money.from_major("400.00", Currency.AED),
                description="Salary transfer credit",
            )
            events_booked.append(e4)

        elif day == 4:
            # E5 — Day 4 — SETTLEMENT — ACC-001 Auth-A settles for AED 185.00 — value_date Day 4
            settle_e5 = self.clearing.process_settlement(
                event_id="E5",
                account_id="ACC-001",
                auth_id="Auth-A",
                booking_day=4,
                value_day=4,
                amount=Money.from_major("185.00", Currency.AED),
            )
            events_booked.append(settle_e5.settlement_event)
            if settle_e5.operational_alert:
                notices.append(settle_e5.operational_alert)

            # E6 — Day 4 — SETTLEMENT — ACC-001 Auth-Z settles for AED 180.00 — value_date Day 4 (no preceding auth)
            settle_e6 = self.clearing.process_settlement(
                event_id="E6",
                account_id="ACC-001",
                auth_id="Auth-Z",
                booking_day=4,
                value_day=4,
                amount=Money.from_major("180.00", Currency.AED),
            )
            events_booked.append(settle_e6.settlement_event)
            if settle_e6.operational_alert:
                notices.append(settle_e6.operational_alert)

        elif day == 5:
            # E7 — Day 5 — DEBIT — ACC-001 AED 620.00 — value_date Day 2
            e7 = self.store.append_event(
                event_id="E7",
                event_type=EventType.DEBIT,
                account_id="ACC-001",
                booking_day=5,
                value_day=2,
                amount=Money.from_major("620.00", Currency.AED),
                description="Late offline clearing debit (back-dated value_date Day 2)",
            )
            events_booked.append(e7)
            notices.append(
                "BACK_DATED_ENTRY: E7 posted on Day 5 with value_date Day 2. Evaluates retroactively on ledger balances."
            )

            # E8 — Day 5 — AUTHORIZATION — ACC-001 Auth-B hold AED 90.00 — value_date Day 5
            # Under Rule 5: approved ONLY if available balance remains >= 0
            # Ledger balance is 1200 - 950 + 400 - 185 - 180 - 620 = -335.00 AED
            # Available balance is -335.00 AED.
            # Available balance - 90.00 = -425.00 < 0 -> MUST BE DECLINED.
            auth_b = self.store.request_authorization(
                auth_id="Auth-B",
                account_id="ACC-001",
                day=5,
                amount=Money.from_major("90.00", Currency.AED),
            )
            auth_results.append(auth_b)
            if auth_b.status == AuthStatus.DECLINED:
                notices.append(f"DECLINE: Auth-B for AED 90.00 was DECLINED. {auth_b.reason}")

            # E10 — Day 5 — CREDIT — ACC-002 BHD 10.000, posted as three equal instalments — value_date Day 5
            # 10.000 BHD divided into 3 instalments: [3.334, 3.333, 3.333] BHD
            bhd_total = Money.from_major("10.000", Currency.BHD)
            instalments = allocate_instalments(bhd_total, 3)
            for idx, inst in enumerate(instalments, start=1):
                e10_inst = self.store.append_event(
                    event_id=f"E10-INST-{idx}",
                    event_type=EventType.CREDIT,
                    account_id="ACC-002",
                    booking_day=5,
                    value_day=5,
                    amount=inst,
                    description=f"Instalment {idx}/3 of E10 10.000 BHD",
                )
                events_booked.append(e10_inst)

        elif day == 6:
            # E9 — Day 6 — REVERSAL — ACC-001 reverses E7 — value_date Day 2
            rev_e9 = self.clearing.process_reversal(
                event_id="E9",
                account_id="ACC-001",
                target_event_id="E7",
                booking_day=6,
                value_day=2,
                description="Reversal of erroneous debit E7",
            )
            events_booked.append(rev_e9.reversal_event)
            notices.append(
                "COMPENSATING_REVERSAL: E9 posted on Day 6 reversing E7 with value_date Day 2 (audit record preserved)."
            )

        # Execute EOD for all accounts
        snapshots: Dict[str, DailyEODSnapshot] = {}
        for acc_id in ("ACC-001", "ACC-002"):
            snap = self.eod.execute_eod(acc_id, day=day)
            snapshots[acc_id] = snap
            if snap.overdraft_fee_assessed:
                notices.append(
                    f"FEE_ASSESSED: {acc_id} incurred {snap.overdraft_fee_assessed.format()} overdraft fee on Day {day}."
                )

        report = DailyReport(
            day=day,
            snapshots=snapshots,
            authorizations=auth_results,
            operational_notices=notices,
            booked_events=events_booked,
        )
        self.reports[day] = report
        return report

    def format_daily_report(self, day: int) -> str:
        """Renders the required daily output format."""
        report = self.reports[day]
        lines: List[str] = []
        lines.append("=" * 78)
        lines.append(f"DAY {day} CLOSE-OF-BUSINESS LEDGER REPORT")
        lines.append("=" * 78)

        # 1. Closing Ledger Balance & Snapshots
        lines.append("\n[1] CLOSING LEDGER BALANCES:")
        for acc_id in sorted(report.snapshots.keys()):
            snap = report.snapshots[acc_id]
            fee_str = f" [Overdraft Fee: {snap.overdraft_fee_assessed.format()}]" if snap.overdraft_fee_assessed else ""
            lines.append(
                f"  * {acc_id} ({snap.currency.value}): "
                f"Closing Balance: {snap.closing_ledger_balance_after_fees.format()} | "
                f"Available: {snap.available_balance.format()}{fee_str}"
            )
            if snap.interest_accrued.is_positive():
                lines.append(f"    - Daily Interest Accrued: {snap.interest_accrued.format()}")

        # 2. Fee Assessments
        lines.append("\n[2] FEE ASSESSMENTS:")
        fee_count = 0
        for acc_id, snap in report.snapshots.items():
            if snap.overdraft_fee_assessed:
                fee_count += 1
                lines.append(f"  * {acc_id}: Assessed {snap.overdraft_fee_assessed.format()} (Closing balance negative)")
        if fee_count == 0:
            lines.append("  * None assessed.")

        # 3. Authorization States
        lines.append("\n[3] AUTHORIZATION STATES:")
        if report.authorizations:
            for auth in report.authorizations:
                lines.append(
                    f"  * {auth.auth_id} ({auth.account_id}): {auth.status.value} for {auth.requested_amount.format()} "
                    f"[Avail before: {auth.available_before.format()}, after: {auth.available_after.format()}]"
                )
                if auth.reason:
                    lines.append(f"    Reason: {auth.reason}")
        else:
            lines.append("  * No authorization requests on this day.")

        # Active holds summary
        lines.append("  Active Holds at EOD:")
        has_active_holds = False
        for acc_id in sorted(report.snapshots.keys()):
            acc = self.store.get_account(acc_id)
            for h in acc.holds.values():
                if h.day_placed <= day and (not h.settlement_event_id or day < 4):
                    # Check if hold was active on this day
                    # For EOD report of Day 2 and Day 3, Auth-A is active
                    if h.day_placed <= day and (h.is_active or (h.settlement_event_id and day < 4)):
                        has_active_holds = True
                        lines.append(f"    - {acc_id}: Hold {h.auth_id} = {h.amount.format()} (placed Day {h.day_placed})")
        if not has_active_holds:
            lines.append("    - None active.")

        # 4. Operational Notices & Errors
        lines.append("\n[4] OPERATIONAL NOTICES & EXCEPTIONS:")
        if report.operational_notices:
            for notice in report.operational_notices:
                lines.append(f"  ! {notice}")
        else:
            lines.append("  * Normal processing — zero errors or warnings.")

        lines.append("-" * 78)
        return "\n".join(lines)

    def print_all_reports(self) -> None:
        """Print all 6 days sequentially."""
        for d in range(1, 7):
            print(self.format_daily_report(d))
            print()
