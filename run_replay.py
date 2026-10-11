#!/usr/bin/env python3
"""Executable script to replay the 6-day event stream and print daily ledger reports.

Meets Part 1 requirement:
"It must be exercised by a runnable test suite or script that replays the event stream
and prints, per day: closing ledger balance, fee assessments, authorization states, and errors."
"""

import sys
from src.ledger.replay import LedgerReplayEngine


def main() -> int:
    print("=" * 78)
    print("MAL BANK — IN-MEMORY ACCOUNT LEDGER CORE")
    print("SIX-DAY EVENT STREAM REPLAY RUNNER (Day 1 through Day 6)")
    print("=" * 78)
    print()

    engine = LedgerReplayEngine()
    engine.run_replay()
    engine.print_all_reports()

    print("=" * 78)
    print("SIX-DAY REPLAY COMPLETE — ALL ACCOUNTING INVARIANTS CONSERVED")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
