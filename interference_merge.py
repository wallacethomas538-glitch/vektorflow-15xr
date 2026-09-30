from typing import List, Dict, Any
from collections import Counter

class InterferenceMerge:
    @staticmethod
    def merge(responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not responses:
            return {"error": "No responses"}
        
        stringified = [str(r) for r in responses]
        counter = Counter(stringified)
        most_common, count = counter.most_common(1)[0]
        
        if count >= len(responses) * 0.6:
            return {"status": "commit", "value": eval(most_common), "confidence": count / len(responses)}
        else:
            return {"status": "ask_user", "options": responses, "confidence": count / len(responses)}
