#!/usr/bin/env bash
# E2E test: compile artifacts → merge → search
# Validates the full pipeline from skill artifacts to semantic intent search
# through the MCP server.
#
# This test bypasses the LLM extraction step (which requires API keys) and
# creates the compiled artifacts (ontoskill.ttl + intents.json) directly,
# then validates: JS merge → ONNX export → Rust MCP search.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
step()  { echo -e "${YELLOW}[E2E] $*${NC}"; }
ok()    { echo -e "${GREEN}[PASS] $*${NC}"; }
fail()  { echo -e "${RED}[FAIL] $*${NC}"; exit 1; }

# ── Step 0: Build the Rust MCP binary ────────────────────────────────
step "Building ontomcp binary..."
(cd "$REPO_ROOT/mcp" && cargo build --release --quiet 2>/dev/null)
ONTOCP="$REPO_ROOT/mcp/target/release/ontomcp"
[[ -x "$ONTOCP" ]] || fail "ontomcp binary not found"
ok "ontomcp binary built"

# ── Step 1: Create compiled skill artifacts ───────────────────────────
# Simulates what ontocore compile produces (bypasses LLM extraction).
step "Creating compiled skill artifacts..."

ONTOLOGY_ROOT="$SANDBOX/ontology-root"
SKILL_DIR="$ONTOLOGY_ROOT/author/test-author/calc-skill"
EMBEDDINGS_DIR="$ONTOLOGY_ROOT/system/embeddings"
SYSTEM_DIR="$ONTOLOGY_ROOT/system"
mkdir -p "$SKILL_DIR" "$EMBEDDINGS_DIR" "$SYSTEM_DIR"

# Create ontoskill.ttl (matches what compiler produces)
cat > "$SKILL_DIR/ontoskill.ttl" <<'TTL'
@prefix oc: <https://ontoskills.sh/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

<https://ontoskills.sh/ontology#skill_calc-skill> a oc:Skill ;
    dcterms:identifier "calc-skill" ;
    oc:nature "A skill for spreadsheet editing and calculation"@en ;
    oc:resolvesIntent "edit spreadsheet" ;
    oc:resolvesIntent "perform calculation" ;
    oc:resolvesIntent "format cell data" .
TTL

# Create per-skill intents.json with real embeddings from sentence-transformers
python3 -c "
import sys, json
sys.path.insert(0, '$REPO_ROOT/core')
from sentence_transformers import SentenceTransformer

MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
DIM = 384

intents = ['edit spreadsheet', 'perform calculation', 'format cell data']
model = SentenceTransformer(MODEL_NAME)
embeddings = model.encode(intents, convert_to_numpy=True, normalize_embeddings=True)

data = {
    'model': MODEL_NAME,
    'dimension': DIM,
    'intents': [
        {
            'intent': intent,
            'embedding': emb.tolist(),
            'skills': ['calc-skill'],
        }
        for intent, emb in zip(intents, embeddings)
    ],
}

with open('$SKILL_DIR/intents.json', 'w') as f:
    json.dump(data, f)
print(f'  Wrote {len(intents)} intents with {DIM}-dim embeddings')
" 2>/dev/null || fail "Failed to create embeddings"

[[ -f "$SKILL_DIR/intents.json" ]] || fail "intents.json not created"
ok "Per-skill intents.json created with real embeddings"

# ── Step 2: Merge with JS ────────────────────────────────────────────
step "Merging embeddings via JS..."

node -e "
const path = require('path');
const fsp = require('fs/promises');

const EMBEDDINGS_DIR = '$EMBEDDINGS_DIR';
const AUTHOR_DIR = '$ONTOLOGY_ROOT/author';

async function walkForIntentsJson(dir) {
  let results = [];
  const entries = await fsp.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results = results.concat(await walkForIntentsJson(fullPath));
    } else if (entry.name === 'intents.json') {
      results.push(fullPath);
    }
  }
  return results;
}

async function run() {
  await fsp.mkdir(EMBEDDINGS_DIR, { recursive: true });
  let intentsFiles = await walkForIntentsJson(AUTHOR_DIR);

  const intentMap = new Map();
  for (const filePath of intentsFiles) {
    const data = JSON.parse(await fsp.readFile(filePath, 'utf8'));
    for (const entry of (data.intents || [])) {
      const key = entry.intent;
      if (!intentMap.has(key)) {
        intentMap.set(key, { intent: key, embedding: entry.embedding, skills: [...entry.skills] });
      } else {
        const existing = intentMap.get(key);
        const mergedSkills = [...new Set([...existing.skills, ...entry.skills])];
        intentMap.set(key, { ...existing, skills: mergedSkills });
      }
    }
  }

  const merged = {
    model: 'sentence-transformers/all-MiniLM-L6-v2',
    dimension: 384,
    intents: Array.from(intentMap.values()).sort((a, b) => a.intent.localeCompare(b.intent))
  };

  await fsp.writeFile(
    path.join(EMBEDDINGS_DIR, 'intents.json'),
    JSON.stringify(merged, null, 2)
  );
  console.log('  Merged ' + merged.intents.length + ' intents');
}
run().catch(e => { console.error(e); process.exit(1); });
" || fail "JS merge failed"

MERGED_INTENTS="$EMBEDDINGS_DIR/intents.json"
[[ -f "$MERGED_INTENTS" ]] || fail "Merged intents.json not found"

python3 -c "
import json
data = json.load(open('$MERGED_INTENTS'))
assert data['dimension'] == 384
assert len(data['intents']) == 3, f'Expected 3 intents, got {len(data[\"intents\"])}'
skills = set()
for e in data['intents']:
    skills.update(e['skills'])
assert 'calc-skill' in skills, f'calc-skill not found in {skills}'
print(f'  {len(data[\"intents\"])} intents merged, calc-skill present')
" || fail "Merged intents validation failed"
ok "JS merge validated"

# ── Step 3: Export ONNX model + tokenizer ────────────────────────────
step "Exporting ONNX model + tokenizer..."
python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/core')
from pathlib import Path
from compiler.embeddings.exporter import MODEL_NAME
from optimum.exporters.onnx import main_export
from transformers import AutoTokenizer

output_dir = Path('$EMBEDDINGS_DIR')
output_dir.mkdir(parents=True, exist_ok=True)

print(f'  Exporting ONNX model ({MODEL_NAME})...')
main_export(MODEL_NAME, output=output_dir, task='feature-extraction')

print('  Exporting tokenizer...')
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.save_pretrained(str(output_dir))
print('  Done')
" 2>/dev/null || fail "ONNX model export failed"

[[ -f "$EMBEDDINGS_DIR/model.onnx" ]] || fail "model.onnx not found"
[[ -f "$EMBEDDINGS_DIR/tokenizer.json" ]] || fail "tokenizer.json not found"
ok "ONNX model + tokenizer exported"

# Create a minimal system index so the MCP server can load the ontology
cat > "$SYSTEM_DIR/index.enabled.ttl" <<'TTL'
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://ontoskills.sh/ontology#index> a owl:Ontology ;
    owl:imports <file://author/test-author/calc-skill/ontoskill.ttl> .
TTL

# ── Step 4: Search via MCP binary (JSON-RPC) ─────────────────────────
step "Running search query via MCP server..."

SEARCH_QUERY="edit a spreadsheet"

# Write JSON-RPC messages to a temp file for stdin redirect.
# IMPORTANT: Use file redirect (< file), not pipe (|), because the ONNX
# Runtime initialization can block and pipes cause deadlocks.
INPUT_FILE="$SANDBOX/mcp_input.jsonl"
python3 -c "
import json
msgs = [
    {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'e2e-test','version':'0.1'}}},
    {'jsonrpc':'2.0','method':'notifications/initialized'},
    {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'ontoskill','arguments':{'q':'$SEARCH_QUERY','top_k':3}}},
]
with open('$INPUT_FILE', 'w') as f:
    for m in msgs:
        f.write(json.dumps(m) + '\n')
"

# Locate ONNX Runtime shared library (required by ort load-dynamic)
ORT_LIB="$(python3 -c 'import onnxruntime; import os; print(os.path.join(os.path.dirname(onnxruntime.__file__), "capi", "libonnxruntime.so"))')"
if [[ ! -f "$ORT_LIB" ]]; then
    # Try with version suffix
    ORT_LIB="$(ls "$(dirname "$ORT_LIB")"/libonnxruntime.so.* 2>/dev/null | head -1)"
    [[ -f "$ORT_LIB" ]] || fail "ONNX Runtime shared library not found (install onnxruntime: pip install onnxruntime)"
fi

# Run MCP server with file-based stdin redirect and ONNX Runtime path
export ORT_DYLIB_PATH="$ORT_LIB"
RESPONSE=$(timeout 120 "$ONTOCP" --ontology-root "$ONTOLOGY_ROOT" < "$INPUT_FILE" 2>"$SANDBOX/mcp_stderr.log") || true

if [[ -z "$RESPONSE" ]]; then
    echo "  MCP stderr output:" >&2
    cat "$SANDBOX/mcp_stderr.log" >&2
    fail "MCP server returned empty response"
fi

# Parse the search response (id:2)
echo "$RESPONSE" > "$SANDBOX/mcp_response.jsonl"

SEARCH_RESULT=$(python3 -c "
import json

with open('$SANDBOX/mcp_response.jsonl') as f:
    lines = f.read().strip().split('\n')

for line in lines:
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    if msg.get('id') == 2:
        result = msg.get('result', {})
        content = result.get('content', [])
        for c in content:
            if c.get('type') == 'text':
                data = json.loads(c['text'])
                matches = data.get('matches', [])
                if not matches:
                    print('NO_MATCHES')
                    exit(0)
                top = matches[0]
                print(f'TOP_MATCH: intent={top[\"intent\"]} score={top[\"score\"]:.4f} skills={top[\"skills\"]}')
                for m in matches:
                    print(f'  {m[\"intent\"]:30s} score={m[\"score\"]:.4f} skills={m[\"skills\"]}')
                exit(0)
        error = msg.get('error')
        if error:
            print(f'ERROR: {error}')
            exit(1)
        print('NO_CONTENT')
        exit(0)
print('RESPONSE_NOT_FOUND')
")

step "Search results for '$SEARCH_QUERY':"
echo "$SEARCH_RESULT"

# Verify the search found the correct skill
if echo "$SEARCH_RESULT" | grep -q "calc-skill"; then
    ok "Search returned 'calc-skill' — E2E pipeline validated!"
else
    if echo "$SEARCH_RESULT" | grep -q "ERROR\|NO_MATCHES\|NO_CONTENT\|RESPONSE_NOT_FOUND"; then
        fail "Search did not return expected results: $SEARCH_RESULT"
    else
        fail "Search returned wrong skill (expected 'calc-skill'): $SEARCH_RESULT"
    fi
fi
