import hashlib
import uuid

import argon2

ph = argon2.PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        ph.verify(stored_hash, password)
        return True
    except argon2.exceptions.VerifyMismatchError:
        return False
    except:
        raise


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def create_uuid() -> str:
    return str(uuid.uuid4())
