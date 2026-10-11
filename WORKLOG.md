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
