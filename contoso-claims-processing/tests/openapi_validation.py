"""Strict response validation against the hand-authored OpenAPI 3.0 schemas.

Implements the subset of OpenAPI 3.0 schema keywords used by tools/openapi.json:
type, properties, required, additionalProperties: false, enum, nullable, items,
pattern and format (date, date-time). No external dependency.
"""

from __future__ import annotations

import re
from datetime import date, datetime

TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def _check_format(value: str, fmt: str) -> bool:
    try:
        if fmt == "date":
            return date.fromisoformat(value).isoformat() == value
        if fmt == "date-time":
            return value.endswith("Z") and datetime.fromisoformat(value.replace("Z", "+00:00")) is not None
    except ValueError:
        return False
    return True


def validate(value, schema: dict, path: str = "$") -> list[str]:
    """Return a list of violations of ``schema`` by ``value`` (empty when valid)."""
    if value is None:
        return [] if schema.get("nullable") else [f"{path}: null is not allowed"]
    expected = schema.get("type")
    if expected and not TYPE_CHECKS[expected](value):
        return [f"{path}: expected {expected}, got {type(value).__name__}"]

    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if expected == "string":
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if "format" in schema and not _check_format(value, schema["format"]):
            errors.append(f"{path}: {value!r} is not a valid {schema['format']}")
    if expected == "object":
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required property {name!r}")
        for name, item in value.items():
            if name in properties:
                errors.extend(validate(item, properties[name], f"{path}.{name}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property {name!r}")
    if expected == "array" and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(validate(item, schema["items"], f"{path}[{index}]"))
    return errors


def response_schema(spec: dict, path: str) -> dict:
    return spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]


def iter_schemas(schema: dict, path: str = "$"):
    """Yield (path, schema) for ``schema`` and every nested schema."""
    yield path, schema
    for name, child in schema.get("properties", {}).items():
        yield from iter_schemas(child, f"{path}.{name}")
    if "items" in schema:
        yield from iter_schemas(schema["items"], f"{path}[]")
