# Contoso Insurance synthetic claims data

> **Synthetic data.** Contoso Insurance is fictional. Every customer, policy,
> vehicle, VIN, claim, address, phone number and email address in this folder is
> invented for demonstration. Nothing here describes a real person, vehicle,
> insurer or claim.

These files are the system-of-record data served by the Claims Operations API
(`tools/main.py`). They hold business facts only — no coverage determinations,
assessments, scores or recommendations.

## Regenerating

```powershell
python data/generate_data.py           # rewrite the JSON files
python data/generate_data.py --check   # verify the committed files are current
```

Generation is deterministic (fixed seed `20261120`, static dates, sorted output,
LF line endings). Running the generator twice produces byte-identical files.
Records are as of `2026-11-20T08:00:00Z` (`recordsAsOf` in every file).

## Files

| File | Records | Contents |
|---|---|---|
| `customers.json` | 30 | Policyholders: contact details, `customerSince`, policy and vehicle IDs |
| `policies.json` | 40 | Personal auto policies: status, term dates, drivers, policy-level and per-vehicle coverages, deductibles, limits, loss payees |
| `vehicles.json` | 35 | Vehicles: VIN, year/make/model/trim, color, ownership and lienholder, garaging, equipment |
| `claims.json` | 50 | Claims in the current claims system (losses on or after 2023-01-01) |
| `claim-history.json` | 12 | Closed claims archived from the legacy claims system (losses before 2023-01-01) |
| `repair-facilities.json` | 10 | Repair facilities: services, network status, address, labor rates |

Each file is a JSON object with dataset metadata (`synthetic`, `notice`,
`recordsAsOf`, `source`) and one record list.

## Conventions

- **IDs:** `CUST-#####`, `PAP-#######`, `VEH-#####`, `CLM-#####`,
  `AC-YYYY-#####` (archived claims), `RF-###`, `DOC-<claim number>-##`.
  Claim numbers increase with the time a claim was reported.
- **Dates** are ISO 8601 calendar dates. `reportedAt`, `createdAt`,
  `lastUpdatedAt` and document `receivedAt` are UTC timestamps.
  `lossTime` is local time in `lossTimeZone`.
- **Policy terms:** coverage begins at 12:01 a.m. on `termEffectiveDate` and
  ends at 12:01 a.m. on `termExpirationDate` (exclusive). `inceptionDate` is the
  first day the policy was ever in force. A cancelled policy's coverage ends on
  `cancellation.effectiveDate`. A vehicle is on a policy from `addedDate` until
  `removedDate` (exclusive), within the policy period.
- **Money** is US dollars as JSON numbers with two decimal places.
  `estimate.grossAmount` is the repair facility's estimate total before any
  deductible. For paid claims, `settlement.totalPaid` is
  `settledAmount - deductibleApplied`.
- **Contact data** uses the reserved `555-0100`–`555-0199` phone range and the
  `example.com` email domain. VINs use world manufacturer identifiers that begin
  with `0`, which are not assigned to any real manufacturer; check digits are
  valid.
- Makes and models (Contoso, Fabrikam, Northwind, Litware, Adatum, Tailspin)
  are fictional.

## Scope of the claim records

`claims[].documents` is the claim's document index: what has been received and
when. Evidence **files** exist only for the demo claim `CLM-10482`, under
`evidence/CLM-10482/` (see `evidence/CLM-10482/evidence-manifest.json`). For
every other claim the document index is metadata only.

## Situations represented

Beyond routine open and closed claims, the data intentionally includes these
situations so later evaluations can use claims other than the demo claim. The
records themselves describe facts only; none of them carries a label for the
situation it represents.

| Claim(s) | Situation |
|---|---|
| `CLM-10482` | Demo claim: two-vehicle collision in a parking lot, collision coverage with a $1,000 deductible, police report and repair estimate received |
| `CLM-10329` | The same policyholder's earlier glass claim (closed, paid) |
| `CLM-10247`, `CLM-10278`, `CLM-10340`, `CLM-10436`, `AC-2022-25562` | One policyholder with several claims over several years |
| `CLM-10459`, `CLM-10464` | Two open claims for the same vehicle with loss dates one day apart, reported through different channels |
| `CLM-10419` | Loss date after the policy's expiration date |
| `CLM-10445` | Loss date after the policy's cancellation date |
| `CLM-10467` | Police report reported by the customer but not yet received |
| `CLM-10471` | Open two-vehicle claim with photos, police report and estimate received |
| `CLM-10487` | Newly submitted single-vehicle claim, not reported to police |

Six customers have no claims. Some older owned vehicles carry liability-only or
comprehensive-only coverage; financed and leased vehicles always carry
collision and comprehensive coverage.
