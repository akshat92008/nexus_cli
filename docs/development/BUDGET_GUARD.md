# Budget Guard & Hard Ceilings Specification

## Overview
`BudgetController` (`nexus/budget.py`) enforces hard per-run budget limits across hosted calls, provider attempts, token counts, and monetary ceilings.

## Features
- **INR Budget Directives**: Pass `--budget-inr 20` for explicit INR hard limits.
- **Pre-Call Cost Reservation**: Reserves upper-bound costs prior to invocation to prevent parallel or stream overrun.
- **Overrun Accounting Tolerance**: 1% grace margin for unexpected provider token report variances.
- **Budget Exceeded Exception**: Halts execution cleanly before issuing an unauthorized LLM request.
