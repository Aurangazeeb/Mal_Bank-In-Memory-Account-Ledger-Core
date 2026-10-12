# AMBIGUITIES: Domain Contradictions, Gray Areas & Resolution Rationale

**Role:** Staff Software Engineer  
**Institution:** Mal Bank (UAE)  
**Deliverable:** Mandatory Part 1 Deliverable — Exhaustive Ambiguities & Edge Case Log

The specification instructs:
> *"AMBIGUITIES.md — every ambiguity you found and how you resolved it; near-empty is a fail"*

Financial specifications in banking are frequently incomplete, contradictory, or silent on critical operational edge cases. Below is the exhaustive log of every domain ambiguity identified in the prompt, along with the Staff-level rationale and architectural resolution implemented in the ledger core.

---

## 1. Value-Date vs. Booking-Date Fee Assessment Timing

### The Ambiguity
Rule 1 specifies:
> *"Overdraft fee: AED 25.00, assessed once per day per account when that day's closing ledger balance (all entries with value_date <= that day) is negative. Booked with value_date equal to the day assessed."*

When Event E7 arrives on **Day 5** with `value_date = Day 2`, the historical balance of Day 2 ($value\_date \le \text{Day 2}$) becomes negative (AED $-370.00$).
This creates a critical temporal ambiguity:
- **Interpretation A (Retroactive Booking):** Assess the fee retroactively on Day 2 with `booking_day = 2` and `value_day = 2`.
- **Interpretation B (Real-Time Booking on Assessment Day):** Assess the fee on Day 5 (the day the system processes the overdraft) with `booking_day = 5` and `value_day = 5`.
- **Interpretation C (Retroactive Cascade):** Assess fees on Day 2, Day 3, Day 4, and Day 5 because the balance remained negative continuously until Day 6.

### Why It Matters
Interpretation A violates append-only immutability (Rule 4), because Day 2's financial books were already closed and reported. Interpretation C would assess 4 separate fees (AED 100.00) for a single back-dated entry, triggering severe customer dissatisfaction and CBUAE consumer protection sanctions.

### Resolution & Justification
**We implemented Interpretation B.**
The phrase *"booked with value_date equal to the day assessed"* binds the `value_date` to the calendar day on which the assessment logic executes (**Day 5**). The fee is appended as:
```text
Event(event_id="FEE-D5-ACC001", booking_day=5, value_day=5, amount=AED 25.00)
```
Historical Day 2 close-of-business records are preserved as they were on Day 2. The overdraft fee appears in the Day 5 close-of-business report when the negative balance was first recognized.

---

## 2. Card Settlement Without Prior Authorization (The Force-Post / Presentment Dilemma)

### The Ambiguity
Event E6 describes:
> *"E6 — Day 4 — SETTLEMENT — ACC-001 Auth-Z settles for AED 180.00 — value_date Day 4 (Auth-Z has no preceding authorization event)"*

Acceptance Criterion 4 claims:
> *"Any settlement referencing an authorization ID not present in the ledger must be rejected and the funds must not leave the account."*

This creates a direct contradiction between payment scheme clearing rules and the prompt's acceptance criteria.

### Why It Matters
In retail banking, an issuing bank does not have the legal or technical option to unilaterally reject an incoming clearing presentment (interchange file) simply because it lacks a matching local authorization record. Presentments represent cleared settlement obligations across Central Bank or Card Scheme rails (Visa, Mastercard, UAESWITCH). Rejecting them violates operating regulations, incurs immediate chargeback arbitration penalties, and results in fines.

### Resolution & Justification
**We resolved this by treating E6 as a mandatory Force-Post Settlement.**
The funds **must leave the account** (debited immediately to ACC-001). However, to satisfy compliance, risk management, and operational auditability:
1. The transaction is booked with `EventType.SETTLEMENT`.
2. The settlement result flags `is_force_post = True`.
3. An operational notice `FORCE_POST: Settlement E6 for Auth-Z has no preceding active authorization. Posted per clearing network obligation.` is logged in the daily report.
Acceptance Criterion 4 was formally refuted and rejected in [REJECTED.md](REJECTED.md).

---

## 3. Partial Settlement Hold Lifecycle (Full vs. Residual Release)

### The Ambiguity
Event E3 placed an authorization hold for **AED 200.00** (`Auth-A`).
Event E5 arrives on Day 4 settling `Auth-A` for **AED 185.00**.
The specification is silent on what happens to the remaining **AED 15.00**:
- **Option A (Residual Hold):** Keep an active hold of AED 15.00 on the account until explicit release or expiration.
- **Option B (Full Hold Release):** Release the entire AED 200.00 hold upon posting the AED 185.00 settlement debit.

### Why It Matters
If Option A is chosen, the customer's available balance remains artificially suppressed by AED 15.00 indefinitely. If Option B is chosen, what if the merchant submits a secondary settlement for the remaining amount?

### Resolution & Justification
**We implemented Option B (Full Hold Release).**
Under Visa and Mastercard scheme clearing rules (e.g. Visa Core Rules, section on Authorization and Clearing Matching), a first presentment referencing an authorization lifecycle ID satisfies and extinguishes the authorization hold in full unless explicitly flagged as a partial-sequence presentment (e.g. split-shipment e-commerce).
Upon processing E5:
1. The active hold of AED 200.00 is completely deactivated (`is_active = False`).
2. The settlement debit of AED 185.00 is posted.
3. Available balance increases by AED 15.00 net ($+200.00 \text{ hold release} - 185.00 \text{ debit} = +15.00$).

---

## 4. Reversal vs. Historical Fee Cancellation (The E9 Dilemma)

### The Ambiguity
Event E9 arrives on Day 6 reversing E7 (`value_date = Day 2`).
Acceptance Criterion 6 claims:
> *"After E9, all balances and fees return to their pre-E7 values."*

### Why It Matters
Does reversing a transaction retroactively delete or reverse the overdraft fee that was assessed on Day 5?
In an append-only ledger (Rule 4), events are never mutated or deleted. Furthermore, on Day 5, the bank was legally in an overdrawn exposure condition due to E7. An unauthorized overdraft occurred.

### Resolution & Justification
**We resolved this strictly in favor of immutable append-only accounting.**
1. E9 books an immutable compensating credit (`EventType.REVERSAL`) for AED 620.00 with `value_date = Day 2` on Day 6.
2. The overdraft fee assessed on Day 5 **remains on the ledger**. Reversing a fee in commercial banking requires an explicit business justification and an independent transaction (`FEE_WAIVER`).
3. Historical EOD closing balances for Day 5 are not retroactively rewritten; Day 6 close reflects the restored balance minus the valid Day 5 fee plus Day 6 interest.
Acceptance Criterion 6 was formally refused in [REJECTED.md](REJECTED.md).

---

## 5. Non-Settled Authorization at Window Boundary (Auth-B)

### The Ambiguity
The specification states:
> *"E8 — Day 5 — AUTHORIZATION — ACC-001 Auth-B hold AED 90.00 — value_date Day 5"*
> *"Auth-B is never settled inside the window."*

Acceptance Criterion 5 states:
> *"If Auth-B is approved, its hold reduces available balance but not ledger balance."*

This creates an ambiguity regarding whether the system should evaluate the hypothetical scenario or enforce the strict rule.

### Why It Matters
When E8 arrives on Day 5, the ledger balance is AED $-335.00$ (due to E7). If a developer implements the conditional "If Auth-B is approved" by artificially approving it, they violate Rule 5:
> *"An authorization is approved only if the account's available balance — ledger balance minus active holds — remains at or above zero after the hold is applied."*

### Resolution & Justification
**We enforced Rule 5 unconditionally.**
On Day 5, ACC-001 available balance is AED $-335.00$. An authorization request for AED 90.00 would leave available balance at AED $-425.00 < 0$.
Auth-B is **DECLINED**. Zero hold is created. The clause *"Auth-B is never settled inside the window"* is true vacuously because a declined authorization can never settle.

---

## 6. Interest Capitalization Rounding Remainder Allocation

### The Ambiguity
Rule 2 specifies:
> *"Daily interest: 0.04% per day on the closing ledger balance, positive balances only. Accruals capitalize as a single credit at end of Day 6. The rounded daily accruals must sum exactly to the capitalized total."*

Acceptance Criterion 8 claims:
> *"If the rounded daily interest accruals do not sum to the capitalized total, the remainder is discarded."*

This is a direct, explicit contradiction between Rule 2 and Acceptance Criterion 8.

### Why It Matters
If you round daily accruals to currency precision (e.g. fils), the sum of rounded values may drift from a hypothetical unrounded 6-day cumulative interest calculation. Which number takes precedence?
- Does the capitalization event equal $\sum \text{rounded daily accruals}$?
- Or does the capitalization event calculate $( \sum \text{unrounded} )$ and discard the difference?

### Resolution & Justification
**We resolved this strictly by enforcing Non-Negotiable Rule 2 and refusing Acceptance Criterion 8.**
In financial accounting:
1. Each day's accrual is a legally recognized, rounded liability: $\text{Accrual}(d)$.
2. The capitalized credit booked on Day 6 is defined as:
   $$\text{Capitalized Total} \equiv \sum_{d=1}^{6} \text{Accrual}(d)$$
3. By construction, the sum of daily accruals matches the capitalized credit to the exact minor unit (fil). Zero remainder is discarded. Criterion 8 was formally refused in [REJECTED.md](REJECTED.md).

---

## 7. Multi-Instalment Division Conservation (Event E10)

### The Ambiguity
Event E10 specifies crediting ACC-002 with BHD 10.000 posted as three equal instalments on Day 5.
Acceptance Criterion 7 claims:
> *"The three BHD instalments in E10 must each be BHD 3.334."*

$\frac{10.000}{3} = 3.333333...$ BHD. $3.334 \times 3 = 10.002$ BHD.

### Why It Matters
Accepting Criterion 7 creates 2 fils of phantom equity out of thin air, violating double-entry balance sheet conservation.

### Resolution & Justification
**We resolved this using the Hamilton-Hare Largest Remainder algorithm (`allocate_instalments`).**
10.000 BHD ($10,000$ fils) divided into 3 instalments:
- Base instalment: $10,000 // 3 = 3,333$ fils ($3.333$ BHD).
- Remainder: $10,000 \pmod 3 = 1$ fil ($0.001$ BHD).
- Partition:
  - Instalment 1: $3,334$ fils ($3.334$ BHD)
  - Instalment 2: $3,333$ fils ($3.333$ BHD)
  - Instalment 3: $3,333$ fils ($3.333$ BHD)
- $\sum = 10,000$ fils ($10.000$ BHD).
Criterion 7 was formally refused in [REJECTED.md](REJECTED.md).
