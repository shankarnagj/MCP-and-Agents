#!/usr/bin/env python3
"""Print freshly generated secrets for TESSERA_SECRET_KEY / TESSERA_ENCRYPTION_KEY / DB password."""
import secrets

from cryptography.fernet import Fernet

print(f"TESSERA_SECRET_KEY={secrets.token_urlsafe(48)}")
print(f"TESSERA_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
print(f"TESSERA_DB_PASSWORD={secrets.token_urlsafe(24)}")
