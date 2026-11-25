"""Backend for Contoso Claims Review (FastAPI).

The backend is a channel: it shows claim facts and evidence, verifies and attaches the claim's
evidence package, and relays the adjuster's messages to the existing Foundry prompt agent. It
contains no claims reasoning; the agent owns the investigation.
"""
