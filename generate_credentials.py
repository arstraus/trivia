import hashlib
import secrets

def generate_credentials(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode(), 
        salt.encode(), 
        100000
    ).hex()
    return password_hash, salt

password = ""
password_hash, salt = generate_credentials(password)
print(f"""
[auth.credentials.admin]
password_hash = "{password_hash}"
salt = "{salt}"
""")
