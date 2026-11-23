#!/usr/bin/env bash
# Pinned Phi 4-mini weights + pinned CPU llama.cpp, zero paid inference APIs.
set -euo pipefail
if [[ "$#" -lt 2 ]]; then
  echo "Usage: bash scripts/run_cairn_phi.sh --site PATH [--max-cases N] or --analyst-config FILE" >&2
  exit 2
fi
ROOT="$RUNNER_TEMP/cairn-local-phi"
mkdir -p "$ROOT"
REPO="bartowski/microsoft_Phi-4-mini-instruct-GGUF"
REV="7ff82c2aaa4dde30121698a973765f39be5288c0"
FILE="microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
EXPECTED="01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2"
LLAMA_COMMIT="325914defd2c1279a039366d999dff4c19a75b54"
WEIGHTS="$ROOT/model.gguf"
if ! [[ -s "$WEIGHTS" ]] || ! echo "$EXPECTED  $WEIGHTS" | sha256sum --check --status; then
  echo "Downloading pinned Phi weights to ephemeral runner; no analyst prompts leave runner"
  curl --fail --location --retry 3 --retry-delay 8 \
    --connect-timeout 30 --max-time 700 \
    "https://huggingface.co/$REPO/resolve/$REV/$FILE?download=true" \
    --output "$WEIGHTS.part"
  mv "$WEIGHTS.part" "$WEIGHTS"
fi
echo "$EXPECTED  $WEIGHTS" | sha256sum --check -
if [[ ! -x "$ROOT/llama/build/bin/llama-server" ]]; then
  git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$ROOT/llama"
  git -C "$ROOT/llama" checkout "$LLAMA_COMMIT"
  cmake -S "$ROOT/llama" -B "$ROOT/llama/build" \
    -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF
  cmake --build "$ROOT/llama/build" --target llama-server -j 4
fi
[[ "$(git -C "$ROOT/llama" rev-parse HEAD)" = "$LLAMA_COMMIT" ]]
echo "Starting loopback-only Phi; GGUF SHA256 verified; llama.cpp SHA pinned"
"$ROOT/llama/build/bin/llama-server" \
  -m "$WEIGHTS" --host 127.0.0.1 --port 8080 \
  --ctx-size 4096 --threads 4 --parallel 1 --no-webui \
  > "$ROOT/llama-server.log" 2>&1 &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; }
trap cleanup EXIT
ready=0
for _ in $(seq 1 150); do
  if curl --silent --fail http://127.0.0.1:8080/health >/dev/null; then
    ready=1; break
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    tail -40 "$ROOT/llama-server.log"
    exit 1
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "::warning::Phi service not ready; normal publishing can continue"
  tail -40 "$ROOT/llama-server.log"
  exit 1
fi
PYTHONPATH=. python -m scripts.cairn_phi_local "$@"
# Avoid exporting model server logs containing untrusted source text.
if [[ -r "/proc/$pid/status" ]]; then
  grep -E 'VmHWM|VmRSS' "/proc/$pid/status" || true
fi
