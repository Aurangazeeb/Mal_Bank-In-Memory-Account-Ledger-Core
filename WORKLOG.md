# Engineering Worklog: In-Memory Account Ledger Core

All timestamps are in GST (Gulf Standard Time, UTC+4), matching the operational timezone of Mal Bank in the UAE.

---

### 2026-10-11 10:15:00 GST — Session Initialization & Governance Scaffolding
- Reviewed assignment requirements: zero-dependency in-memory ledger, dual-date model, 6-day window, currency precision (AED 2 decimals, BHD 3 decimals).
- Refuted 6 flawed acceptance criteria to be formalized in `REJECTED.md`.
- Configured `.gitignore` 
  and ensured git tracking is strictly restricted to deliverables requested by Mal Bank (`WORKLOG.md`, `README.md`, `NUMBERS.md`, `AMBIGUITIES.md`, `REJECTED.md`, `ARCHITECTURE.md`, core source, and tests).
- Initialized git repository on branch `main`.

---

### 2026-10-11 10:30:00 GST — Phase 1: Exact Monetary Primitives & Precision Engine
- Configured Python test runner using `~/.uv-envs/interview-tools/.venv/bin/python` with standard library `unittest` (zero external dependencies).
- Implemented `Currency` enum supporting AED (precision 2) and BHD (precision 3).
- Implemented immutable `Money` value object with exact integer minor unit representation (`subunits`), banker's rounding on conversion, and currency isolation checks.
- Implemented `allocate_instalments()` implementing the Hamilton-Hare remainder-preserving algorithm to ensure strict conservation of money across fractional instalments.
- Verified and refuted flawed criterion: 3 x 3.334 BHD = 10.002 BHD (+0.002 BHD phantom creation); correct allocation is 3.334 + 3.333 + 3.333 = 10.000 BHD.
- Authored unit test suite in `tests/test_money.py` (5 tests passing).

---

### 2026-10-11 10:45:00 GST — Phase 2: Append-Only Event Store & Dual-Balance Projections
- Implemented immutable `Event` dataclass with frozen slots and monotonically increasing `sequence_id`.
- Implemented `Account` aggregate tracking currency, opening balance, and active authorization holds.
- Implemented `EventStore` enforcing append-only immutability and bifurcated balances (`ledger_balance` vs `available_balance`).
- Implemented authorization processing strictly enforcing Rule 5: approved only if available balance minus requested hold remains $\ge 0$.
- Verified that authorization holds affect available balance while isolating ledger balance.
- Authored unit test suite in `tests/test_event_store.py` (6 tests passing, 11 total passing across suite).

---

### 2026-10-11 11:05:00 GST — Phase 3: Dual-Date Engine & End-of-Day (EOD) Processing
- Implemented `EODEngine` orchestrating daily closing ledger balance evaluation ($value\_date \le current\_day$), overdraft fees, and interest accrual.
- Implemented daily overdraft fee rules: AED 25.00 assessed once per calendar day per account when closing balance is negative, booked with `value_date = current_day`.
- Implemented daily interest accrual at 0.04% on positive closing ledger balance with banker's rounding to currency precision.
- Implemented Day 6 interest capitalization reconciling the sum of rounded daily accruals with the capitalized total credit ($\sum \text{Daily Accruals} \equiv \text{Capitalized Total}$).
- Authored unit test suite in `tests/test_eod.py` (4 tests passing, 15 total passing across suite).
- Authored internal decision record `./dr/03-dual-date-and-eod/decision_record.md`.

---

### 2026-10-11 11:25:00 GST — Phase 4: Authorization Lifecycle, Force-Posts & Reversals
- Implemented `ClearingEngine` managing card presentments, authorization releases, and reversals.
- Implemented matching settlement handling: E5 releases Auth-A AED 200.00 hold and debits settled amount AED 185.00.
- Implemented force-post clearing settlement for E6 (Auth-Z): debited account AED 180.00 per mandatory network clearing obligations and emitted structured `FORCE_POST` operational alert.
- Refuted flawed criterion demanding rejection of unmatched settlements.
- Implemented append-only compensating reversal for E9 referencing E7 with value date Day 2, preserving immutable audit trail.
- Authored unit test suite in `tests/test_clearing.py` (4 tests passing, 19 total passing across suite).
- Authored internal decision record `./dr/04-clearing-and-reversals/decision_record.md`.

---

### 2026-10-11 11:45:00 GST — Phase 5: Six-Day Event Stream Replay & Daily Reporter
- Implemented `LedgerReplayEngine` in `src/ledger/replay.py` sequentially executing events E1 through E10 across Day 1 to Day 6.
- Implemented formatted daily reporting displaying closing ledger balance, fee assessments, authorization states (requests, holds, declines), and operational notices/errors.
- Created executable runner script `run_replay.py` meeting Part 1 exercise requirements.
- Confirmed all daily snapshots:
  * Day 1: Credit 1200, Debit 950 -> Closing 250.00 AED, Interest 0.10 AED.
  * Day 2: Auth-A 200 hold placed -> Closing 250.00 AED, Available 50.00 AED.
  * Day 3: Credit 400 -> Closing 650.00 AED, Available 450.00 AED.
  * Day 4: Auth-A settles for 185.00 AED (hold released), Auth-Z force-posts for 180.00 AED -> Closing 285.00 AED.
  * Day 5: E7 back-dated debit 620.00 AED (Day 2 value_date) drives balance to -335.00 AED. Auth-B for 90.00 AED declined under Rule 5. Overdraft fee 25.00 AED assessed -> Closing -360.00 AED. ACC-002 credited 10.000 BHD in 3 instalments [3.334, 3.333, 3.333]. Day 2 closing balance evaluated at end of Day 5 verified as -370.00 AED.
  * Day 6: E9 reversal of E7 (+620.00 AED). Capitalized interest credited: 0.67 AED for ACC-001 (closing 260.67 AED) and 0.008 BHD for ACC-002 (closing 10.008 BHD).
- Authored integration test suite in `tests/test_replay.py` (7 tests passing, 26 total passing across suite).
- Authored internal decision record `./dr/05-replay-and-reporting/decision_record.md`.

---

### 2026-10-11 12:05:00 GST — Phase 6: The Intentional Annotated Failing Test
- Designed intentional failing test `tests/test_failing_retro_capitalization_boundary.py` fulfilling the mandatory Part 1 deliverable ("One failing test against your own design, inline-annotated with what it reveals").
- Target architectural tension: "Closed-Period Capitalization Invariant vs. Unbounded Retroactive Back-Dated Entries".
- Scenario modeled: An unnotified back-dated clearing debit of AED 1,000.00 with `value_date = Day 1` arrives on Day 7, after Day 6 interest has already been finalized and capitalized as an immutable ledger credit (AED 0.67).
- Demonstrated that post-facto re-evaluation reveals the true accruals across Days 1–6 were AED 0.00, causing `sum(accruals) == capitalized_event.amount` to fail (AED 0.00 != AED 0.67).
- Provided extensive inline annotations explaining why an append-only ledger without an enterprise Prior-Period Adjustment (PPA) subsystem or hard value-dating cutoff window cannot reconcile finalized closed periods.
- Authored internal decision record `./dr/06-intentional-failing-test/decision_record.md`.
