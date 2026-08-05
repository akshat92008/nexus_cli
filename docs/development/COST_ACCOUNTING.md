# Cost Accounting & Ledger Specification

## Overview
`CostLedger` (`nexus/cost_accounting.py`) tracks token usage, calculates native USD cost and display INR cost (1 USD = 85 INR), and computes cost per verified task success.

## Features
- **Real-Time Token Usage Accounting**: Prompt, completion, cached, and reasoning tokens.
- **Multi-Currency Conversion**: Display in INR (`₹`) alongside native USD (`$`).
- **Artifact Persistence**: Automatically writes `.nexus/runs/<run-id>/cost/ledger.json` and `summary.json`.
