import logging
from typing import Optional
from amaura.crm.database import CRMDatabase, Lead

logger = logging.getLogger(__name__)

class Pipeline:
    """
    Manages the lifecycle of a lead in the Amaura AI System.
    Valid states: new -> researched -> drafted -> contacted -> responded -> qualified -> closed -> rejected
    """
    def __init__(self, db: CRMDatabase):
        self.db = db

    def process_new_lead(self, lead_id: str, score: float, profile: dict) -> bool:
        """Transitions a 'new' lead to 'researched' after profiling."""
        lead = self.db.get_lead(lead_id)
        if not lead or lead.status != "new":
            return False
        
        lead.score = score
        lead.profile = profile
        lead.status = "researched"
        self.db.update_lead(lead)
        logger.info(f"Lead {lead_id} advanced to 'researched'.")
        return True

    def outreach_drafted(self, lead_id: str, draft_content: str) -> bool:
        """Transitions a 'researched' lead to 'drafted'."""
        lead = self.db.get_lead(lead_id)
        if not lead or lead.status != "researched":
            return False
            
        profile = lead.profile
        profile["outreach_draft"] = draft_content
        lead.profile = profile
        lead.status = "drafted"
        self.db.update_lead(lead)
        logger.info(f"Lead {lead_id} advanced to 'drafted'.")
        return True
        
    def mark_contacted(self, lead_id: str) -> bool:
        """Transitions a 'drafted' lead to 'contacted'."""
        lead = self.db.get_lead(lead_id)
        if not lead or lead.status != "drafted":
            return False
            
        lead.status = "contacted"
        self.db.update_lead(lead)
        logger.info(f"Lead {lead_id} advanced to 'contacted'.")
        return True

    def mark_responded(self, lead_id: str, response_text: str) -> bool:
        """Transitions a 'contacted' lead to 'responded'."""
        lead = self.db.get_lead(lead_id)
        if not lead or lead.status != "contacted":
            return False
            
        profile = lead.profile
        profile["last_response"] = response_text
        lead.profile = profile
        lead.status = "responded"
        self.db.update_lead(lead)
        logger.info(f"Lead {lead_id} advanced to 'responded'. Waiting for human qualification.")
        return True

    def qualify_lead(self, lead_id: str, requirements: dict) -> bool:
        """Transitions a 'responded' lead to 'qualified'. (Human action)"""
        lead = self.db.get_lead(lead_id)
        if not lead or lead.status != "responded":
            return False
            
        profile = lead.profile
        profile["requirements"] = requirements
        lead.profile = profile
        lead.status = "qualified"
        self.db.update_lead(lead)
        logger.info(f"Lead {lead_id} advanced to 'qualified'. Ready for proposal/closing.")
        return True
        
    def close_deal(self, lead_id: str) -> bool:
        """Transitions a 'qualified' lead to 'closed'. Triggers handoff to Antigravity."""
        lead = self.db.get_lead(lead_id)
        if not lead or lead.status != "qualified":
            return False
            
        lead.status = "closed"
        self.db.update_lead(lead)
        logger.info(f"Deal closed for Lead {lead_id}. Handing off to Antigravity.")
        return True

    def reject_lead(self, lead_id: str, reason: str) -> bool:
        """Marks a lead as rejected at any stage."""
        lead = self.db.get_lead(lead_id)
        if not lead:
            return False
            
        profile = lead.profile
        profile["rejection_reason"] = reason
        lead.profile = profile
        lead.status = "rejected"
        self.db.update_lead(lead)
        logger.info(f"Lead {lead_id} rejected: {reason}")
        return True
