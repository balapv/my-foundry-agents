"""Create (or update) the Contoso Air Customer Care prompt agent in Microsoft Foundry with code.

This is "Option B - Build with code". It produces the same agent you can build in the Foundry
portal (Option A): the same instructions, the same four policy PDFs in a File Search vector
store, and the same Contoso Air Operations OpenAPI tool (three operations, one specification).

    python agent/create_agent.py                 # create the vector store if needed, then a new agent version
    python agent/create_agent.py --test          # ...then send the hero prompt to the new version
    python agent/create_agent.py --dry-run       # print the agent definition without calling Azure
    python agent/create_agent.py --refresh-knowledge   # re-upload the policy PDFs to a new vector store
    python agent/create_agent.py --no-activate   # create a version without making it the active version

Every run creates a new agent version; the number is assigned by Foundry. The new version is recorded
as activeAgentVersion in .foundry-state.json (git-ignored). Clients resolve the version to invoke from
FOUNDRY_AGENT_VERSION, then activeAgentVersion, then the agent's latest version.

Requires FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT_NAME and TOOLS_API_BASE_URL in .env,
and an Azure sign-in (az login) with the Foundry User role or higher on the project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.foundry_common import (  # noqa: E402
    REPO_ROOT,
    ConfigError,
    agent_metadata,
    ask_agent,
    build_agent_definition,
    clean_customer_text,
    configure_console,
    create_conversation,
    get_settings,
    load_config,
    read_state,
    resolve_agent_version,
    validate_agent_name,
    validate_tools_url,
    write_state,
)

DRY_RUN_VECTOR_STORE = "vs_DRY_RUN_PLACEHOLDER"


def knowledge_hash(files: list[str]) -> str:
    """Short content hash of the policy PDFs, stored on the vector store to detect stale knowledge."""
    digest = hashlib.sha256()
    for relative in files:
        digest.update(Path(relative).name.encode("utf-8"))
        digest.update((REPO_ROOT / relative).read_bytes())
    return digest.hexdigest()[:16]


def find_vector_store(openai_client, name: str, expected_files: int, content_hash: str):
    """Reuse an existing, fully indexed vector store with the configured name and the same PDF content."""
    for store in openai_client.vector_stores.list(limit=100):
        if store.name != name:
            continue
        if (getattr(store, "metadata", None) or {}).get("knowledgeHash") != content_hash:
            print(f"  Ignoring vector store {store.id}: its documents differ from the current knowledge PDFs.")
            continue
        counts = getattr(store, "file_counts", None)
        if counts is not None and counts.completed >= expected_files and counts.failed == 0:
            return store
        print(f"  Ignoring vector store {store.id}: {getattr(counts, 'completed', 0)}/{expected_files} files indexed.")
    return None


def create_vector_store(openai_client, name: str, files: list[str], content_hash: str):
    print(f"  Creating vector store '{name}' and uploading {len(files)} policy documents...")
    store = openai_client.vector_stores.create(
        name=name, metadata={"sample": "contoso-air-customer-care", "knowledgeHash": content_hash})
    for relative in files:
        path = REPO_ROOT / relative
        with path.open("rb") as handle:
            result = openai_client.vector_stores.files.upload_and_poll(vector_store_id=store.id, file=handle)
        print(f"    {path.name}: {result.status}")
        if result.status != "completed":
            raise RuntimeError(f"Indexing {path.name} failed: {getattr(result, 'last_error', None)}")
    return store


def ensure_vector_store(openai_client, config: dict, refresh: bool) -> str:
    knowledge = config["knowledge"]
    files = knowledge["files"]
    missing = [f for f in files if not (REPO_ROOT / f).exists()]
    if missing:
        raise ConfigError(f"Knowledge files not found: {missing}. Run python knowledge/build_pdfs.py.")
    content_hash = knowledge_hash(files)
    store = None if refresh else find_vector_store(openai_client, knowledge["vectorStoreName"], len(files), content_hash)
    if store is not None:
        print(f"  Reusing vector store '{store.name}' ({store.id}).")
        return store.id
    return create_vector_store(openai_client, knowledge["vectorStoreName"], files, content_hash).id


def _short(value, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + f"... ({len(text)} chars)"


def print_turn(result, output_limit: int = 600) -> None:
    print("\nTool activity (in call order):")
    for number, call in enumerate(result.tool_calls, start=1):
        print(f"  {number}. [{call.category or call.type}] {call.name}")
        if call.arguments:
            print(f"     arguments: {_short(call.arguments, 400)}")
        if call.category == "knowledge" and isinstance(call.output, list):
            for hit in call.output[:5]:
                hit = hit if isinstance(hit, dict) else {}
                snippet = " ".join(str(hit.get("text", "")).split())
                print(f"     result:    {hit.get('filename')} | {_short(snippet, 200)}")
        elif call.output is not None:
            print(f"     output:    {_short(call.output, output_limit)}")
    print("\nAgent reply:\n" + clean_customer_text(result.text))


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the agent definition without calling Azure")
    parser.add_argument("--test", action="store_true", help="send the hero prompt to the new agent version")
    parser.add_argument("--prompt", help="with --test: send this prompt instead of the hero prompt")
    parser.add_argument("--refresh-knowledge", action="store_true", help="always create a new vector store")
    parser.add_argument("--no-activate", action="store_true",
                        help="create the version without recording it as the active version in .foundry-state.json")
    args = parser.parse_args()

    config = load_config()
    settings = get_settings(config)
    try:
        validate_agent_name(settings.agent_name)
        if args.dry_run:
            tools_url = settings.tools_api_base_url or "https://YOUR-TOOLS-API-HOST"
            definition = build_agent_definition(config, settings.model_deployment or "YOUR-MODEL-DEPLOYMENT",
                                                tools_url, DRY_RUN_VECTOR_STORE)
            print(json.dumps({"agent_name": settings.agent_name, "description": config["description"],
                              "metadata": agent_metadata(config), "definition": definition.as_dict()}, indent=2))
            return 0
        settings.require("project_endpoint", "model_deployment", "tools_api_base_url")
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    for warning in validate_tools_url(settings.tools_api_base_url):
        print(f"WARNING: {warning}")

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    print(f"Connecting to Foundry project {settings.project_endpoint}")
    with DefaultAzureCredential() as credential, \
            AIProjectClient(endpoint=settings.project_endpoint, credential=credential) as project, \
            project.get_openai_client() as openai_client:
        print("Step 1/3: knowledge")
        vector_store_id = ensure_vector_store(openai_client, config, args.refresh_knowledge)

        print("Step 2/3: agent definition (instructions, File Search, Operations API OpenAPI tool)")
        definition = build_agent_definition(config, settings.model_deployment, settings.tools_api_base_url,
                                            vector_store_id)

        print(f"Step 3/3: creating a new version of agent '{settings.agent_name}'")
        agent = project.agents.create_version(
            agent_name=settings.agent_name,
            definition=definition,
            description=config["description"],
            metadata=agent_metadata(config),
        )
        print(f"  Created {agent.name} version {agent.version} (id {agent.id}) using model {settings.model_deployment}.")

        state = read_state()
        version = str(agent.version)
        state.update({"agentName": agent.name, "latestAgentVersion": version, "vectorStoreId": vector_store_id})
        versions = state.setdefault("agentVersions", [])
        if version not in versions:
            versions.append(version)
        if not args.no_activate:
            state["activeAgentVersion"] = version
        write_state(state)
        print("  Saved resource IDs to .foundry-state.json (git-ignored) for cleanup.")

        active, source = resolve_agent_version(settings)
        print(f"  Clients (web app, evaluations) will use version {active or 'latest'} (from {source}).")
        if settings.agent_version and settings.agent_version != version:
            print(f"  NOTE: FOUNDRY_AGENT_VERSION={settings.agent_version} pins an older version. Set it to "
                  f"{version}, or clear it, to use the version just created.")

        if args.test:
            prompt = args.prompt or config["heroPrompt"]
            print(f"\nTesting version {version} as {settings.demo_customer_id}:")
            print(f"  > {prompt}")
            handle = create_conversation(openai_client, settings.demo_customer_id)
            result = ask_agent(openai_client, handle, prompt, agent.name, version, include_search_results=True)
            print_turn(result)

    print("\nDone. Open the agent in the Foundry portal under Build > Agents, or run the web app:"
          "\n  python -m uvicorn server:app --app-dir webapp/backend --port 8080")
    return 0


if __name__ == "__main__":
    sys.exit(main())
