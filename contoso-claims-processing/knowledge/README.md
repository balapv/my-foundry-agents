# Contoso Insurance claims guidance (agent knowledge)

These four documents are the **only** knowledge uploaded to the Claims Review agent's File Search vector store. They are synthetic company guidance written to apply to any personal auto physical damage claim. They do not mention any synthetic claim, customer, vehicle, repair facility or amount, and they do not encode the hero scenario's answer. `tests/test_knowledge.py` enforces this.

| File (uploaded) | Title | Document ID | Version | Pages | Covers |
|---|---|---|---|---|---|
| `claims-handling-guidelines.pdf` | Auto Claims Handling Guidelines | CI-CLM-GL-101 | 4.2 | 7 | intake, evidence requirements, date-of-loss and coverage verification, reviewing photographs, police reports and estimates, inconsistent evidence, supplemental evidence, manual review and decision authority, documentation |
| `auto-coverage-guidance.pdf` | Personal Auto Coverage Guidance | CI-CLM-CV-204 | 3.1 | 5 | active-policy requirement, collision/comprehensive/liability, deductibles, pre-existing and unrelated damage, betterment, coverage uncertainty |
| `repair-estimate-review.pdf` | Repair Estimate Review Guidelines | CI-CLM-ER-310 | 2.6 | 5 | labor/parts/refinish review, estimate and evidence consistency, supplements, line items not established by the evidence, limits of photographic evidence, revised estimates, authorization boundaries, continuing supported processing |
| `claims-escalation-guidance.pdf` | Claims Escalation and Special Investigation Guidance | CI-CLM-SI-420 | 5.0 | 4 | ordinary manual review, supervisor escalation, indicators and Special Investigations referral criteria, when not to escalate, decision-support tools, communication without accusation |

## Source of truth

- `source/*.md` is authoritative. The PDFs are generated from it deterministically, with fixed metadata and no timestamps:

  ```powershell
  python knowledge/build_pdfs.py          # rebuild after editing a source
  python knowledge/build_pdfs.py --check  # verify the committed PDFs match the sources byte for byte
  ```

- Both the Markdown and the PDFs are committed, so the Foundry portal path can upload the PDFs without running code.

## What is deliberately *not* knowledge

Claim-specific material is attached to each claim conversation instead (see `agent/run_claim_review.py`). Build and test material is never uploaded:

- claim evidence under `evidence/CLM-*/`
- build provenance under `evidence/source/`, including the photo-generation records `photos.json`
- `docs/IMPLEMENTATION-SPEC.md`
- `evaluation/` expectations and results
