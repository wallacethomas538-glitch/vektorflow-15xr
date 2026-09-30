class KillSwitch:
    def __init__(self):
        self._killed = set()
    
    def kill(self, agent_id: str):
        self._killed.add(agent_id)
    
    def revive(self, agent_id: str):
        self._killed.discard(agent_id)
    
    def is_killed(self, agent_id: str) -> bool:
        return agent_id in self._killed
