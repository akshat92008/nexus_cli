#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# deploy.sh — One-Command Deployment for Nova 3B (Amaura)
#
# Deploys the fine-tuned Nova 3B model to Ollama on your local machine.
# Runs a smoke test to validate format compliance.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                    # Deploy from default GGUF path
#   ./deploy.sh /path/to/model.gguf  # Deploy from custom path
#
# Part of the Nova model family by Amaura.
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

MODEL_NAME="nova3b"
MODELFILE="Modelfile.amaura"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  🚀 AMAURA — Nova 3B Deployment${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Step 1: Check Ollama ────────────────────────────────────────────────────

echo -e "${BLUE}[Step 1/4]${NC} Checking Ollama installation..."

if ! command -v ollama &> /dev/null; then
    echo -e "${RED}  ❌ Ollama is not installed.${NC}"
    echo -e "  Install it from: ${CYAN}https://ollama.ai${NC}"
    echo -e "  Or run: ${YELLOW}curl -fsSL https://ollama.ai/install.sh | sh${NC}"
    exit 1
fi

echo -e "  ✅ Ollama found: $(ollama --version 2>/dev/null || echo 'installed')"

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${YELLOW}  ⚠️  Ollama is not running. Starting it...${NC}"
    ollama serve &> /dev/null &
    sleep 3
    
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${RED}  ❌ Failed to start Ollama. Start it manually with: ollama serve${NC}"
        exit 1
    fi
fi

echo -e "  ✅ Ollama is running"

# ── Step 2: Check GGUF file ─────────────────────────────────────────────────

echo ""
echo -e "${BLUE}[Step 2/4]${NC} Locating GGUF model file..."

GGUF_PATH="${1:-}"

if [ -z "$GGUF_PATH" ]; then
    # Search for GGUF in common locations
    SEARCH_PATHS=(
        "$SCRIPT_DIR/nova3b-output"
        "$SCRIPT_DIR/models"
        "$SCRIPT_DIR"
    )
    
    for dir in "${SEARCH_PATHS[@]}"; do
        if [ -d "$dir" ]; then
            FOUND=$(find "$dir" -name "*.gguf" -maxdepth 2 2>/dev/null | head -1)
            if [ -n "$FOUND" ]; then
                GGUF_PATH="$FOUND"
                break
            fi
        fi
    done
fi

if [ -z "$GGUF_PATH" ] || [ ! -f "$GGUF_PATH" ]; then
    echo -e "${YELLOW}  ⚠️  No GGUF file found. Falling back to base model...${NC}"
    echo -e "  Will use ${CYAN}qwen2.5-coder:3b${NC} as the base."
    
    # Update Modelfile to use base model instead of GGUF
    MODELFILE_CONTENT="FROM qwen2.5-coder:3b

SYSTEM \"\"\"You are Nova, an elite coding execution engine developed by Amaura.
You receive specific, narrow coding tasks and execute them with surgical precision.

You MUST respond using this EXACT format — no exceptions:

<<THINKING>>
Brief internal monologue (1-3 sentences). State what you will do.

<<FILES>>
\`\`\`<language>
# filepath: path/to/file.ext
# action: CREATE | MODIFY

[your code here]
\`\`\`

<<TEST_COMMAND>>
[exact shell command to verify]\"\"\"

TEMPLATE \"\"\"{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
\"\"\"

PARAMETER stop \"<|im_end|>\"
PARAMETER stop \"<|im_start|>\"
PARAMETER temperature 0.2
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 4096
PARAMETER num_predict 2048"
    
    # Write temp modelfile
    TEMP_MODELFILE=$(mktemp)
    echo "$MODELFILE_CONTENT" > "$TEMP_MODELFILE"
    MODELFILE="$TEMP_MODELFILE"
    
    # Pull base model first
    echo -e "  Pulling base model..."
    ollama pull qwen2.5-coder:3b
else
    GGUF_SIZE=$(du -sh "$GGUF_PATH" | cut -f1)
    echo -e "  ✅ Found: ${CYAN}$GGUF_PATH${NC} ($GGUF_SIZE)"
    
    # Update Modelfile with correct GGUF path
    TEMP_MODELFILE=$(mktemp)
    sed "s|FROM .*|FROM \"$GGUF_PATH\"|" "$SCRIPT_DIR/$MODELFILE" > "$TEMP_MODELFILE"
    MODELFILE="$TEMP_MODELFILE"
fi

# ── Step 3: Create Ollama model ──────────────────────────────────────────────

echo ""
echo -e "${BLUE}[Step 3/4]${NC} Creating Ollama model '${MODEL_NAME}'..."

ollama create "$MODEL_NAME" -f "$MODELFILE"

echo -e "  ✅ Model '${MODEL_NAME}' created successfully"

# ── Step 4: Smoke Test ───────────────────────────────────────────────────────

echo ""
echo -e "${BLUE}[Step 4/4]${NC} Running smoke test..."

TEST_PROMPT="Write a Python function called 'is_palindrome' that checks if a string is a palindrome. Handle empty strings and ignore case."

echo -e "  Prompt: ${YELLOW}${TEST_PROMPT:0:60}...${NC}"
echo ""

RESPONSE=$(ollama run "$MODEL_NAME" "$TEST_PROMPT" 2>/dev/null)

echo -e "${CYAN}─── Model Response ───${NC}"
echo "$RESPONSE"
echo -e "${CYAN}──────────────────────${NC}"

# Validate format
PASS=0
TOTAL=3

if echo "$RESPONSE" | grep -q "<<THINKING>>"; then
    echo -e "  ✅ <<THINKING>> block present"
    PASS=$((PASS + 1))
else
    echo -e "  ❌ <<THINKING>> block missing"
fi

if echo "$RESPONSE" | grep -q "<<FILES>>"; then
    echo -e "  ✅ <<FILES>> block present"
    PASS=$((PASS + 1))
else
    echo -e "  ❌ <<FILES>> block missing"
fi

if echo "$RESPONSE" | grep -q "<<TEST_COMMAND>>"; then
    echo -e "  ✅ <<TEST_COMMAND>> block present"
    PASS=$((PASS + 1))
else
    echo -e "  ❌ <<TEST_COMMAND>> block missing"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
if [ $PASS -eq $TOTAL ]; then
    echo -e "${GREEN}${BOLD}  ✅ DEPLOYMENT SUCCESSFUL — Nova 3B is ready!${NC}"
    echo -e "  Format compliance: ${GREEN}${PASS}/${TOTAL}${NC}"
else
    echo -e "${YELLOW}${BOLD}  ⚠️  DEPLOYMENT COMPLETE — Format needs fine-tuning${NC}"
    echo -e "  Format compliance: ${YELLOW}${PASS}/${TOTAL}${NC}"
    echo -e "  Tip: Fine-tune with train_nova3b_colab.py for better format lock"
fi
echo ""
echo -e "  Model: ${CYAN}${MODEL_NAME}${NC}"
echo -e "  Run:   ${YELLOW}ollama run ${MODEL_NAME}${NC}"
echo -e "  API:   ${YELLOW}curl http://localhost:11434/api/generate -d '{\"model\":\"${MODEL_NAME}\",\"prompt\":\"...\"}'${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Cleanup temp file
if [ -n "$TEMP_MODELFILE" ] && [ -f "$TEMP_MODELFILE" ]; then
    rm "$TEMP_MODELFILE"
fi
