"""Build tools/openapi.json, the Claims Operations API contract given to Foundry.

Schemas are composed from reusable Python fragments and written fully inlined
(no $ref), so the document is self-contained for the Foundry OpenAPI tool.

Run from the contoso-claims-processing/ directory:

    python tools/build_openapi.py          # write tools/openapi.json
    python tools/build_openapi.py --check  # verify tools/openapi.json is current
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "openapi.json"
PLACEHOLDER_SERVER = "https://YOUR-TOOLS-API-HOST"

ERROR_CODES = [
    "CLAIM_NOT_FOUND",
    "POLICY_NOT_FOUND",
    "CUSTOMER_NOT_FOUND",
    "VEHICLE_NOT_FOUND",
    "INVALID_REQUEST",
    "SERVICE_UNAVAILABLE",
]
CLAIM_TYPES = ["Collision", "Comprehensive", "Property Damage Liability"]
CAUSES_OF_LOSS = [
    "Two-vehicle collision",
    "Single-vehicle collision",
    "Hit while parked",
    "Animal strike",
    "Glass breakage",
    "Hail",
    "Theft",
    "Vandalism",
    "Property damage to another vehicle",
]
CLAIM_STATUSES = [
    "Submitted",
    "In Review",
    "Pending Documentation",
    "Closed - Paid",
    "Closed - Denied",
    "Closed - Withdrawn",
]
CLOSURE_REASONS = ["Payment issued", "Repair cost below deductible", "Withdrawn by policyholder"]
REPORT_CHANNELS = ["Online", "Mobile app", "Phone", "Agent"]
DOCUMENT_TYPES = [
    "Claim form",
    "Photograph",
    "Police report",
    "Repair estimate",
    "Repair invoice",
    "Total loss valuation",
]
DOCUMENT_SOURCES = ["Policyholder", "Police agency", "Repair facility", "Other party", "Contoso Insurance"]
POLICY_STATUSES = ["Active", "Expired", "Cancelled"]
CANCELLATION_REASONS = ["Insured request", "Non-payment of premium", "Rewritten to new policy"]
DRIVER_RELATIONSHIPS = ["Named insured", "Spouse/partner", "Household member"]
POLICY_COVERAGE_CODES = ["BI", "PD", "UMBI", "PIP", "MED"]
VEHICLE_COVERAGE_CODES = ["COLL", "COMP", "RENT", "ROAD", "GAP"]
LIMIT_TYPES = ["Per person", "Per accident", "Per day", "Maximum per loss", "Per occurrence"]
OWNERSHIP_TYPES = ["Owned", "Financed", "Leased"]
PRIMARY_USES = ["Commute", "Pleasure", "Business"]
NETWORK_STATUSES = ["Contoso Direct Repair Network", "Independent"]
TIME_ZONES = ["America/Los_Angeles", "America/Phoenix", "America/Denver"]

# ---------------------------------------------------------------------------
# Schema fragments
# ---------------------------------------------------------------------------


def string(description: str, **extra) -> dict:
    return {"type": "string", "description": description, **extra}


def nullable(schema: dict) -> dict:
    return {**schema, "nullable": True}


def date(description: str) -> dict:
    return string(description, format="date")


def timestamp(description: str) -> dict:
    return string(description, format="date-time")


def money(description: str) -> dict:
    return {"type": "number", "description": description + " US dollars."}


def integer(description: str) -> dict:
    return {"type": "integer", "description": description}


def boolean(description: str) -> dict:
    return {"type": "boolean", "description": description}


def enum(description: str, values: list[str]) -> dict:
    return string(description, enum=values)


def array(description: str, items: dict) -> dict:
    return {"type": "array", "description": description, "items": items}


def obj(description: str, properties: dict, *, required: bool = True) -> dict:
    schema = {"type": "object", "description": description, "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(properties)
    return schema


def address(description: str) -> dict:
    return obj(
        description,
        {
            "street": string("Street address."),
            "city": string("City."),
            "state": string("Two-letter US state code."),
            "postalCode": string("Five-digit ZIP code."),
        },
    )


RECORDS_AS_OF = timestamp(
    "UTC time at which this snapshot of the claims system was taken. Statuses and dates are as of this time."
)
CLAIM_ID = string("Claim ID, format CLM-nnnnn. Archived claims use AC-yyyy-nnnnn.")
POLICY_ID = string("Policy ID, format PAP-nnnnnnn.")
CUSTOMER_ID = string("Customer ID, format CUST-nnnnn.")
VEHICLE_ID = string("Vehicle ID, format VEH-nnnnn.")

ERROR = obj(
    "Present only when the operation failed. When present, no data fields are returned. "
    "Do not substitute or invent the requested information.",
    {
        "code": enum("Machine-readable error code.", ERROR_CODES),
        "message": string("Human-readable description of the error."),
        "httpStatus": integer("Conventional HTTP status for this error (400, 404 or 503)."),
        "retryable": boolean("True only when retrying the same request later may succeed (SERVICE_UNAVAILABLE)."),
    },
)

LIMIT = obj(
    "A coverage limit.",
    {"limitType": enum("What the limit applies to.", LIMIT_TYPES), "amount": money("Limit amount.")},
)


def coverage(description: str, codes: list[str]) -> dict:
    return obj(
        description,
        {
            "coverageCode": enum("Coverage code.", codes),
            "coverageName": string("Coverage name as shown on the declarations page."),
            "deductible": nullable(money("Deductible for this coverage; null when the coverage has no deductible.")),
            "limits": array("Limits for this coverage. Empty when none are stated on the declarations page.", LIMIT),
        },
    )


DOCUMENT = obj(
    "A document or photograph received for the claim.",
    {
        "documentId": string("Document ID, format DOC-nnnnn-nn."),
        "documentType": enum("Document type.", DOCUMENT_TYPES),
        "title": string("Document title as indexed in the claim file."),
        "source": enum("Who supplied the document.", DOCUMENT_SOURCES),
        "receivedAt": timestamp("UTC time the document was received."),
    },
)

CLAIM = obj(
    "Claim record as stored in the claims system.",
    {
        "claimId": CLAIM_ID,
        "customerId": CUSTOMER_ID,
        "policyId": POLICY_ID,
        "vehicleId": VEHICLE_ID,
        "claimType": enum("Claim type as recorded at first notice of loss.", CLAIM_TYPES),
        "causeOfLoss": enum("Cause of loss as recorded at first notice of loss.", CAUSES_OF_LOSS),
        "status": enum("Current claim status.", CLAIM_STATUSES),
        "lossDate": date("Date of loss, local to lossTimeZone."),
        "lossTime": string("Approximate time of loss (HH:MM, 24-hour), local to lossTimeZone.", pattern="^\\d{2}:\\d{2}$"),
        "lossTimeZone": enum("IANA time zone of the loss location.", TIME_ZONES),
        "lossLocation": obj(
            "Where the loss occurred.",
            {
                "description": string("Location as described in the report."),
                "street": nullable(string("Street or block, when reported.")),
                "city": string("City."),
                "state": string("Two-letter US state code."),
            },
        ),
        "reportedAt": timestamp("UTC time the claim was reported to Contoso Insurance."),
        "reportChannel": enum("Channel used to report the claim.", REPORT_CHANNELS),
        "description": string("The policyholder's description of the loss, as reported."),
        "reportedDamage": obj(
            "Damage to the insured vehicle as reported by the policyholder at first notice of loss.",
            {
                "areas": array("Damaged areas selected by the reporter.", string("Vehicle area.")),
                "summary": string("Reporter's damage summary."),
            },
        ),
        "vehicleDrivable": boolean("Whether the vehicle was reported as drivable."),
        "injuriesReported": boolean("Whether any injury was reported."),
        "otherParties": array(
            "Other parties involved in the loss. Empty when none were reported.",
            obj(
                "Another party involved in the loss.",
                {
                    "role": string("Role of the party, for example Other driver."),
                    "name": string("Party name as reported."),
                    "vehicleDescription": string("Party's vehicle as reported."),
                    "insurer": string("Party's insurer as reported."),
                },
            ),
        ),
        "policeReport": obj(
            "Police involvement as reported. This records whether a report was made; whether a police report "
            "document has been received is shown in documents.",
            {
                "reportedToPolice": boolean("Whether the loss was reported to police."),
                "agency": nullable(string("Police agency.")),
                "reportNumber": nullable(string("Police report number.")),
            },
        ),
        "repairFacilityId": nullable(string("ID of the repair facility selected for the claim, format RF-nnn.")),
        "estimate": nullable(
            obj(
                "Reference to the repair estimate of record. The estimate document itself is listed in documents.",
                {
                    "estimateId": string("Estimate ID assigned by the repair facility."),
                    "repairFacilityId": string("Repair facility that wrote the estimate."),
                    "estimateDate": date("Date the estimate was written."),
                    "grossAmount": money("Estimate grand total before the deductible."),
                },
            )
        ),
        "documents": array(
            "Documents and photographs received for the claim, in the order received. Empty when none have "
            "been received.",
            DOCUMENT,
        ),
        "settlement": nullable(
            obj(
                "Payment recorded on a closed claim; null when no payment was recorded.",
                {
                    "settledAmount": money("Agreed loss amount before the deductible."),
                    "deductibleApplied": money("Deductible applied."),
                    "totalPaid": money("Amount paid."),
                },
            )
        ),
        "closedDate": nullable(date("Date the claim was closed; null while open.")),
        "closureReason": nullable(enum("Recorded closure reason; null while open.", CLOSURE_REASONS)),
        "createdAt": timestamp("UTC time the claim record was created."),
        "lastUpdatedAt": timestamp("UTC time the claim record was last updated."),
    },
)

REPAIR_FACILITY = nullable(
    obj(
        "Repair facility selected for the claim; null when none has been selected.",
        {
            "repairFacilityId": string("Repair facility ID, format RF-nnn."),
            "name": string("Facility name."),
            "networkStatus": enum("Contoso network participation.", NETWORK_STATUSES),
            "address": address("Facility address."),
            "phone": string("Facility phone number."),
        },
    )
)

POLICY = obj(
    "Personal auto policy record. Coverage and deductible facts are as stated on the declarations page; this "
    "record does not interpret them for any particular loss.",
    {
        "policyId": POLICY_ID,
        "customerId": CUSTOMER_ID,
        "productName": string("Policy product."),
        "status": enum(
            "Policy status as of recordsAsOf. Expired: the term ended without renewal. Cancelled: see cancellation.",
            POLICY_STATUSES,
        ),
        "ratingState": string("Two-letter state in which the policy is written."),
        "inceptionDate": date("Date the policy was first issued."),
        "termMonths": integer("Length of the current term in months (6 or 12)."),
        "termEffectiveDate": date("Start of the current (or last) policy term, inclusive, 12:01 AM local time."),
        "termExpirationDate": date("End of the current (or last) policy term, 12:01 AM local time."),
        "cancellation": nullable(
            obj(
                "Cancellation details; null when the policy has not been cancelled.",
                {
                    "effectiveDate": date("Date the cancellation took effect, 12:01 AM local time."),
                    "reason": enum("Recorded cancellation reason.", CANCELLATION_REASONS),
                },
            )
        ),
        "paymentPlan": string("Premium payment plan."),
        "termPremium": money("Premium for the current term."),
        "drivers": array(
            "Drivers listed on the policy.",
            obj(
                "Listed driver.",
                {
                    "fullName": string("Driver name."),
                    "relationship": enum("Relationship to the named insured.", DRIVER_RELATIONSHIPS),
                    "licenseState": string("State that issued the driver's license."),
                },
            ),
        ),
        "policyCoverages": array(
            "Coverages that apply to the policy as a whole.",
            coverage("Policy-level coverage.", POLICY_COVERAGE_CODES),
        ),
        "vehicles": array(
            "Vehicles listed on the policy, including vehicles since removed. Vehicle-level coverages and "
            "deductibles are recorded per vehicle.",
            obj(
                "Vehicle listing on the policy.",
                {
                    "vehicleId": VEHICLE_ID,
                    "addedDate": date("Date the vehicle was added to the policy."),
                    "removedDate": nullable(date("Date the vehicle was removed from the policy; null if still listed.")),
                    "lossPayee": nullable(string("Lienholder or lessor recorded as loss payee; null if none.")),
                    "coverages": array(
                        "Vehicle-level coverages. Empty when only liability coverages apply to this vehicle.",
                        coverage("Vehicle-level coverage.", VEHICLE_COVERAGE_CODES),
                    ),
                },
            ),
        ),
    },
)

VEHICLE = obj(
    "Vehicle record.",
    {
        "vehicleId": VEHICLE_ID,
        "vin": string("17-character vehicle identification number (synthetic)."),
        "year": integer("Model year."),
        "make": string("Manufacturer."),
        "model": string("Model."),
        "trim": string("Trim level."),
        "bodyStyle": string("Body style."),
        "exteriorColor": string("Exterior color."),
        "drivetrain": string("Drivetrain."),
        "fuelType": string("Fuel type."),
        "ownerCustomerId": CUSTOMER_ID,
        "acquiredDate": date("Date the owner acquired the vehicle."),
        "disposedDate": nullable(date("Date the owner disposed of the vehicle; null if still owned.")),
        "ownership": obj(
            "Ownership arrangement.",
            {
                "type": enum("Ownership type.", OWNERSHIP_TYPES),
                "lienholder": nullable(string("Lienholder or lessor; null when owned outright.")),
            },
        ),
        "primaryUse": enum("Primary use.", PRIMARY_USES),
        "garaging": obj(
            "Where the vehicle is principally garaged.",
            {"city": string("City."), "state": string("Two-letter US state code.")},
        ),
        "equipment": array("Factory equipment recorded for the vehicle.", string("Equipment item.")),
    },
)

HISTORY_ENTRY = obj(
    "One claim on the customer's record.",
    {
        "claimId": CLAIM_ID,
        "recordSource": enum(
            "Where the record is held. Claims system: current claims system (use get_claim for detail). "
            "Archive: closed claims migrated from the previous system; summary only.",
            ["Claims system", "Archive"],
        ),
        "policyId": POLICY_ID,
        "vehicleId": VEHICLE_ID,
        "vehicleDescription": string("Year, make and model."),
        "claimType": enum("Claim type.", CLAIM_TYPES),
        "causeOfLoss": enum("Cause of loss.", CAUSES_OF_LOSS),
        "lossDate": date("Date of loss, local time."),
        "reportedDate": date("Date the claim was reported, local to the loss location."),
        "status": enum("Claim status as of recordsAsOf.", CLAIM_STATUSES),
        "closedDate": nullable(date("Date closed; null while open.")),
        "settledAmount": nullable(money("Agreed loss amount before the deductible; null if no payment recorded.")),
        "deductibleApplied": nullable(money("Deductible applied; null if no payment recorded.")),
        "totalPaid": nullable(money("Amount paid; null if no payment recorded.")),
    },
)


def path_parameter(name: str, description: str, pattern: str) -> dict:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string", "pattern": pattern},
    }


def response(description: str, properties: dict) -> dict:
    schema = {
        "type": "object",
        "description": "On success, the data fields. On failure, only error.",
        "properties": {**properties, "error": ERROR},
        "additionalProperties": False,
    }
    return {"200": {"description": description, "content": {"application/json": {"schema": schema}}}}


ERROR_NOTE = (
    "Failures are returned with HTTP 200 and an error object instead of data (no other fields), so that the "
    "agent can read and explain them. Possible error codes: {codes}. Only SERVICE_UNAVAILABLE is retryable."
)
ID_NOTE = "IDs are case-insensitive; surrounding spaces are ignored."


def operation(operation_id: str, summary: str, description: str, parameter: dict, codes: list[str], ok: str, data: dict) -> dict:
    codes = codes + ["INVALID_REQUEST", "SERVICE_UNAVAILABLE"]
    return {
        "get": {
            "operationId": operation_id,
            "summary": summary,
            "description": f"{description} {ID_NOTE} {ERROR_NOTE.format(codes=', '.join(codes))}",
            "parameters": [parameter],
            "responses": response(ok, data),
        }
    }


def build_spec() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Contoso Insurance Claims Operations API",
            "version": "1.0.0",
            "description": (
                "Read-only Contoso Insurance claims-system records for the claims review agent: claims, policies, "
                "customer claim history and vehicles. The API returns stored business facts only. It does not "
                "interpret policy language, decide coverage, compare or assess claim evidence, score risk, or "
                "recommend claim actions. Dates are ISO 8601. Dates of loss are local to the loss location; "
                "timestamps ending in Z are UTC. Each response includes recordsAsOf, the time of the data snapshot. "
                "Errors are returned as HTTP 200 with an error object so the agent can explain them. All data is "
                "synthetic; Contoso Insurance is fictional."
            ),
        },
        "servers": [{"url": PLACEHOLDER_SERVER}],
        "paths": {
            "/claims/{claimId}": operation(
                "get_claim",
                "Get a claim record",
                "Returns the stored claim record: customer, policy and vehicle references, loss details, damage "
                "reported at first notice of loss, other parties, police involvement, status, the documents and "
                "photographs received (evidence references), the selected repair facility and the estimate of "
                "record reference. Documents are listed by reference; their content is not returned.",
                path_parameter("claimId", "Claim ID, for example CLM-10001.", "^[Cc][Ll][Mm]-\\d{5}$"),
                ["CLAIM_NOT_FOUND"],
                "Claim record and selected repair facility, or an error.",
                {"recordsAsOf": RECORDS_AS_OF, "claim": CLAIM, "repairFacility": REPAIR_FACILITY},
            ),
            "/policies/{policyId}": operation(
                "get_policy",
                "Get a personal auto policy",
                "Returns policy facts: policyholder, status, current term dates, cancellation details, listed "
                "drivers, policy-level coverages and limits, and each listed vehicle with its dates on the policy, "
                "vehicle-level coverages and deductibles and loss payee. vehicleDetails identifies each listed "
                "vehicle. The record states what the policy contains; it does not determine whether a loss is covered.",
                path_parameter("policyId", "Policy ID, for example PAP-1000001.", "^[Pp][Aa][Pp]-\\d{7}$"),
                ["POLICY_NOT_FOUND"],
                "Policy record with policyholder and listed-vehicle identification, or an error.",
                {
                    "recordsAsOf": RECORDS_AS_OF,
                    "policy": POLICY,
                    "policyholder": obj(
                        "Named insured.",
                        {
                            "customerId": CUSTOMER_ID,
                            "fullName": string("Policyholder name."),
                            "address": address("Mailing address."),
                        },
                    ),
                    "vehicleDetails": array(
                        "Identification of each vehicle in policy.vehicles, in the same order.",
                        obj(
                            "Listed vehicle identification.",
                            {
                                "vehicleId": VEHICLE_ID,
                                "vin": string("Vehicle identification number."),
                                "description": string("Year, make, model and trim."),
                                "bodyStyle": string("Body style."),
                            },
                        ),
                    ),
                },
            ),
            "/customers/{customerId}/claim-history": operation(
                "get_customer_claim_history",
                "Get a customer's claim history",
                "Returns every claim on record for the customer, open and closed, from the current claims system "
                "and from the archive of the previous system, most recent date of loss first. The list includes "
                "any claim currently being reviewed. Amounts are shown where a payment was recorded. A customer "
                "with no claims returns an empty claims list and claimCount 0; that is not an error. Prior claims "
                "are factual history only.",
                path_parameter("customerId", "Customer ID, for example CUST-10001.", "^[Cc][Uu][Ss][Tt]-\\d{5}$"),
                ["CUSTOMER_NOT_FOUND"],
                "Customer claim history, or an error.",
                {
                    "recordsAsOf": RECORDS_AS_OF,
                    "customer": obj(
                        "Customer.",
                        {
                            "customerId": CUSTOMER_ID,
                            "fullName": string("Customer name."),
                            "customerSince": date("Date the customer relationship began."),
                        },
                    ),
                    "claimCount": integer("Number of claims in claims."),
                    "claims": array("Claims on record, most recent date of loss first.", HISTORY_ENTRY),
                },
            ),
            "/vehicles/{vehicleId}": operation(
                "get_vehicle",
                "Get a vehicle record",
                "Returns the vehicle record (synthetic VIN, year, make, model, trim, body style, color, ownership, "
                "use, garaging and recorded equipment), its owner, and every policy listing for the vehicle with "
                "its dates and coverage codes. listedOnActivePolicy is true when the vehicle is currently listed "
                "(no removedDate) on a policy whose status is Active as of recordsAsOf.",
                path_parameter("vehicleId", "Vehicle ID, for example VEH-10001.", "^[Vv][Ee][Hh]-\\d{5}$"),
                ["VEHICLE_NOT_FOUND"],
                "Vehicle record, owner and policy listings, or an error.",
                {
                    "recordsAsOf": RECORDS_AS_OF,
                    "vehicle": VEHICLE,
                    "owner": obj(
                        "Registered owner.",
                        {"customerId": CUSTOMER_ID, "fullName": string("Owner name.")},
                    ),
                    "insurance": obj(
                        "Policy listings for this vehicle.",
                        {
                            "listedOnActivePolicy": boolean(
                                "True when the vehicle is listed, without a removedDate, on a policy with status Active."
                            ),
                            "policies": array(
                                "Every policy on which the vehicle is or was listed. Empty if none.",
                                obj(
                                    "Policy listing.",
                                    {
                                        "policyId": POLICY_ID,
                                        "policyStatus": enum("Policy status as of recordsAsOf.", POLICY_STATUSES),
                                        "addedDate": date("Date the vehicle was added to the policy."),
                                        "removedDate": nullable(date("Date removed; null if still listed.")),
                                        "coverageCodes": array(
                                            "Vehicle-level coverage codes on this listing.",
                                            enum("Coverage code.", VEHICLE_COVERAGE_CODES),
                                        ),
                                    },
                                ),
                            ),
                        },
                    ),
                },
            ),
        },
    }


def render() -> bytes:
    return (json.dumps(build_spec(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify tools/openapi.json is current; write nothing")
    args = parser.parse_args(argv)
    content = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != content:
            print("tools/openapi.json is out of date; run python tools/build_openapi.py", file=sys.stderr)
            return 1
        print("tools/openapi.json is current.")
        return 0
    OUTPUT.write_bytes(content)
    print(f"wrote tools/openapi.json ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
