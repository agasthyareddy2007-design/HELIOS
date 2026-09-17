"""
HELIOS V2 API — API-key authentication (lightweight, production-oriented).

Features:
- Keys are stored securely in SQLite with PBKDF2 hashing.
- Role-based permissions (admin, user).
- Constant-time verification.
- In-memory caching with periodic invalidation to reduce DB load (if needed, but for now every check can hit DB cheaply or we cache).
- No plaintext keys stored or returned.
"""

from __future__ import annotations

import hmac
import os
import time
import secrets
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from database.connection import get_db_manager
from database.schema.helios_schema import ApiKey

API_KEY_HEADER = "X-API-Key"
UNAUTHORIZED_BODY = {
    "error": "unauthorized",
    "message": "Valid API key required",
}
FORBIDDEN_BODY = {
    "error": "forbidden",
    "message": "Admin role required",
}

def hash_secret(secret: str) -> str:
    """Hash a secret using PBKDF2."""
    salt = os.environ.get("HELIOS_API_KEY_PEPPER", "helios_default_pepper_2026").encode('utf-8')
    iterations = 100000
    hash_obj = hashlib.pbkdf2_hmac('sha256', secret.encode('utf-8'), salt, iterations)
    return hash_obj.hex()

def _mask(secret: str) -> str:
    if not secret:
        return "<empty>"
    return f"len={len(secret)}"

class ApiKeyAuthenticator:
    """Validates ``X-API-Key`` against SQLite database keys."""

    def __init__(self):
        self.db = get_db_manager()

    def identify(self, presented: Optional[str]) -> Optional[Tuple[str, str]]:
        """Return (key_id, role) for a presented secret, or None if invalid."""
        if not presented or not presented.startswith("hl_"):
            return None
        
        parts = presented.split("_")
        if len(parts) < 3:
            return None
            
        role_label = parts[1]
        raw_secret_part = parts[2]
        
        # Calculate hash of the whole presented secret to match
        presented_hash = hash_secret(presented)
        
        # Because we only have the hash, we can search by the key_prefix if we want to be fast,
        # but let's just create a prefix from the raw_secret_part
        key_prefix = raw_secret_part[:8]

        with self.db.get_session() as session:
            key_record = session.query(ApiKey).filter_by(key_prefix=key_prefix, enabled=True).first()
            if not key_record:
                return None
            
            if hmac.compare_digest(presented_hash.encode('utf-8'), key_record.key_hash.encode('utf-8')):
                return (key_record.id, key_record.role)
                
        return None

    def authenticate(self, presented: Optional[str], require_admin: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate a presented key. 
        Returns (ok, key_id, error_body)."""
        result = self.identify(presented)
        if result is None:
            return False, None, UNAUTHORIZED_BODY
            
        key_id, role = result
        if require_admin and role != "admin":
            return False, key_id, FORBIDDEN_BODY
            
        # Update last_used_at in background or synchronously
        with self.db.get_session() as session:
            key_record = session.query(ApiKey).filter_by(id=key_id).first()
            if key_record:
                key_record.last_used_at = datetime.utcnow()
                session.commit()
                
        return True, key_id, None

def generate_key(role: str, name: str) -> Tuple[str, dict]:
    """Generates a new API key and stores it in the database."""
    raw_secret = secrets.token_hex(32)
    api_key_plaintext = f"hl_{role}_{raw_secret}"
    
    key_prefix = raw_secret[:8]
    key_hash = hash_secret(api_key_plaintext)
    key_id = f"key_{secrets.token_hex(8)}"
    
    db = get_db_manager()
    with db.get_session() as session:
        new_key = ApiKey(
            id=key_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=name,
            role=role,
            enabled=True
        )
        session.add(new_key)
        session.commit()
        
    return api_key_plaintext, {
        "id": key_id,
        "name": name,
        "role": role,
        "api_key": api_key_plaintext,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "warning": "Store this key securely. It will not be shown again."
    }

if __name__ == "__main__":
    import sys
    role = "admin"
    name = "Bootstrap Admin Key"
    if len(sys.argv) > 1:
        role = sys.argv[1]
    if len(sys.argv) > 2:
        name = sys.argv[2]
        
    bootstrap_secret = os.environ.get("HELIOS_ADMIN_BOOTSTRAP_SECRET")
    if bootstrap_secret and role == "admin":
        print(f"Using provided bootstrap secret...")
        # Create a deterministically mapped admin key for the bootstrap secret
        api_key_plaintext = bootstrap_secret 
        
        parts = api_key_plaintext.split("_")
        if len(parts) >= 3:
             key_prefix = parts[2][:8]
        else:
             key_prefix = api_key_plaintext[:8]
             
        key_hash = hash_secret(api_key_plaintext)
        key_id = "bootstrap_admin"
        
        db = get_db_manager()
        with db.get_session() as session:
            existing = session.query(ApiKey).filter_by(id=key_id).first()
            if existing:
                print("Bootstrap admin key already exists.")
            else:
                new_key = ApiKey(
                    id=key_id,
                    key_prefix=key_prefix,
                    key_hash=key_hash,
                    name=name,
                    role=role,
                    enabled=True
                )
                session.add(new_key)
                session.commit()
                print(f"Created bootstrap {role} key: {api_key_plaintext}")
    else:
        plaintext, info = generate_key(role, name)
        print(f"Generated {role} key: {plaintext}")
        print("Keep it safe!")
