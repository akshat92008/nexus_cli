import logging
from amaura.crm.database import Lead
# Assuming nexus provides a basic provider interface we can use later.
# from nexus.models import resolve_model
# from nexus.providers.hosted import HostedProvider

logger = logging.getLogger(__name__)

class LeadScorer:
    """
    Evaluates raw leads to remove low-quality ones and assign a confidence score.
    """
    def __init__(self, model_name: str = "glm-5.2"):
        self.model_name = model_name

    def score_lead(self, lead: Lead) -> float:
        """
        Evaluates the lead's content and context to determine a buying signal score (0.0 to 1.0).
        """
        logger.info(f"Scoring lead {lead.id} from {lead.source}")
        
        # Simulated LLM scoring logic
        content = lead.content.lower()
        score = 0.5 # base score
        
        # Positive signals
        if "budget" in content or "$" in content:
            score += 0.2
        if "need a developer" in content or "looking for" in content:
            score += 0.2
        if "mvp" in content or "saas" in content:
            score += 0.1
            
        # Negative signals
        if "for free" in content or "equity only" in content:
            score -= 0.4
        if "student project" in content:
            score -= 0.5
            
        final_score = max(0.0, min(1.0, score))
        logger.info(f"Lead {lead.id} scored: {final_score}")
        return final_score

    def filter_leads(self, leads: list[Lead], threshold: float = 0.6) -> list[Lead]:
        """
        Returns only leads that score above the threshold.
        """
        qualified = []
        for lead in leads:
            lead.score = self.score_lead(lead)
            if lead.score >= threshold:
                qualified.append(lead)
            else:
                logger.info(f"Lead {lead.id} rejected (score {lead.score} < {threshold})")
                
        return qualified
