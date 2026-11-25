# Knowledge assets

Four fictional Contoso Air policy documents provide the agent's grounding through **File Search**.

| PDF (upload these) | Document ID | Pages |
|---|---|---|
| `flight-disruption-policy.pdf` | CA-CC-POL-014 | 6 |
| `loyalty-benefits.pdf` | CA-LOY-POL-003 | 4 |
| `meal-hotel-assistance.pdf` | CA-CC-POL-021 | 4 |
| `customer-service-escalation.pdf` | CA-CC-GDE-007 | 4 |

`source/*.md` holds the editable sources. After editing a source, rebuild and verify:

```powershell
python knowledge/build_pdfs.py          # rebuild PDFs (deterministic output)
python knowledge/build_pdfs.py --check  # verify page targets only
```

`agent/create_agent.py` uploads the four PDFs to a vector store named `contoso-air-policies` and reuses it on later runs. In the Foundry portal you can attach the same files; see `docs/foundry-ui-agent-setup.md`.

Rules that drive the hero scenario:

- **CA-CC-POL-014 §4.4:** on a Contoso Air cancellation, passengers may be reaccommodated on an eligible alternative without a change fee, and the traveling party should be kept together.
- **CA-CC-POL-014 §7–§10:** prefer the earliest same-day eligible option that keeps the party together in the original cabin. Prefer a nonstop when arrival times are comparable.
- **CA-LOY-POL-003 §6:** Gold members get priority reaccommodation, but no guaranteed seat.
- **CA-CC-POL-021:** no hotel when the disruption happens at the passenger's home airport.
