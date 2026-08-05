from typing import Any, Dict, Optional
import uuid
import logging

from nexus.events import EventBus, EventType
from nexus.run_state import RunStatus
from nexus.config.core import get_config

logger = logging.getLogger(__name__)

class AgentSession:
    """
    Coordinates the lifecycle of a single user task.
    Delegates domain-specific responsibilities to Controllers.
    """
    def __init__(
        self,
        task: str,
        planner: Any = None,
        context_selector: Any = None,
        execution_controller: Any = None,
        mutation_controller: Any = None,
        verification_controller: Any = None,
        recovery_controller: Any = None,
        evidence_collector: Any = None,
        finalizer: Any = None
    ):
        self.session_id = str(uuid.uuid4())
        self.task = task
        self.status = RunStatus.RUNNING
        self.config = get_config()
        
        # Injected Controllers
        self.planner = planner
        self.context_selector = context_selector
        self.execution_controller = execution_controller
        self.mutation_controller = mutation_controller
        self.verification_controller = verification_controller
        self.recovery_controller = recovery_controller
        self.evidence_collector = evidence_collector
        self.finalizer = finalizer

    def start(self) -> Dict[str, Any]:
        """Begin the session workflow."""
        self.status = RunStatus.RUNNING
        EventBus.publish(EventType.TASK_STARTED, self.session_id, "AgentSession", {"task": self.task})
        
        try:
            # 1. Context Gathering
            if self.context_selector:
                context = self.context_selector.gather_context(self.task)
            else:
                context = {}
            
            # 2. Planning
            if self.planner:
                plan = self.planner.create_plan(self.task, context)
            else:
                plan = {"steps": []}
                
            EventBus.publish(EventType.PLAN_CREATED, self.session_id, "AgentSession", {"plan": plan})
            
            # 3. Execution (delegated to execution controller loop)
            # In a fully migrated state, the ExecutionController drives the loop based on the plan.
            result = {"status": "success", "message": "Stub execution"}
            
            # 4. Finalization
            self.status = RunStatus.VERIFIED
            EventBus.publish(EventType.TASK_COMPLETED, self.session_id, "AgentSession", {"result": result})
            if self.finalizer:
                return self.finalizer.finalize(self.session_id, result)
            return result
            
        except Exception as e:
            self.status = RunStatus.FAILED
            logger.exception("Session failed")
            EventBus.publish(EventType.TASK_FAILED, self.session_id, "AgentSession", {"error": str(e)})
            if self.recovery_controller:
                return self.recovery_controller.attempt_recovery(self.session_id, e)
            return {"status": "error", "error": str(e)}

