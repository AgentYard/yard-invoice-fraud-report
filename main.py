"""Auto-generated Chain Executor for Invoice Fraud Report."""
import asyncio
import json
import os
import time

import httpx
from fastapi import FastAPI
from jsonpath_ng import parse as jsonpath_parse

app = FastAPI(title="Invoice Fraud Report")

TOKEN = ""
# h11 (httpx's transport) rejects "Bearer " with nothing after it as an
# illegal header value — only attach Authorization when a token exists.
AGENT_HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
AGENTS = [
    {"id": "extract", "agent_id": "4dacef11-4a27-4344-975b-08283bcff78d", "name": "invoice-processor-agent", "endpoint": "http://invoice-processor-agent:9040", "timeout": 30},
    {"id": "fraud_check", "agent_id": "2f565a6b-06b9-4a66-a882-4df2238dc1d4", "name": "fraud-detector-agent", "endpoint": "http://fraud-detector-agent:9041", "timeout": 30},
    {"id": "report", "agent_id": "69d1924f-740d-47a0-9c6c-75db27f1ace6", "name": "report-generator-agent", "endpoint": "http://report-generator-agent:9035", "timeout": 30},
]

# Endpoints baked in above come from the registry at generation time —
# correct when agents run wherever they're registered, stale when this
# orchestrator is deployed alongside its own freshly-spun-up agent pods
# elsewhere (a different cluster/VPC). YARD_AGENT_ENDPOINTS (JSON, node id
# -> endpoint), set by the K8s deploy generator, overrides per-node.
_ENDPOINT_OVERRIDES = json.loads(os.environ.get("YARD_AGENT_ENDPOINTS", "{}"))
for _agent in AGENTS:
    _agent["endpoint"] = _ENDPOINT_OVERRIDES.get(_agent["id"], _agent["endpoint"])

# Incoming-edge transform per target node id — {"strategy": ..., "mappings": {...}}.
# Only the *previous* node's outgoing edge matters for a sequential chain
# (each node has at most one incoming edge here), so this is keyed by target.
# Each field is rendered as its own JSON string (double `tojson`) rather
# than inline dict/list syntax — a bare `tojson` emits real JSON
# (null/true/false), which isn't valid Python; json.loads() per field turns
# it back into a real value. Only strategy + mappings are carried through —
# the only two apply_transform() below actually reads.
EDGE_TRANSFORM_BY_TARGET = {
    "fraud_check": {
        "strategy": "explicit_mapping",
        "mappings": json.loads("{\"transaction\": \"$\"}"),
    },
    "report": {
        "strategy": "explicit_mapping",
        "mappings": json.loads("{\"data\": \"$\"}"),
    },
}


def apply_transform(transform: dict, source_output: dict) -> dict:
    """Mirrors the platform's own transforms/*.py strategies, self-contained
    since this generated container doesn't import the platform package.
    Covers passthrough + explicit_mapping (what's actually exercised by
    generated systems today); auto_negotiate/llm_transform/
    supervisor_handles fall back to passthrough rather than silently
    dropping fields — a real gap, but a safer default than guessing.
    """
    strategy = (transform or {}).get("strategy", "passthrough")
    if strategy == "explicit_mapping":
        mappings = (transform or {}).get("mappings") or {}
        if not mappings:
            return source_output
        result = {}
        for target_key, path_expr in mappings.items():
            try:
                matches = jsonpath_parse(path_expr).find(source_output)
                if matches:
                    result[target_key] = matches[0].value
            except Exception:
                pass
        return result
    return source_output


async def call_agent(endpoint: str, input_data: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(endpoint, json={"input": input_data}, headers=AGENT_HEADERS, timeout=180)
        resp.raise_for_status()
        return resp.json()


@app.post("/invoke")
async def invoke(input: dict):
    current = input.get("input", input)
    trace = []
    for i, agent in enumerate(AGENTS):
        transform = EDGE_TRANSFORM_BY_TARGET.get(agent["id"])
        if transform is not None:
            current = apply_transform(transform, current)
        start = time.monotonic()
        try:
            result = await call_agent(agent["endpoint"], current)
            duration_ms = int((time.monotonic() - start) * 1000)
            # Mission Control's trace step renderer keys rows by `step` and
            # reads `agent_name`/`duration_ms` (matches the local
            # chain_executor's own trace shape) — this used to emit `agent`
            # with no `step` or timing at all, so every deployed-
            # orchestrator invoke rendered blank step names, "(ms)" with no
            # number, and React key warnings for the undefined `step`.
            trace.append({"step": i + 1, "agent_name": agent["name"], "status": "completed", "output": result, "duration_ms": duration_ms})
            current = result.get("output", result)
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            trace.append({"step": i + 1, "agent_name": agent["name"], "status": "failed", "error": str(e), "duration_ms": duration_ms})
    return {"output": current, "trace": trace, "status": "completed"}


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "chain_executor", "agents": len(AGENTS)}