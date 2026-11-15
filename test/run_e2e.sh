#!/usr/bin/env bash
# End-to-end test: runs the Lead Qualifier workflow inside a real n8n container
# against a mock OpenAI server (no API keys or Google/Slack accounts needed).
#
# It strips the Google Sheets / Slack nodes, points the AI call at the mock,
# activates the workflow and fires real HTTP requests at the webhook.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE=docker.n8n.io/n8nio/n8n:latest
NAME=n8n-e2e
PORT=15679
TMP=$(mktemp -d)
[ -n "${KEEP:-}" ] || trap 'docker rm -f $NAME >/dev/null 2>&1; kill $MOCK_PID 2>/dev/null; rm -rf "$TMP"' EXIT

python3 test/mock_openai.py & MOCK_PID=$!

python3 - "$TMP/lead.json" <<'PY'
import json, sys
wf = json.load(open("workflows/02-ai-lead-qualifier.json"))
drop = {"Save to CRM Sheet", "Ping Sales on Slack"}
wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in drop]
for n in wf["nodes"]:
    if n["name"] == "AI Score Lead":
        n["parameters"]["url"] = "http://host.docker.internal:18999/v1/chat/completions"
        n["parameters"]["authentication"] = "none"
        n.pop("credentials", None)
conns = {}
for src, v in wf["connections"].items():
    if src in drop:
        continue
    conns[src] = {"main": [[t for t in outs if t["node"] not in drop] for outs in v["main"]]}
wf["connections"] = conns
wf["id"] = "e2eLeadQualifier01"
wf["active"] = True
json.dump(wf, open(sys.argv[1], "w"))
PY

docker rm -f $NAME >/dev/null 2>&1 || true
docker run -d --name $NAME -p $PORT:5678 --add-host=host.docker.internal:host-gateway \
  -e N8N_DIAGNOSTICS_ENABLED=false -v "$TMP":/wf:ro,Z $IMAGE >/dev/null
sleep 12
docker exec $NAME n8n import:workflow --input=/wf/lead.json >/dev/null
docker exec $NAME n8n update:workflow --id=e2eLeadQualifier01 --active=true >/dev/null 2>&1 || true
docker restart $NAME >/dev/null
for _ in $(seq 1 30); do curl -sf localhost:$PORT/healthz >/dev/null && break; sleep 1; done
sleep 3

fail=0
check() { # name, expected substring, actual
  if [[ "$3" == *"$2"* ]]; then echo "PASS  $1"; else echo "FAIL  $1 -> $3"; fail=1; fi
}

hot=$(curl -s -X POST localhost:$PORT/webhook/lead -H 'Content-Type: application/json' \
  -d '{"name":"Jane Doe","email":"jane@acme-corp.com","company":"Acme","budget":"$5k","message":"We need an AI support bot"}')
check "hot lead accepted" '"ok":true' "$hot"

cold=$(curl -s -X POST localhost:$PORT/webhook/lead -H 'Content-Type: application/json' \
  -d '{"name":"Bob","email":"bob@gmail.com","message":"hi"}')
check "cold lead accepted" '"ok":true' "$cold"

bad=$(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:$PORT/webhook/lead -H 'Content-Type: application/json' \
  -d '{"name":"Spam","email":"not-an-email"}')
check "invalid email rejected with 400" "400" "$bad"

exit $fail
