# Nova v12 — Locked Vision

## Internal Project Name

**Nova v12**

## Public Product Name

**Amaura Nova Code**

Public checkpoints:

```
amauralabs/Nova-Code-Lite
amauralabs/Nova-Code-4B
amauralabs/Nova-Code-8B
```

Do not publicly lead with "v12." New users do not need Nova's internal experiment history.

## Public Promise

> **A fast, open, local-first coding model family designed for code generation,
> completion, debugging, repository editing and agentic development on consumer
> hardware.**

## Competitive Category

Nova aims to become:

> **The best openly available coding model family in its hardware class.**

Not "better than Claude at everything."

A defensible eventual claim would be:

> "Best tested local coding model under 5B parameters on specified code-generation
> and agentic benchmarks as of a stated date."

---

## Model Family

| Variant            | Purpose                                | Target Environment        | Release Priority |
| ------------------ | -------------------------------------- | ------------------------- | ---------------: |
| **Nova Code 4B**   | Main coding model                      | 8 GB laptops and desktops |            First |
| **Nova Code Lite** | Completion and simple coding           | Very constrained hardware |           Second |
| **Nova Code 8B**   | Stronger reasoning and repository work | 16 GB+ systems and GPUs   |            Third |

All three share:
- Training data
- Output protocols
- Tool-calling format
- Benchmarks
- Nexus integration
- Branding
- Model card structure

## Hero Model: Nova Code 4B

This is the most important release. It offers the best intersection of:
- Local usability
- Download size
- Inference speed
- Fine-tuning feasibility
- Coding capability
- Public interest

The Lite and 8B versions should be distilled or trained after the 4B pipeline is proven.

---

## Operating Modes

Nova Code supports explicit operating modes via control tokens:

```
<|nova_chat|>      — General conversation
<|nova_code|>      — Code generation
<|nova_fim|>       — Fill-in-the-middle completion
<|nova_edit|>      — Code editing / patches
<|nova_agent|>     — Agentic tool use
<|nova_debug|>     — Debugging mode
<|nova_review|>    — Code review
<|nova_explain|>   — Explanation mode
<|nova_refactor|>  — Refactoring mode
```

---

## Language Coverage (Launch)

| Language Group            | Training Allocation |
| ------------------------- | ------------------: |
| Python                    |                 25% |
| JavaScript and TypeScript |                 25% |
| Java and C++              |                 20% |
| Go and Rust               |                 15% |
| SQL and Bash              |                 10% |
| Other languages           |                  5% |

---

## Locked Definition

> **Nova v12 is an Amaura Labs family of open, local-first coding models. Its hero
> release, Nova Code 4B, will support code generation, explanation, debugging,
> fill-in-the-middle completion, repository editing and multi-turn tool use. It
> will be built from the strongest commercially usable small foundation selected
> through a blind bake-off, then improved through code-focused continued
> pretraining, execution-verified supervised training, teacher distillation,
> execution-ranked preference optimisation and verifiable-reward reinforcement
> learning. Nova will ship across GGUF, MLX, Transformers and GPU formats, with
> Lite and 8B variants following the 4B release. It will not be marketed as
> category-leading unless it wins a reproducible small-model coding evaluation.**

---

## What Nova Is Not

- Nova is not a pretrained-from-scratch model
- Nova does not claim to beat frontier models
- Nova does not require Amaura-specific software to function
- Nova does not hide weak raw performance behind a pipeline
- Nova does not publish unverified benchmark claims

---

*Amaura Labs — Building verifiable intelligence.*
