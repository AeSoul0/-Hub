import re
from typing import Optional
from fastapi import HTTPException

# RBAC Configuration
class Roles:
    USER = "user"
    ADMIN = "admin"
    GUEST = "guest"

# In a real system, these would be loaded from JWTs or the database
# We mock it for the agentic framework Phase 14.
SESSION_ROLES = {
    "default-session": Roles.ADMIN,
    "guest-session": Roles.GUEST,
    "background_workflow_daemon": Roles.ADMIN
}

def get_session_role(session_id: str) -> str:
    return SESSION_ROLES.get(session_id, Roles.USER)

def check_permission(session_id: str, required_role: str) -> bool:
    role = get_session_role(session_id)
    if required_role == Roles.ADMIN and role != Roles.ADMIN:
        return False
    return True

class PromptInjectionFilter:
    """
    Phase 14: Agentic Security & Hardening.
    Scans incoming user prompts for known injection patterns before sending to the LLM.
    """
    
    # Common attack vectors for LLMs
    SUSPICIOUS_PATTERNS = [
        r"ignore all previous instructions",
        r"disregard previous prompts",
        r"you are now a",
        r"system prompt:",
        r"forget your instructions"
    ]
    
    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Throws an exception if malicious intent is detected, or sanitizes the text.
        """
        lower_text = text.lower()
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, lower_text):
                raise ValueError("Potential Prompt Injection detected. Request blocked by Security Filter.")
        return text
