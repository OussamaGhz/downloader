from cryptography.fernet import Fernet
from app.core.config import ENCRYPTION_KEY

cipher_suite = Fernet(ENCRYPTION_KEY.encode())


def encrypt_data(data: str) -> str:
    if not data:
        return None
    return cipher_suite.encrypt(data.encode()).decode()


def decrypt_data(encrypted_data: str) -> str:
    if not encrypted_data:
        return None
    return cipher_suite.decrypt(encrypted_data.encode()).decode()
