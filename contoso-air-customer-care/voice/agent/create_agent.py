"""Create (or update) the Contoso Air Customer Care VOICE agent in Microsoft Foundry with code.

Demo 1B, Phase V1. Builds the same voice agent you can build in the Foundry portal (voice/README.md):

  1. A toolbox version with the shared Contoso Air Operations OpenAPI spec (tools/openapi.json,
     unchanged) and File Search over the shared policy vector store created by Demo 1A.
     Voice agents accept tools only through a toolbox (or function/MCP/system tools), so the
     OpenAPI and File Search tools are packaged in one toolbox.
  2. A new version of the voice agent (kind "voice") that references that toolbox version, with
     voice-native instructions, the customer_id session input, audio, turn detection and greeting.

    python voice/agent/create_agent.py --dry-run     # print toolbox + agent definitions, no Azure calls
    python voice/agent/create_agent.py               # new toolbox version + new voice agent version
    python voice/agent/create_agent.py --model gpt-6.1-sol --model-type self_deployed
    python voice/agent/create_agent.py --reuse-toolbox   # new agent version on the active toolbox version
    python voice/agent/create_agent.py --export-openapi voice/openapi.toolbox.json   # spec for the portal path
    python voice/agent/create_agent.py --reuse-toolbox --portal-default   # portal playground can start sessions

Every run creates new versions; Foundry assigns the numbers. They are recorded in
voice/.voice-state.json (git-ignored). Demo 1A's agent, vector store and .foundry-state.json are only read.

Requires FOUNDRY_PROJECT_ENDPOINT and TOOLS_API_BASE_URL in .env, the Demo 1A vector store
(from .foundry-state.json or FOUNDRY_VECTOR_STORE_ID), and an Azure sign-in (az login).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_common import (  # noqa: E402
    ConfigError,
    build_toolbox_tools,
    build_voice_definition,
    load_voice_config,
    read_voice_state,
    resolve_vector_store_id,
    toolbox_compatible_spec,
    voice_metadata,
    voice_settings,
    write_voice_state,
)

from agent.foundry_common import (  # noqa: E402
    configure_console,
    load_tool_spec,
    validate_agent_name,
    validate_tools_url,
)

DRY_RUN_VECTOR_STORE = "vs_DRY_RUN_PLACEHOLDER"
DRY_RUN_TOOLBOX_VERSION = "TOOLBOX_VERSION_ASSIGNED_BY_FOUNDRY"


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the definitions without calling Azure")
    parser.add_argument("--model", help="override the model (managed model name or deployment name)")
    parser.add_argument("--model-type", choices=["managed", "self_deployed"], help="override the model type")
    parser.add_argument("--vector-store-id", help="override the shared policy vector store ID")
    parser.add_argument("--reuse-toolbox", action="store_true",
                        help="reference the toolbox version in voice/.voice-state.json instead of creating one")
    parser.add_argument("--no-activate", action="store_true",
                        help="do not record the new version as activeAgentVersion in voice/.voice-state.json")
    parser.add_argument("--export-openapi", metavar="PATH",
                        help="write the toolbox-compatible Operations OpenAPI spec (with your TOOLS_API_BASE_URL) "
                             "to PATH for the Foundry portal path, then exit without calling Azure")
    parser.add_argument("--portal-default", nargs="?", const="", metavar="CUSTOMER_ID",
                        help="demo only: make customer_id optional with this default (default: the "
                             "config's demo customer) so the Foundry portal playground, which sends no "
                             "structured inputs, can start a session. Without it, customer_id is required.")
    args = parser.parse_args()

    config = load_voice_config()
    settings = voice_settings(config)
    model = args.model or settings["model"]
    model_type = args.model_type or settings["model_type"]
    toolbox_name = config["toolbox"]["name"]
    portal_default = None
    if args.portal_default is not None:
        portal_default = (args.portal_default or settings["customer_id"]).strip()
        if not re.fullmatch(r"CUST-\d{4}", portal_default):
            print(f"Configuration error: --portal-default must look like CUST-1234, got {portal_default!r}.",
                  file=sys.stderr)
            return 2
    try:
        validate_agent_name(settings["agent_name"])
        validate_agent_name(toolbox_name)
        if args.export_openapi:
            if not settings["tools_api_base_url"]:
                raise ConfigError("Missing configuration: TOOLS_API_BASE_URL (set it in .env).")
            spec = toolbox_compatible_spec(
                load_tool_spec(config["toolbox"]["openapi"]["specFile"], settings["tools_api_base_url"]))
            out = Path(args.export_openapi)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote the toolbox OpenAPI spec to {out}. It contains your tools API URL: do not commit it.")
            return 0
        if args.dry_run:
            tools_url = settings["tools_api_base_url"] or "https://YOUR-TOOLS-API-HOST"
            vector_store_id, _ = resolve_vector_store_id(settings, args.vector_store_id)
            tools = build_toolbox_tools(config, tools_url, vector_store_id or DRY_RUN_VECTOR_STORE)
            definition = build_voice_definition(config, model, model_type, toolbox_name, DRY_RUN_TOOLBOX_VERSION,
                                                portal_default)
            print(json.dumps({
                "toolbox": {"name": toolbox_name, "description": config["toolbox"]["description"],
                            "tools": [t.as_dict() for t in tools]},
                "agent": {"agent_name": settings["agent_name"], "description": config["description"],
                          "metadata": voice_metadata(config), "definition": definition.as_dict()},
            }, indent=2))
            return 0
        missing = [n for n, k in (("FOUNDRY_PROJECT_ENDPOINT", "project_endpoint"),
                                  ("TOOLS_API_BASE_URL", "tools_api_base_url")) if not settings[k]]
        if missing:
            raise ConfigError(f"Missing configuration: {', '.join(missing)} (set them in .env).")
        vector_store_id, vs_source = resolve_vector_store_id(settings, args.vector_store_id)
        if not vector_store_id:
            raise ConfigError("No policy vector store found. Run Demo 1A setup (python agent/create_agent.py) "
                              "or set FOUNDRY_VECTOR_STORE_ID.")
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    for warning in validate_tools_url(settings["tools_api_base_url"]):
        print(f"WARNING: {warning}")

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    state = read_voice_state()
    print("Connecting to the Foundry project from FOUNDRY_PROJECT_ENDPOINT")
    with DefaultAzureCredential() as credential, \
            AIProjectClient(endpoint=settings["project_endpoint"], credential=credential) as project:
        if args.reuse_toolbox and state.get("toolboxName") == toolbox_name and state.get("toolboxVersion"):
            toolbox_version = str(state["toolboxVersion"])
            print(f"Step 1/2: reusing toolbox '{toolbox_name}' version {toolbox_version}")
        else:
            print(f"Step 1/2: creating a new version of toolbox '{toolbox_name}'")
            print(f"  Operations API: tools/openapi.json (3 operations); policies: vector store from {vs_source}")
            toolbox = project.toolboxes.create_version(
                name=toolbox_name,
                tools=build_toolbox_tools(config, settings["tools_api_base_url"], vector_store_id),
                description=config["toolbox"]["description"],
                metadata=voice_metadata(config),
            )
            toolbox_version = str(toolbox.version)
            print(f"  Created toolbox {toolbox_name} version {toolbox_version}.")
            state.update({"toolboxName": toolbox_name, "toolboxVersion": toolbox_version})
            state.setdefault("toolboxVersions", [])
            if toolbox_version not in state["toolboxVersions"]:
                state["toolboxVersions"].append(toolbox_version)
            write_voice_state(state)

        print(f"Step 2/2: creating a new version of voice agent '{settings['agent_name']}' "
              f"({model_type} model {model})")
        if portal_default:
            print(f"  Portal default: customer_id is optional and defaults to {portal_default} (demo only).")
        agent = project.agents.create_version(
            agent_name=settings["agent_name"],
            definition=build_voice_definition(config, model, model_type, toolbox_name, toolbox_version,
                                              portal_default),
            description=config["description"],
            metadata=voice_metadata(config),
        )
        version = str(agent.version)
        print(f"  Created {agent.name} version {version}.")
        state.update({"agentName": agent.name, "latestAgentVersion": version, "vectorStoreId": vector_store_id})
        versions = state.setdefault("agentVersions", [])
        if not any(v.get("version") == version for v in versions):
            versions.append({"version": version, "model": model, "modelType": model_type,
                             "toolboxVersion": toolbox_version, "portalDefault": portal_default})
        if not args.no_activate:
            state["activeAgentVersion"] = version
        write_voice_state(state)
        print("  Saved versions to voice/.voice-state.json (git-ignored).")

    print("\nDone. Try it in the Foundry portal (Build > Agents > open the agent > Start session), or run:"
          "\n  python voice/agent/run_session.py --scenario V1-hero")
    return 0


if __name__ == "__main__":
    sys.exit(main())
