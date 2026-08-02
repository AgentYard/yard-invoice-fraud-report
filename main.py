"""Auto-generated Chain Executor for Invoice Fraud Report."""
import asyncio
import json
import os
import time

import httpx
from fastapi import FastAPI

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

EDGES = [
    {"id": "", "source": "extract", "target": "fraud_check", "transform": "explicit_mapping"},
    {"id": "", "source": "fraud_check", "target": "report", "transform": "explicit_mapping"},
]


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