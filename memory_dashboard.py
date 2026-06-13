from fastapi import APIRouter, Depends
from database import get_db
from main import get_current_user

router = APIRouter(prefix="/memory", tags=["memory"])

@router.get("/agent/{agent_id}")
def get_agent_memory(agent_id: str, email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT memory_type, content, timestamp FROM agent_memory
        WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 50
    """, (agent_id,))
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "agent_id": agent_id,
        "memories": [dict(row) for row in rows],
        "count": len(rows)
    }

@router.get("/dashboard")
def get_memory_dashboard(email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT agent_id, memory_type, COUNT(*) as count
        FROM agent_memory
        WHERE agent_id LIKE ?
        GROUP BY agent_id, memory_type
    """, (f"{email}%",))
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "email": email,
        "memory_stats": [dict(row) for row in rows]
    }
