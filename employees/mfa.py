import base64
import hashlib
import hmac
import secrets
import struct
import time


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def totp_code(secret, at_time=None):
    at_time = int(at_time or time.time())
    counter = at_time // 30
    padded = secret + ('=' * (-len(secret) % 8))
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0f
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff
    return f'{value % 1000000:06d}'


def verify_code(secret, code):
    code = ''.join((code or '').split())
    if len(code) != 6 or not code.isdigit():
        return False
    now = time.time()
    return any(
        hmac.compare_digest(totp_code(secret, now + offset), code)
        for offset in (-30, 0, 30)
    )


def provisioning_uri(secret, username, issuer='CoreCloud'):
    from urllib.parse import quote
    return f'otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}'
