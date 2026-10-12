# REJECTED: Refused Acceptance Criteria & Abandoned Approaches

**Role:** Staff Software Engineer  
**Institution:** Mal Bank (UAE)  
**Deliverable:** Mandatory Part 1 Deliverable — Acceptance Criteria Refutation & Mid-Build Pivot Log

---

## Part 1: Formal Refusal of Flawed Acceptance Criteria

The specification states:
> *"Some of the following criteria are wrong. Identify every incorrect criterion, refuse it, and document your reasoning in REJECTED.md."*

Below is the exhaustive, mathematically and operationally grounded refutation of every invalid criterion present in the prompt.

---

### Criterion 1: *"E7 causes exactly one overdraft fee to be assessed, on Day 2."*
- **Verdict:** **REFUSED (Mathematically and Temporally Invalid)**
- **Prompt Formulation:** E7 (DEBIT ACC-001 AED 620.00, `value_date = Day 2`) arrives on Day 5. The criterion asserts that this event causes a fee to be assessed on Day 2.
- **Architectural & Legal Grounds for Refusal:**
  1. **Append-Only Temporal Immutability:** Non-negotiable Rule 4 mandates: *"The ledger is append-only. No event record is ever mutated or deleted."* When Day 2 closed, the facts available to the bank at close of business showed a ledger balance of AED +250.00. That accounting period closed without an overdraft. An event arriving on Day 5 cannot time-travel into a sealed historical close-of-business batch to insert a fee on Day 2.
  2. **Rule 1 Booking Mandate:** Non-negotiable Rule 1 explicitly states: *"Booked with value_date equal to the day assessed."* The fee is assessed on **Day 5** (when the negative balance is first realized by the system), and must therefore be booked with `booking_day = 5` and `value_date = 5`.
  3. **Multi-Day Overdraft Reality:** Even if one attempted retroactive restatement, E7 makes the closing ledger balance negative across **three distinct days** (Day 2: AED -370.00, Day 4: AED -335.00, Day 5: AED -335.00). Asserting that it causes "exactly one fee, on Day 2" contradicts the rule that fees are assessed *"once per day per account when that day's closing ledger balance is negative"*.
- **Correct System Behavior:** The overdraft fee is assessed once on Day 5 with `value_date = Day 5` for AED 25.00.

---

### Criterion 2: *"Any settlement referencing an authorization ID not present in the ledger must be rejected and the funds must not leave the account."*
- **Verdict:** **REFUSED (Violates Payment Scheme Rules & Banking Law)**
- **Prompt Formulation:** Settlement E6 references `Auth-Z` (for AED 180.00), which has no preceding authorization event in the ledger.
- **Architectural & Operational Grounds for Refusal:**
  1. **Clearing Presentment Obligations:** In card payment networks (Visa Core Rules and Mastercard Bylaws) and UAE clearing operations (CBUAE UAESWITCH), a presentment (clearing settlement file) is a non-negotiable legal demand for funds. The merchant has already rendered goods or services (e.g. offline flight purchase, parking meter, or transaction where authorization expired after 7 days).
  2. **Regulatory & Financial Penalties:** If an issuing bank unilaterally rejects an incoming presentment due to a missing local authorization record, the payment scheme levies severe non-compliance fines, forces chargeback arbitration losses, and may revoke clearing license status.
  3. **Force-Post Semantics:** The universal banking standard for unmatched presentments is a **force-post**: the funds *must* leave the account (debit posted immediately), driving the account into overdraft if necessary, while simultaneously generating a security/fraud operational alert.
- **Correct System Behavior:** Settlement E6 is accepted and debited to ACC-001. An operational notice `FORCE_POST: Settlement E6 for Auth-Z has no preceding active authorization` is logged.

---

### Criterion 3: *"If Auth-B is approved, its hold reduces available balance but not ledger balance."*
- **Verdict:** **REFUSED (Premise False; Contradicts Non-Negotiable Rule 5)**
- **Prompt Formulation:** Event E8 requests an authorization hold for AED 90.00 on ACC-001 on Day 5. The criterion posits a hypothetical approval.
- **Architectural & Mathematical Grounds for Refusal:**
  1. **Rule 5 Mandate:** Non-negotiable Rule 5 states: *"An authorization is approved only if the account's available balance — ledger balance minus active holds — remains at or above zero after the hold is applied."*
  2. **Financial State on Day 5:**
     - Ledger balance prior to E8:
       $$\text{Credits} (1200 + 400) - \text{Debits} (950 + 185 + 180 + 620) = 1600 - 1935 = \text{AED } -335.00$$
     - Active holds: AED 0.00 (Auth-A was fully released upon Day 4 settlement E5).
     - Available balance: $\text{AED } -335.00 - 0.00 = \text{AED } -335.00$.
  3. **Evaluation:** Applying the requested AED 90.00 hold yields:
     $$\text{Available After} = -335.00 - 90.00 = \text{AED } -425.00 < 0$$
     Because $-425.00 < 0$, the condition `Available >= 0` is breached.
  4. Approving Auth-B would directly violate Rule 5. The premise of the acceptance criterion is false.
- **Correct System Behavior:** Auth-B is unconditionally **DECLINED** with the reason: `Insufficient funds: available AED -335.00 < hold AED 90.00`. Zero hold is placed.

---

### Criterion 4: *"After E9, all balances and fees return to their pre-E7 values."*
- **Verdict:** **REFUSED (Violates Accounting Immutability & Audit Trail Integrity)**
- **Prompt Formulation:** E9 arrives on Day 6 reversing E7 (`value_date = Day 2`). The criterion claims that all balances and fees return to their pre-E7 values.
- **Architectural & Accounting Grounds for Refusal:**
  1. **Fee Legitimacy at Point-in-Time:** The AED 25.00 overdraft fee assessed at Day 5 close of business was assessed legitimately based on the actual ledger state on Day 5.
  2. **No Retroactive Fee Deletion:** In an append-only ledger, a reversal of a underlying transaction does not magically extinguish validly assessed fees. Under banking regulations, reversing a fee requires an explicit, separate business transaction: a `FEE_WAIVER` or `FEE_REFUND` compensating credit, approved via operational policy.
  3. **Historical Interest Accrual Integrity:** Closing balances and interest accruals calculated for Day 2, Day 3, Day 4, and Day 5 were legally closed. E9 restores the posted ledger balance on Day 6 via a compensating entry, but the historical Day 5 close-of-business record remains on file with its fee intact.
- **Correct System Behavior:** E9 restores the principal ledger balance by posting a compensating credit of AED 620.00. The Day 5 fee of AED 25.00 remains posted on the ledger. Final closing balance at Day 6 close is AED +260.67 (reflecting original funds minus the valid Day 5 fee plus accrued interest), not the pre-E7 balance of AED 285.00.

---

### Criterion 5: *"The three BHD instalments in E10 must each be BHD 3.334."*
- **Verdict:** **REFUSED (Violates Conservation of Money)**
- **Prompt Formulation:** Event E10 specifies crediting ACC-002 with BHD 10.000 posted as three equal instalments. The criterion claims each instalment must be BHD 3.334.
- **Mathematical Proof of Refusal:**
  $$\text{Instalment 1: } 3.334 \text{ BHD} = 3,334 \text{ fils}$$
  $$\text{Instalment 2: } 3.334 \text{ BHD} = 3,334 \text{ fils}$$
  $$\text{Instalment 3: } 3.334 \text{ BHD} = 3,334 \text{ fils}$$
  $$\text{Sum} = 3 \times 3.334 = 10.002 \text{ BHD} = 10,002 \text{ fils}$$
  $$\Delta = 10.002 - 10.000 = +0.002 \text{ BHD} (+2 \text{ fils})$$
  Accepting three instalments of BHD 3.334 mints 2 fils out of thin air. In double-entry banking systems, this creates an un-reconcilable ledger variance across the bank's clearing suspense account.
- **Correct System Behavior:** Remainder-preserving allocation (Hamilton-Hare method). The 10,000 fils are partitioned as $3,334 + 3,333 + 3,333 = 10,000$ fils ($3.334, 3.333, 3.333$ BHD), strictly conserving the exact 10.000 BHD total.

---

### Criterion 6: *"If the rounded daily interest accruals do not sum to the capitalized total, the remainder is discarded."*
- **Verdict:** **REFUSED (Violates Non-Negotiable Rule 2 & Financial Conservation)**
- **Prompt Formulation:** The criterion suggests discarding rounding remainders during capitalization.
- **Grounds for Refusal:**
  1. **Direct Contradiction:** Non-negotiable Rule 2 explicitly mandates: *"The rounded daily accruals must sum exactly to the capitalized total."*
  2. Discarding remainders destroys minor units (fils), creating an un-balanced balance sheet where the liability incurred on the accrual account does not match the equity transferred to customer deposits.
- **Correct System Behavior:** The capitalized total is computed as the exact sum of the rounded daily accruals:
  $$\text{Capitalized Total} \equiv \sum_{d=1}^{6} \text{Daily Accrual}(d)$$
  Zero remainder is discarded; exact conservation is maintained down to the minor unit.

---

## Part 2: Approaches Abandoned Mid-Build

In keeping with Staff Software Engineering discipline, several architectural approaches were evaluated, prototyped, and deliberately abandoned during development.

### Abandoned Approach 1: Python `float` or Naive `decimal.Decimal` Quantization
- **Initial Idea:** Use Python's built-in `float` or float-based `Decimal` arithmetic directly for balance computation.
- **Why Abandoned:** Floating-point arithmetic fails fundamental precision tests (`0.1 + 0.2 != 0.3`). Even `Decimal` without explicit scale management can accumulate unbounded precision during interest division ($0.04\% = 0.0004$).
- **Final Decision:** Created an immutable `Money` value object storing balance strictly as an integer count of minor units (`subunits`: fils). Scale is locked by `Currency` enum (factor 100 for AED, 1000 for BHD). All additions, subtractions, and comparisons are strictly integer arithmetic.

### Abandoned Approach 2: Retroactive In-Place Balance Mutation
- **Initial Idea:** When back-dated event E7 arrives on Day 5 with `value_date = Day 2`, retroactively update Day 2's stored balance record and mutate the historical Day 2 EOD snapshot.
- **Why Abandoned:** Violates Rule 4 (append-only ledger). Mutating historical records destroys auditability and invalidates regulatory reports already dispatched to regulators.
- **Final Decision:** Retained append-only event stream. Day-specific closing balances are derived via point-in-time projections filtering by `booking_day <= current_day` and `value_day <= target_day`. Day 5 assesses the overdraft fee for Day 5 without rewriting the historical Day 2 ledger.

### Abandoned Approach 3: Rejecting Unmatched Settlements (Offline Presentments)
- **Initial Idea:** Strictly reject Event E6 (Auth-Z settlement) because `Auth-Z` does not exist in `account.holds`.
- **Why Abandoned:** Although superficially appealing from a naive validation perspective, it violates card network clearing rules (Visa/Mastercard) and banking law. Unmatched presentments are binding clearing obligations.
- **Final Decision:** Implemented force-post clearing semantics. The account is debited immediately, while an operational event `FORCE_POST` is emitted for downstream fraud and compliance monitoring.

### Abandoned Approach 4: Partial Hold Reduction on Partial Settlement
- **Initial Idea:** When E5 settles Auth-A for AED 185.00 against a hold of AED 200.00, leave the remaining AED 15.00 active as a residual hold.
- **Why Abandoned:** Under Visa and Mastercard clearing rules, a final clearing presentment matched to an authorization lifecycle identifier extinguishes the authorization hold in full. Retaining "orphan residual holds" artificially depresses customer available balance and triggers customer friction and regulatory complaints.
- **Final Decision:** E5 releases the entire AED 200.00 hold and books the actual settlement debit of AED 185.00.
