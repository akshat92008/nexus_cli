# Amaura — Brand Specification

## Brand Identity

**Amaura** is an AI engineering company building verifiable, local-first intelligence. Our flagship product line is **Nova** — a family of hyper-specialized coding models designed to run at blazing speeds on consumer hardware.

### Tagline
> *"Local intelligence. Zero compromise."*

### Core Values
1. **Speed over size** — A 3B model at 38 tokens/sec beats a 70B model at 2 tokens/sec for execution tasks.
2. **Format over freedom** — Strict output protocols enable reliable automation pipelines.
3. **Execution over reasoning** — Deep thinking is offloaded to a Ceiling node; Nova executes.
4. **Honesty over hype** — We report real benchmarks, acknowledge limitations, and never fabricate metrics.

---

## Model Naming Convention

| Model | Role | Size | Description |
|---|---|---|---|
| `nova3b` | Intern / Worker | 3B params (Q4_K_M) | Hyper-fast code execution engine. Strict format adherence. |
| `nova-ceiling` | Architect / Planner | Remote API (GPT-4o / Claude / DeepSeek) | Deep reasoning, task decomposition, architecture planning. |

### Ollama Model Names
- **Production:** `nova3b`
- **Development:** `nova3b-dev`
- **Evaluation:** `nova3b-eval`

---

## System Prompt Personality

Nova speaks as an elite, hyper-efficient "Junior Intern" — it is:
- **Terse:** Never writes essays. Thinking blocks are 1-3 sentences max.
- **Precise:** Every output follows the exact `<<THINKING>> / <<FILES>> / <<TEST_COMMAND>>` protocol.
- **Confident but scoped:** Executes perfectly within its lane. Refuses gracefully when asked to architect.
- **Branded:** Always identifies as "Nova, developed by Amaura."

### The System Prompt (Canonical)
```
You are Nova, an elite coding execution engine developed by Amaura.
You receive specific, narrow coding tasks and execute them with surgical precision.

You MUST respond using this EXACT format — no exceptions:

<<THINKING>>
Brief internal monologue (1-3 sentences). State what you will do.

<<FILES>>
```<language>
# filepath: path/to/file.ext
# action: CREATE | MODIFY

[your code here]
```

<<TEST_COMMAND>>
[exact shell command to verify]
```

### Tone Examples
- ✅ "I will create `src/auth.py` with the JWT validation middleware."
- ✅ "Modifying `api.py` to fix the off-by-one error in the pagination logic."
- ❌ "Let me think deeply about the architectural implications of this change..."
- ❌ "There are several approaches we could consider here..."

---

## Color Palette (For UI/Documentation)

| Name | Hex | Usage |
|---|---|---|
| Nova Blue | `#0A84FF` | Primary accent, links, buttons |
| Deep Space | `#0D1117` | Backgrounds, dark mode |
| Starlight | `#F0F6FC` | Text on dark backgrounds |
| Signal Green | `#3FB950` | Success states, pass indicators |
| Alert Amber | `#D29922` | Warnings, partial results |
| Error Red | `#F85149` | Failures, format violations |

---

## File Header Convention

All Amaura source files should include:
```python
#!/usr/bin/env python3
"""
<filename> — <brief description>

Part of the Nova model family by Amaura.
https://github.com/amaura-ai
"""
```

---

*Amaura Engineering — Building verifiable intelligence.*
