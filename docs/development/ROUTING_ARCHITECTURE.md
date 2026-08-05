# Adaptive Model Routing Architecture

## Overview
`ModelRouter` (`nexus/model_router.py`) selects the cheapest suitable model satisfying capability scorecards, portfolio mode constraints, and privacy policies.

## Portfolio Modes
- `CHEAPEST`: Minimize cost while meeting minimum capability requirements.
- `PRIVATE`: Enforce `LOCAL_ONLY` or `PRIVATE_INFRASTRUCTURE`.
- `FASTEST`: Prioritize local compute and low latency.
- `BALANCED`: Balance cost, latency, and success probability.
- `STRONGEST`: Utilize highest tier model permitted by policy.
- `MANUAL`: Use user-selected model unless policy-blocked.

## Phase-Specific Routing & Downshifting
- **Planning & Criticism**: Strong/Frontier models (`GLM 5.2`, `DeepSeek Pro`).
- **Code Repair & Editing**: Affordable/Strong models (`DeepSeek Flash`, `Llama 3.3`).
- **Documentation & Summaries**: Downshifted automatically to local Nova (`nova3b`) or cheap flash models.
