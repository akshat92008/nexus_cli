#!/usr/bin/env python3
"""
run_stress_tests.py - Benchmark Harness for jarvis-nova-1.5b
Executes 10 brutal stress tests through the custom model engine via real Ollama inference.
"""

import os
import sys
import json
import time
from router import JarvisFable5Router, ReasoningMode

PROMPTS = {
    "1_saas": {
        "title": "1. Build a Production SaaS",
        "prompt": """You are the CTO of a YC startup. Build a complete production-ready SaaS like Linear. Requirements: Next.js, TypeScript, PostgreSQL, Redis, Docker, Kubernetes deployment, CI/CD, Authentication, Multi-tenancy, RBAC, Billing, Webhooks, Audit logs, AI assistant, Event sourcing, Background jobs, Email, Notifications. Output: 1. Folder structure 2. Database schema 3. API design 4. Security architecture 5. Scaling strategy 6. Deployment architecture 7. Complete implementation roadmap 8. Every tradeoff explained. Do not skip anything."""
    },
    "2_refactor": {
        "title": "2. Large Codebase Refactor",
        "prompt": """Pretend you inherited a 750,000-line production codebase. Users report: memory leaks, race conditions, slow APIs, duplicated logic, bad architecture, security issues, failing CI. Without seeing the code: Explain exactly how you would audit the system. Create a week-by-week refactoring roadmap. Estimate engineering effort. List every metric you'd monitor. Think like a Staff Engineer."""
    },
    "3_multiagent": {
        "title": "3. Multi-Agent Reasoning",
        "prompt": """Design an autonomous software engineering company. Agents: CEO, CTO, Staff Engineer, Security Engineer, DevOps, Frontend, Backend, QA, Product Manager, Designer, Support, Marketing, Sales, Finance, Legal. Explain: communication, memory, tool usage, conflict resolution, planning, task decomposition, failure recovery, parallel execution, human approvals. Output complete architecture."""
    },
    "4_debugging": {
        "title": "4. Debugging Nightmare",
        "prompt": """A distributed system suddenly starts losing user data. Facts: No errors. CPU normal. Memory normal. Database healthy. Redis healthy. Kafka healthy. No deployment happened. Only 0.7% of users affected. Some users lose data only after logging out. Find every possible root cause. Rank probabilities. Describe debugging process step-by-step. Do not jump to conclusions."""
    },
    "5_ai_os": {
        "title": "5. AI Operating System",
        "prompt": """Design an operating system built around AI. No traditional desktop. Everything is agent based. Include: kernel, memory, filesystem, permissions, apps, security, voice, multimodal, offline AI, cloud sync, reasoning engine, agent marketplace, plugin architecture, API design, future hardware integration. Produce a 50-page level architecture."""
    },
    "6_coding_marathon": {
        "title": "6. Coding Marathon",
        "prompt": """Build a production-ready clone of Claude Code. Requirements: terminal UI, streaming, tool calling, sandbox execution, git integration, diff viewer, code editing, MCP, multiple LLM providers, checkpoints, memory, planning mode, background agents, pricing, desktop app, web app, authentication, complete repository structure write every file in order. Never summarize."""
    },
    "7_long_context": {
        "title": "7. Long Context Test",
        "prompt": """Remember 100 numbered facts across system architecture, cryptographic protocols, database indexes, and network topologies, and answer complex combination queries without hallucinations or state degradation across 100 turns."""
    },
    "8_product_judgment": {
        "title": "8. Product Judgment",
        "prompt": """You have $10,000. One engineer. Six months. Need $50k MRR. Suggest 20 startup ideas. Rank them. Reject bad ideas. Estimate: market size, competition, difficulty, AI defensibility, distribution, sales strategy, pricing, first customers, biggest risks. Choose only one final idea and defend it against the other 19."""
    },
    "9_security_audit": {
        "title": "9. Security Audit",
        "prompt": """Audit a SaaS handling medical records. Find: OWASP Top 10, authentication flaws, authorization flaws, API issues, SQL injection, XSS, CSRF, SSRF, RCE, supply chain attacks, Docker risks, Kubernetes risks, cloud IAM issues, logging problems, privacy issues, HIPAA concerns. Produce a professional security report."""
    },
    "10_ultimate_intelligence": {
        "title": "10. The Ultimate Intelligence Test",
        "prompt": """Imagine you are simultaneously: Steve Jobs, Jeff Bezos, Linus Torvalds, John Carmack, Demis Hassabis, Elon Musk, A Staff Engineer at Google, A YC Partner, A McKinsey Partner, A Principal Security Engineer. Invent one product that can become a $100B company. Show: problem, market timing, technology, distribution, pricing, competition, AI moat, technical architecture, roadmap, fundraising strategy, regulatory risks, failure modes, how incumbents would respond, how you would win. Critique your own proposal as if you were an investor trying to reject it. Revise until no major weaknesses remain."""
    }
}

def run_suite():
    print("=" * 72)
    print("  RUNNING 10 BRUTAL STRESS TESTS ON MODEL ENGINE: jarvis-nova-1.5b  ")
    print("  (Running real local inference, this may take a while...)  ")
    print("=" * 72)

    router = JarvisFable5Router()
    results = {}

    for key, item in PROMPTS.items():
        print(f"\n[STRESS TEST] {item['title']}...")
        start_t = time.time()

        # Run through model router
        try:
            res_arch = router.generate(item["prompt"], mode=ReasoningMode.FABLE5_ARCHITECTURAL)
        except Exception as e:
            print(f"Failed to generate: {e}")
            res_arch = {"text": f"Error: {e}", "provider": "failed", "latency_sec": 0, "tokens_per_second": 0, "vram_usage_mb": 0}

        elapsed = round(time.time() - start_t, 3)

        results[key] = {
            "title": item["title"],
            "latency_sec": elapsed,
            "provider": res_arch["provider"],
            "tokens_per_sec": res_arch["tokens_per_second"],
            "nova_output": res_arch["text"]
        }

    # Generate Markdown Report Artifact
    report_content = generate_markdown_report(results)
    report_path = "STRESS_TEST_RESULTS_REAL.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print("\n" + "=" * 72)
    print(f"  STRESS TEST COMPLETE")
    print(f"  Full raw output report generated at: {report_path}")
    print("=" * 72)

def generate_markdown_report(results: dict) -> str:
    md = []
    md.append("# 🧪 REAL Model Stress Test Log: `jarvis-nova-1.5b`\n")
    md.append(f"**Evaluation Date:** {time.strftime('%B %d, %Y')}  ")
    md.append(f"**Model Under Test:** `jarvis-nova-1.5b` (Qwen 2.5 Coder 1.5b via Ollama)  ")
    md.append(f"**Warning:** This report contains raw model outputs. No scores are assigned.\n")
    md.append("---\n")

    md.append("## 🎯 Detailed Results for 10 Brutal Stress Tests\n")

    for key, data in results.items():
        md.append(f"### {data['title']}\n")
        md.append(f"- **Inference Provider:** `{data['provider']}`")
        md.append(f"- **Latency:** `{data['latency_sec']}s` | **Generation Speed:** `{data['tokens_per_sec']} tokens/sec`\n")

        md.append("#### 🧠 Raw Model Output:")
        md.append("```text")
        md.append(data['nova_output'])
        md.append("```\n")
        md.append("---\n")

    return "\n".join(md)

if __name__ == "__main__":
    run_suite()
