"""Create (or update) the Contoso Claims Review prompt agent in Microsoft Foundry.

What it does, in order:
  1. Uploads the four Contoso Insurance guidance PDFs in knowledge/ to one vector store (reused when
     the file contents are unchanged).
  2. Builds a PromptAgentDefinition from agent/instructions.md with two tools:
       - File Search over that vector store (company guidance only)
       - OpenAPI tool "claims_operations" from tools/openapi.json, pointed at TOOLS_API_BASE_URL
  3. Creates a new agent version and records IDs in .foundry-state.json (git-ignored).

Claim evidence is NOT uploaded here; it is attached per conversation by run_claim_review.py.

Usage:
  python agent/create_agent.py --dry-run          # print the definition, no Azure calls
  python agent/create_agent.py                    # create a new version
  python agent/create_agent.py --name X --empty-knowledge   # evaluation variant with no guidance
  python agent/create_agent.py --name X --delete  # delete an agent and its private vector store
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402


def knowledge_signature(paths: list[Path]) -> dict[str, str]:
    return {p.name: common.sha256(p.read_bytes()) for p in paths}


def ensure_vector_store(oai, state: dict, name: str, empty: bool) -> str:
    paths = [] if empty else common.knowledge_paths()
    signature = knowledge_signature(paths)
    key = f"{name}{':empty' if empty else ''}"
    existing = state["vectorStores"].get(key)
    if existing and existing.get("files") == signature:
        try:
            store = oai.vector_stores.retrieve(existing["id"])
            if store.status == "completed":
                print(f"Reusing vector store {key} ({len(signature)} files, unchanged).")
                return existing["id"]
        except Exception as exc:  # store deleted out of band
            print(f"Recorded vector store unavailable ({type(exc).__name__}); creating a new one.")
    if existing:
        delete_vector_store(oai, existing)
    store = oai.vector_stores.create(name=key, metadata={"purpose": "contoso-insurance-claims-guidance"})
    file_ids = []
    for path in paths:
        with path.open("rb") as handle:
            result = oai.vector_stores.files.upload_and_poll(vector_store_id=store.id, file=handle)
        if result.status != "completed":
            raise RuntimeError(f"Indexing {path.name} ended with status {result.status}: {result.last_error}")
        file_ids.append(result.id)
        print(f"Indexed {path.name}")
    state["vectorStores"][key] = {"id": store.id, "files": signature, "fileIds": file_ids,
                                   "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return store.id


def delete_vector_store(oai, record: dict) -> None:
    for file_id in record.get("fileIds", []):
        try:
            oai.files.delete(file_id)
        except Exception:
            pass
    try:
        oai.vector_stores.delete(record["id"])
    except Exception:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--name", help="Agent name (default: agentName in agent/config.json or config.example.json).")
    parser.add_argument("--dry-run", action="store_true", help="Print the agent definition without calling Azure.")
    parser.add_argument("--empty-knowledge", action="store_true",
                        help="Attach an empty vector store (evaluation of unavailable guidance).")
    parser.add_argument("--delete", action="store_true", help="Delete the named agent and any vector store created only for it.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    common.configure_console()
    args = parse_args(argv)
    config = common.load_config()
    name = args.name or config["agentName"]
    instructions = common.read_instructions()
    metadata = {
        "instructions_sha256": common.sha256(instructions.encode("utf-8"))[:16],
        "knowledge": "empty" if args.empty_knowledge else "contoso-guidance-v1",
        "demo": "contoso-claims-processing",
    }

    if args.dry_run:
        settings = {"FOUNDRY_MODEL_DEPLOYMENT_NAME": "<FOUNDRY_MODEL_DEPLOYMENT_NAME>",
                    "TOOLS_API_BASE_URL": "https://<claims-operations-api>"}
        definition = common.agent_definition(settings["FOUNDRY_MODEL_DEPLOYMENT_NAME"], "<vector-store-id>",
                                             settings["TOOLS_API_BASE_URL"], config, instructions)
        print(json.dumps({"name": name, "metadata": metadata,
                          "knowledgeFiles": [] if args.empty_knowledge else list(common.KNOWLEDGE_FILES),
                          "definition": definition.as_dict()}, indent=2))
        return 0

    try:
        settings = common.load_settings(require_tools_url=not args.delete)
    except common.ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2
    project = common.project_client(settings)
    oai = project.get_openai_client()
    state = common.load_state()

    if args.delete:
        try:
            project.agents.delete(agent_name=name)
            print(f"Deleted agent {name}.")
        except Exception as exc:
            print(f"Agent {name} not deleted: {type(exc).__name__}: {exc}")
        record = state["agents"].pop(name, None)
        store_key = (record or {}).get("vectorStoreKey")
        shared = any(a.get("vectorStoreKey") == store_key for a in state["agents"].values())
        if store_key and not shared and store_key in state["vectorStores"]:
            delete_vector_store(oai, state["vectorStores"].pop(store_key))
            print(f"Deleted vector store {store_key}.")
        common.save_state(state)
        return 0

    store_name = config["knowledgeVectorStoreName"]
    vector_store_id = ensure_vector_store(oai, state, store_name, args.empty_knowledge)
    common.save_state(state)
    definition = common.agent_definition(settings["FOUNDRY_MODEL_DEPLOYMENT_NAME"], vector_store_id,
                                         settings["TOOLS_API_BASE_URL"], config, instructions)
    version = project.agents.create_version(agent_name=name, definition=definition,
                                            description=config["description"], metadata=metadata)
    state["agents"][name] = {
        "version": str(version.version),
        "model": settings["FOUNDRY_MODEL_DEPLOYMENT_NAME"],
        "vectorStoreKey": f"{store_name}{':empty' if args.empty_knowledge else ''}",
        "instructionsSha256": metadata["instructions_sha256"],
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    common.save_state(state)
    print(f"Created {name} version {version.version} on {settings['FOUNDRY_MODEL_DEPLOYMENT_NAME']} "
          f"with File Search ({'empty' if args.empty_knowledge else len(common.KNOWLEDGE_FILES)} guidance files) "
          f"and OpenAPI tool {config['openApiToolName']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
