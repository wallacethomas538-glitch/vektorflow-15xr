from memory_fabric import MemoryFabric
from typing import Any

class CognitionFabric:
    def __init__(self):
        self.memory = MemoryFabric()
    
    def share(self, key: str, value: Any, source: str):
        self.memory.update_shared_context(key, value, source)
    
    def recall(self, key: str):
        return self.memory.get_shared_context(key)
    
    def close(self):
        self.memory.close()
