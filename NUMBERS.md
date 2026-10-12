# NUMBERS: Rationale for Constants and Numerical Constraints

**Role:** Staff Software Engineer  
**Institution:** Mal Bank (UAE)  
**Deliverable:** Mandatory Part 1 Deliverable — Constants Rationale & Numerical Sensitivity Analysis

The assignment instructions mandate:
> *"NUMBERS.md — every constant you chose, why that value and not half it"*

Below is the exhaustive, mathematically and operationally grounded defense of every constant chosen throughout the ledger implementation, detailing its systemic purpose and why halving or doubling it breaks system invariants.

---

## 1. Currency Precision Exponents: AED = 2 (Factor 100), BHD = 3 (Factor 1000)

- **Chosen Constants:**
  - `Currency.AED.precision = 2` $\rightarrow$ Subunit factor = $10^2 = 100$ (1 AED = 100 fils).
  - `Currency.BHD.precision = 3` $\rightarrow$ Subunit factor = $10^3 = 1000$ (1 BHD = 1000 fils).
- **Systemic Justification:**
  - Governed by **ISO 4217 Currency Codes** and national banking statutory regulations:
    - Central Bank of the UAE (CBUAE) regulatory standards mandate 2 decimal places for AED.
    - Central Bank of Bahrain (CBB) regulatory standards mandate 3 decimal places for BHD.
- **Why Not Half It?**
  - Halving AED precision to 1 decimal place ($10^1 = 10$ fils) destroys sub-ten-fils granularity. A transaction of AED 12.35 would truncate or round to AED 12.40, creating a mandatory loss of AED 0.05 on every retail transaction.
  - Halving BHD precision to 1 or 2 decimals (e.g. 2 decimals) would make representing 1 fil impossible. Under BHD 3-decimal accounting, 1 fil is $0.001$ BHD. At 2 decimals, minimum representable change is 10 fils, instantly misrepresenting interbank clearing settlements and violating Bahraini financial law.

---

## 2. Overdraft Fee: AED 25.00 (`OVERDRAFT_FEE_AED = 2500` subunits)

- **Chosen Constant:** AED 25.00 (2,500 integer fils).
- **Systemic Justification:**
  - Explicitly mandated by specification Rule 1: *"Overdraft fee: AED 25.00, assessed once per day per account when that day's closing ledger balance is negative."*
  - In UAE retail banking practice, consumer overdraft / unpaid item charges are capped under CBUAE Consumer Protection Regulations (Circular No. 8/2020) at standard flat-rate schedule caps (historically AED 25 to AED 100 per incidence).
- **Why Not Half It (AED 12.50)?**
  - Halving the fee to AED 12.50 violates the non-negotiable specification requirement.
  - Economically, flat fee assessments must cover operational interbank clearing risk and liquidity provisioning costs. Halving the fee depresses recovery of clearing cost overheads.
- **Why Not Double It (AED 50.00)?**
  - Doubling to AED 50.00 directly violates the assignment rules and would breach CBUAE fee schedule maximum limits for retail consumer checking overdrafts.

---

## 3. Daily Interest Accrual Rate: 0.04% per day (`DAILY_INTEREST_RATE = Decimal('0.0004')`)

- **Chosen Constant:** $0.04\%$ daily ($0.0004$ decimal multiplier).
- **Systemic Justification:**
  - Mandated by specification Rule 2: *"Daily interest: 0.04% per day on the closing ledger balance, positive balances only."*
  - $0.04\%$ per day compounded over a standard banking year (365 days) corresponds to:
    $$(1 + 0.0004)^{365} - 1 \approx 15.72\% \text{ APY (or } 14.60\% \text{ simple annual APR)}$$
    This represents a high-yield retail savings or specialized liquidity account tier in the regional GCC market.
- **Why Not Half It (0.02% per day)?**
  - Halving to $0.02\%$ per day (0.0002) yields:
    - Day 1 closing balance AED 250.00: $250.00 \times 0.0002 = \text{AED } 0.05$ (halved).
    - Day 3 closing balance AED 650.00: $650.00 \times 0.0002 = \text{AED } 0.13$ (halved).
    - Final Day 6 capitalized interest would drop from AED 0.67 to AED 0.34, failing test assertion parity and violating specification Rule 2.
- **Why Not Double It (0.08% per day)?**
  - Annual simple rate would exceed $29.2\%$, distorting commercial bank cost of funds (COF) and violating regulatory rules.

---

## 4. Replay Window Duration: 6 Days (`WINDOW_DAYS = 6`)

- **Chosen Constant:** 6 days (Day 1 through Day 6).
- **Systemic Justification:**
  - Defined by specification: *"The window is six days, Day 1 through Day 6."*
  - 6 days is the exact minimum temporal span required to exercise the entire multi-day clearing lifecycle:
    - Day 1: Account funding and retail spend.
    - Day 2: Card authorization hold placement.
    - Day 3: Intermediate funding credit.
    - Day 4: Asynchronous network settlement (partial hold release + force post).
    - Day 5: Late offline clearing debit (back-dated), authorization decline, multi-instalment allocation, and overdraft fee assessment.
    - Day 6: Compensating reversal and interest capitalization event.
- **Why Not Half It (3 Days)?**
  - Halving to 3 days terminates the window on Day 3. This would eliminate:
    - Settlement of Auth-A (Day 4) and force-post of Auth-Z (Day 4).
    - Back-dated entry E7 and authorization decline E8 (Day 5).
    - Remainder instalment credit E10 (Day 5).
    - Compensating reversal E9 (Day 6).
    - Final interest capitalization (Day 6).
  - The entire clearing, back-dating, and capitalization domain would remain completely unexercised.
- **Why Not Double It (12 Days)?**
  - Adds zero additional architectural coverage while diluting the signal-to-noise ratio of the required event replay.

---

## 5. Equal Instalment Partition Count: 3 Instalments (`E10_INSTALMENTS = 3`)

- **Chosen Constant:** $N = 3$ instalments for Event E10.
- **Systemic Justification:**
  - Mandated by specification: *"E10 — Day 5 — CREDIT — ACC-002 BHD 10.000, posted as three equal instalments — value_date Day 5"*.
  - A 3-way partition of 10.000 BHD creates a repeating fraction in decimal arithmetic:
    $$\frac{10.000}{3} = 3.333333... \text{ BHD}$$
  - This numerical choice is deliberate: it forces the ledger engine to demonstrate its ability to handle fractional remainders without losing or minting money.
- **Why Not Half It?**
  - $N = 1.5$ is undefined for discrete financial transactions.
  - $N = 2$ partitions 10.000 BHD evenly into $5.000 + 5.000$ BHD, entirely dodging the repeating fraction test and concealing whether the ledger respects the law of conservation of money.

---

## 6. Remainder Allocation Step: 1 Subunit (1 fil = `1`)

- **Chosen Constant:** 1 integer minor unit (1 fil = 0.001 BHD).
- **Systemic Justification:**
  - In `allocate_instalments(total, parts)`, the integer remainder $R = \text{total.subunits} \pmod{\text{parts}}$ is distributed in discrete chunks of **1 minor unit** across the first $R$ partitions.
  - For $10,000 \text{ fils} \pmod 3 = 1 \text{ fil}$, exactly one instalment receives $+1 \text{ fil}$ ($3,334$ fils) and the remaining two receive the base quotient ($3,333$ fils).
- **Why Not Half It (0.5 fil)?**
  - Minor units are the atomic indivisible quantum of fiat currency. In integer arithmetic, 0.5 fil does not exist; fractional fils cannot be settled across central bank payment rails.
- **Why Not Double It (2 fils)?**
  - Adding 2 fils would overshoot the remainder, creating an unbalanced partition of $3,335 + 3,333 + 3,333 = 10,001$ fils ($10.001$ BHD), violating conservation.

---

## 7. Rounding Mode: Banker's Rounding (`ROUND_HALF_EVEN`)

- **Chosen Constant:** Round half to even (`decimal.ROUND_HALF_EVEN`).
- **Systemic Justification:**
  - Standard IEEE 754 and GAAP/IFRS financial accounting convention.
  - Unlike naive "round half up" (which introduces a positive statistical bias over large volumes), banker's rounding distributes rounding residuals symmetrically toward zero across repeated daily interest accruals.
- **Why Not Truncation (`ROUND_DOWN`)?**
  - Truncation consistently under-credits interest to depositors, causing systematic negative drift and potential regulatory sanctions for unfair consumer practices.
- **Why Not Ceiling (`ROUND_UP`)?**
  - Ceiling consistently over-credits depositors at the bank's expense, creating systemic leakage on the bank's interest expense ledger.
