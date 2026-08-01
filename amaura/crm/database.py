import sqlite3
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

@dataclass
class Lead:
    id: str
    source: str  # e.g., 'reddit', 'x', 'linkedin'
    url: str
    content: str
    author: str
    discovered_at: str
    status: str  # 'new', 'researched', 'drafted', 'contacted', 'responded', 'qualified', 'closed', 'rejected'
    score: float = 0.0
    profile_data: str = "{}"  # JSON string
    
    @property
    def profile(self) -> Dict[str, Any]:
        return json.loads(self.profile_data) if self.profile_data else {}
        
    @profile.setter
    def profile(self, value: Dict[str, Any]):
        self.profile_data = json.dumps(value)

class CRMDatabase:
    def __init__(self, db_path: str = "amaura_crm.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    score REAL DEFAULT 0.0,
                    profile_data TEXT DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
            conn.commit()

    def add_lead(self, lead: Lead) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO leads (id, source, url, content, author, discovered_at, status, score, profile_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (lead.id, lead.source, lead.url, lead.content, lead.author, lead.discovered_at, lead.status, lead.score, lead.profile_data))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Lead already exists

    def get_lead(self, lead_id: str) -> Optional[Lead]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row:
                return Lead(**dict(row))
        return None

    def update_lead(self, lead: Lead):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE leads 
                SET status = ?, score = ?, profile_data = ?
                WHERE id = ?
            """, (lead.status, lead.score, lead.profile_data, lead.id))
            conn.commit()

    def get_leads_by_status(self, status: str) -> List[Lead]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM leads WHERE status = ? ORDER BY score DESC", (status,)).fetchall()
            return [Lead(**dict(row)) for row in rows]
