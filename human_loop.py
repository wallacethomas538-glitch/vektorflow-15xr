from database import get_db
from typing import Dict, List, Any
import json

def create_pending_approval(email: str, task: str, drift_score: float, options: List[Dict]) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pending_approvals (email, task, drift_score, options)
        VALUES (?, ?, ?, ?)
    """, (email, task, drift_score, json.dumps(options)))
    conn.commit()
    approval_id = cursor.lastrowid
    conn.close()
    return approval_id

def get_pending_approvals(email: str) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_approvals WHERE email = ? AND status = 'pending'", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def resolve_approval(approval_id: int, decision: str, selected_option: Any = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE pending_approvals
        SET status = ?, decision = ?, resolved_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (decision, json.dumps(selected_option) if selected_option else None, approval_id))
    conn.commit()
    conn.close()
