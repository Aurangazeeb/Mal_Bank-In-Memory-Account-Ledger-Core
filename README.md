# In-Memory Account Ledger Core

**Role:** Staff Software Engineer  
**Institution:** Mal Bank (UAE)  
**Submission Theme:** In-Memory Account Ledger Core (Part 1 & Part 2)  
**Implementation Language:** Pure Python 3 (Zero external dependencies; standard library + `unittest`)

---

## Executive Summary

This repository contains the production-grade implementation of an **In-Memory Account Ledger Core** designed to model double-entry event-sourced banking operations, dual-date accounting mechanics, exact currency math, card authorization lifecycles, and asynchronous clearing presentments.

### Key Architectural Characteristics
- **Conservation of Money:** Monetary values are modeled as immutable integer minor units (`subunits` = fils) to guarantee mathematical determinism and zero floating-point drift. Multi-instalment division uses the largest-remainder Hamilton-Hare algorithm to guarantee zero loss or creation of currency.
- **Append-Only Immutability:** Historical records are never mutated or deleted. Corrections and reversals are handled via immutable compensating entries inheriting target value dates.
- **Dual-Date Mechanics:** Temporal separation between `booking_day` (when an event physically enters the ledger) and `value_day` (effective financial day for balance calculations, interest accruals, and overdraft fees).
- **Bifurcated Balances:** Strict separation between legal `ledger_balance` (booked entries) and real-time `available_balance` (`ledger_balance - active_holds`).
- **Zero-Dependency Portability:** Written entirely in standard Python 3, runnable on any machine without requiring package managers or compilers.

---

## Deliverables Index

In accordance with the Mal Bank submission instructions, all requested artifacts are provided:

| Deliverable File | Description |
| :--- | :--- |
| **[README.md](README.md)** | System overview, instructions to run the suite, and guide to reading the output. |
| **[NUMBERS.md](NUMBERS.md)** | Rigorous mathematical and regulatory justification for every constant chosen (why that value and not half it). |
| **[AMBIGUITIES.md](AMBIGUITIES.md)** | Exhaustive analysis of domain gray areas, payment network clearing rules, and implemented resolutions. |
| **[REJECTED.md](REJECTED.md)** | Mathematical refutation and refusal of flawed acceptance criteria + mid-build pivot log. |
| **[WORKLOG.md](WORKLOG.md)** | Authentic, timestamped engineering worklog tracking every decision and implementation milestone in GST. |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Part 2 document addressing 100x scale, UAE regulatory surface (CBUAE), authorization state machines, and deferred risks. |
| **[Annotated Failing Test](tests/test_failing_retro_capitalization_boundary.py)** | Deeply annotated failing test exposing the architectural tension of retroactive back-dating in closed periods. |

---

## Project Structure

```text
.
├── .gitignore                                      # Isolates internal decision records & caches
├── README.md                                       # This document: runner guide and system architecture
├── NUMBERS.md                                      # Constants and sensitivity rationale
├── AMBIGUITIES.md                                  # Ambiguities detected and resolutions
├── REJECTED.md                                     # Flawed criteria refutations and abandoned paths
├── WORKLOG.md                                      # Real timestamped GST worklog
├── ARCHITECTURE.md                                 # Part 2 Architecture & Trade-offs document
├── run_replay.py                                   # Standalone script replaying 6-day event stream
├── src/
│   └── ledger/
│       ├── __init__.py                             # Package exports
│       ├── money.py                                # Currency, Money, and Hamilton-Hare allocation
│       ├── events.py                               # Immutable Event dataclasses and EventType enums
│       ├── account.py                              # Account aggregate and AuthorizationHold model
│       ├── store.py                                # Append-only EventStore and Rule 5 balance projector
│       ├── eod.py                                  # EOD engine, overdraft fees, and daily interest accrual
│       ├── clearing.py                             # Settlement matching, force-posts, and reversals
│       └── replay.py                               # 6-day event stream orchestration and daily reporter
└── tests/
    ├── test_money.py                               # Currency isolation & integer minor unit tests
    ├── test_event_store.py                         # Immutability, Rule 5, and dual balance tests
    ├── test_eod.py                                 # Fee idempotence, value-date isolation, and interest tests
    ├── test_clearing.py                            # Matching settlement, force-posts, and reversals
    ├── test_replay.py                              # Complete 6-day integration replay verification
    └── test_failing_retro_capitalization_boundary.py # The intentional annotated failing test
```

---

## How to Run the Submission

The submission requires only a standard Python 3 installation (Python 3.10+ recommended; verified on Python 3.11 and 3.14).

### 1. Execute the Six-Day Event Stream Replay Runner
To replay events E1 through E10 across Day 1 to Day 6 and print the daily ledger reports:

```bash
python3 run_replay.py
```
*(Alternatively, execute directly with `./run_replay.py` if executable permissions are enabled).*

### 2. Execute the Full Unit and Integration Test Suite
To run all 26 passing verification tests:

```bash
python3 -m unittest discover -s tests -v -p "test_*.py" -k "not test_failing"
```
Or run the complete suite including standard tests:
```bash
python3 -m unittest tests/test_money.py tests/test_event_store.py tests/test_eod.py tests/test_clearing.py tests/test_replay.py
```

### 3. Run the Intentional Annotated Failing Test
To inspect the intentional architectural boundary test:

```bash
python3 -m unittest tests/test_failing_retro_capitalization_boundary.py
```
*Expected Result:* The test intentionally fails with `AssertionError: Money(AED 0.00 [0 subunits]) != Money(AED 0.67 [67 subunits])`, demonstrating why value-dated ledgers require a Prior-Period Adjustment (PPA) mechanism when unnotified back-dated entries arrive after closed-period interest capitalization.

---

## How to Read the Daily Replay Output

When running `python3 run_replay.py`, each day from Day 1 through Day 6 produces a standardized 4-part financial report:

```text
==============================================================================
DAY 5 CLOSE-OF-BUSINESS LEDGER REPORT
==============================================================================

[1] CLOSING LEDGER BALANCES:
  * ACC-001 (AED): Closing Balance: AED -360.00 | Available: AED -360.00 [Overdraft Fee: AED 25.00]
  * ACC-002 (BHD): Closing Balance: BHD 10.000 | Available: BHD 10.000
    - Daily Interest Accrued: BHD 0.004

[2] FEE ASSESSMENTS:
  * ACC-001: Assessed AED 25.00 (Closing balance negative)

[3] AUTHORIZATION STATES:
  * Auth-B (ACC-001): DECLINED for AED 90.00 [Avail before: AED -335.00, after: AED -335.00]
    Reason: Insufficient funds: available AED -335.00 < hold AED 90.00
  Active Holds at EOD:
    - None active.

[4] OPERATIONAL NOTICES & EXCEPTIONS:
  ! BACK_DATED_ENTRY: E7 posted on Day 5 with value_date Day 2. Evaluates retroactively on ledger balances.
  ! DECLINE: Auth-B for AED 90.00 was DECLINED. Insufficient funds: available AED -335.00 < hold AED 90.00
  ! FEE_ASSESSED: ACC-001 incurred AED 25.00 overdraft fee on Day 5.
------------------------------------------------------------------------------
```

### Section Breakdown:
1. **`[1] CLOSING LEDGER BALANCES`**:
   - `Closing Balance`: The legally confirmed ledger balance as of close of business, including all posted entries where $value\_date \le \text{current\_day}$.
   - `Available Balance`: The spendable balance after deducting active authorization holds.
   - `Daily Interest Accrued`: Exact interest accrued for that single day at 0.04% on positive balances, rounded using banker's rounding (`ROUND_HALF_EVEN`).
2. **`[2] FEE ASSESSMENTS`**:
   - Details any overdraft fee assessed (AED 25.00 assessed once per day when closing balance is negative).
3. **`[3] AUTHORIZATION STATES`**:
   - Details all authorization requests processed during the day, showing requested amount, approval/decline status, available balances before and after, and decline reasons under Rule 5.
   - Lists all active holds currently pending settlement at EOD.
4. **`[4] OPERATIONAL NOTICES & EXCEPTIONS`**:
   - Emits structured operational alerts for payment scheme force-posts (e.g. Auth-Z settlement E6 without prior auth), back-dated entries (E7), authorization declines (Auth-B), and compensating reversals (E9).

---

## Six-Day Lifecycle Summary Table

| Day | Key Events Replayed | ACC-001 Closing Balance | ACC-001 Available | ACC-002 Closing Balance | Key Operational State |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **Day 1** | E1 (Credit 1200), E2 (Debit 950) | **AED 250.00** | AED 250.00 | BHD 0.000 | Interest accrued: AED 0.10. |
| **Day 2** | E3 (Auth-A hold AED 200.00) | **AED 250.00** | AED 50.00 | BHD 0.000 | Hold placed; ledger unaffected. |
| **Day 3** | E4 (Credit AED 400.00) | **AED 650.00** | AED 450.00 | BHD 0.000 | Salary credit; available rises. |
| **Day 4** | E5 (Auth-A settles 185), E6 (Auth-Z force-post 180) | **AED 285.00** | AED 285.00 | BHD 0.000 | Hold released; Force-post debited. |
| **Day 5** | E7 (Debit 620, val Day 2), E8 (Auth-B), E10 (BHD 10) | **AED -360.00** | AED -360.00 | BHD 10.000 | Day 2 val bal = -370; Auth-B declined; AED 25 fee; E10 in 3 parts. |
| **Day 6** | E9 (Reversal of E7, val Day 2), Day 6 Capitalization | **AED 260.67** | AED 260.67 | BHD 10.008 | E9 restores balance; Interest capitalized: 0.67 AED / 0.008 BHD. |

---

## Mathematical and Invariant Guarantees

1. **Exact Remainder Conservation:** In Event E10, BHD 10.000 is partitioned into three instalments:
   $$\text{Instalments} = [3.334, 3.333, 3.333] \text{ BHD} \implies \sum = 10.000 \text{ BHD strictly conserved.}$$
2. **Exact Interest Capitalization:** Daily accruals across Days 1–6 ($0.10 + 0.10 + 0.26 + 0.11 + 0.00 + 0.10 = 0.67$ AED) sum exactly to the capitalized credit ($0.67$ AED) with zero remainder discarded.
3. **Full Audit Immutability:** Event sequence numbers are monotonic; historical events are permanently immutable.
