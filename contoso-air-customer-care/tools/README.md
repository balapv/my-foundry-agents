# Contoso Air Operations API (mock)

This is a single FastAPI service. Its one OpenAPI specification, [`openapi.json`](openapi.json), defines the three read-only operations the Foundry agent calls through **one OpenAPI tool**. The service serves deterministic synthetic data from `../data`. Customer-service reasoning lives in the agent, not here: the API returns records only. It does not recommend, rebook, or interpret policy.

| Operation (`operationId`) | Endpoint | Route module |
|---|---|---|
| `get_customer_reservations` | `GET /customers/{customerId}/reservations?confirmationCode=` | `reservation_api/router.py` |
| `get_flight_status` | `GET /flight-status/{flightNumber}?date=YYYY-MM-DD` | `flight_status_api/router.py` |
| `search_alternative_flights` | `GET /flight-search/alternatives?origin=&destination=&travelDate=&passengerCount=&preferredCabin=&preferNonstop=` | `flight_search_api/router.py` |

`openapi.json` is hand-authored and is the contract. Unit tests check that it matches the served routes and parameters exactly.

### Search semantics

`search_alternative_flights` returns every itinerary on the route and date that is not cancelled, has not yet departed, and has at least one open seat. It does not rank, recommend or decide eligibility.

- Options are in **chronological order** (departure, then arrival). `optionId` (`OPT-1`, `OPT-2`, ...) identifies a search result only. It is not a booking reference, and no seats are held.
- `passengerCount`, `preferredCabin` and `preferNonstop` are context only. They are echoed in `search` and never filter or reorder options.
- `cabinAvailability` for a connection is the **minimum per cabin across all legs**: the number of passengers who can travel in that cabin end to end. `totalSeatsAvailable` is the sum across cabins, which may be spread across different cabins.
- An empty `options` list is a normal result, not an error.

Other routes:

- `GET /openapi.json` returns the specification with `servers[0].url` set to this host. You can paste it straight into the Foundry portal.
- `GET /docs` is the Swagger UI for that same specification.
- `GET /health` is a liveness check.

### Errors

Foundry's OpenAPI tool treats any non-2xx response as a failed tool call. It ends the agent's response before the model sees the error, so the agent could not tell a customer that a reservation was not found or that a system is down. Agent-facing operations therefore always return **HTTP 200**. A failure comes back as an `error` object instead of data:

```json
{"error": {"code": "SERVICE_UNAVAILABLE", "message": "...", "httpStatus": 503, "retryable": true}}
```

`httpStatus` records the conventional status. Error codes:

- `CUSTOMER_NOT_FOUND`
- `RESERVATION_NOT_FOUND`
- `FLIGHT_NOT_FOUND`
- `SERVICE_UNAVAILABLE` (the simulated CT655 outage)
- `INVALID_REQUEST`, `INVALID_DATE`, `DATE_IN_PAST`, `UNKNOWN_AIRPORT`, `INVALID_ROUTE`, `INVALID_CABIN`

## Run locally

```powershell
# from the contoso-air-customer-care folder, with the virtual environment active
cd tools
uvicorn main:app --port 8000 --reload
```

Then open <http://localhost:8000/docs>.

> **Note:** Foundry calls OpenAPI tools from the cloud, so the agent cannot reach `localhost`. For the agent, deploy the API to a public HTTPS endpoint with `python scripts/deploy_tools.py` (Azure Container Apps), or expose your local port with a dev tunnel.

## Configuration

All settings are optional.

| Variable | Purpose |
|---|---|
| `DEMO_TODAY` | Pin the demo date (`YYYY-MM-DD`) |
| `DEMO_TIME` | Pin the time of day (`HH:MM`) in `DEMO_TIMEZONE`. Controls which of today's flights have departed and caps `lastUpdated` |
| `DEMO_TIMEZONE` | Time zone that defines the current date and time when they are not pinned. Default `America/Los_Angeles` |
| `DISABLE_FAULT_INJECTION` | `true` disables the simulated CT655 outage |
| `TOOLS_API_PUBLIC_URL` | Public base URL written into `/openapi.json`. Defaults to the request's base URL |
| `CONTOSO_DATA_DIR` | Override the data folder |

## Authentication

The demo API is anonymous and read-only. It serves fictional data only. For anything beyond a demo, put it behind managed identity or API-key authentication and use the matching OpenAPI tool authentication in Foundry.
