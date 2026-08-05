# Target Architecture

The target architecture moves Nexus from a monolithic god-class structure into a modular, clean AI engineering runtime.

## High-Level Flow

```
        User Interface (CLI)
              |
        Agent Session (Session Controller)
              |
        Task Controller
              |
      -----------------
      |       |       |
 Planner Context Execution
          Selector Controller
              |
      -----------------
      |       |       |
 Mutation Verification Recovery
 Controller Controller Controller
              |
        Evidence System
              |
        Final Result
```

## Core Components

1. **AgentSession:** Manages a single user task lifecycle. Coordinates controllers, maintains state. Does NOT execute commands or edit files directly.
2. **TaskPlanner:** Understands user goal, creates execution plan, defines acceptance criteria. Does NOT execute commands.
3. **ContextSelector:** Chooses relevant repository information.
4. **ExecutionController:** Responsible for running commands, tools, and processes cleanly.
5. **MutationController:** Responsible for file changes, patches, checkpoints, rollbacks.
6. **VerificationController:** Responsible for evidence collection, test execution results, and verification logic.
7. **RecoveryController:** Handles failures, retry strategies, and recovery decisions.
8. **EvidenceCollector:** Centralizes logs, hashes, receipts, and artifacts.
9. **RunFinalizer:** Handles final status, proof generation, and completion.

## Provider Architecture
A model-agnostic `ModelProvider` interface will be implemented to cleanly separate provider-specific logic (OpenAI, Gemini, Local) from the core business logic.

## Configuration System
A centralized `NexusConfig` class will replace scattered env vars and hardcoded settings. It will resolve config via: CLI args > project config > user config > environment > defaults.

## Event System
An internal event architecture will be established to emit events like `TaskStarted`, `CommandExecuted`, etc., decoupling the UI and analytics from the core logic.
