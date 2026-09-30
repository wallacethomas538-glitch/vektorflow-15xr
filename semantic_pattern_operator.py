from typing import List, Dict, Any
from collections import deque

class SemanticPatternOperator:
    def __init__(self, window_size: int = 10):
        self.window = deque(maxlen=window_size)
    
    def add_event(self, event: Dict[str, Any]):
        self.window.append(event)
    
    def detect_pattern(self, pattern: List[str]) -> bool:
        window_keys = [e.get("type") for e in self.window if "type" in e]
        for i in range(len(window_keys) - len(pattern) + 1):
            if window_keys[i:i+len(pattern)] == pattern:
                return True
        return False
