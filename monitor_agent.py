from memory_fabric import MemoryFabric
from typing import Dict

class MonitorAgent:
    def __init__(self):
        self.memory = MemoryFabric()
    
    def validate_plan(self, plan: Dict, execution: Dict) -> Dict:
        drift_score = self._calculate_drift(plan, execution)
        if drift_score > 0.3:
            return {"status": "drift_detected", "score": drift_score, "action": "halt"}
        return {"status": "valid", "score": drift_score, "action": "continue"}
    
    def _calculate_drift(self, plan: Dict, execution: Dict) -> float:
        plan_keys = set(plan.keys())
        exec_keys = set(execution.keys())
        diff = len(plan_keys.symmetric_difference(exec_keys))
        return diff / max(len(plan_keys), 1)
    
    def close(self):
        self.memory.close()
