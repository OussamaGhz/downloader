#!/usr/bin/env python3
"""Generate a valid Fernet encryption key."""

from cryptography.fernet import Fernet

key = Fernet.generate_key()
print("\n" + "=" * 60)
print("GENERATED FERNET ENCRYPTION KEY")
print("=" * 60)
print("\nAdd this to your .env file:")
print(f"\nENCRYPTION_KEY={key.decode()}")
print("\n" + "=" * 60 + "\n")
