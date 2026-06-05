"""
wecom_crypto.py

WeCom (企业微信) message encryption/decryption and signature verification.

Implements:
  - SHA1 signature calculation and verification
  - AES-CBC decryption for encrypted WeCom messages and echostr

Compatible with WXBizMsgCrypt protocol used by WeCom callbacks.

Requires: cryptography (pip install cryptography)
"""

import base64
import hashlib
import struct
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    _CRYPTOGRAPHY_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════
#  PKCS#7 padding
# ══════════════════════════════════════════════════════════════════


def _pkcs7_unpad(data: bytes) -> bytes:
    """Remove PKCS#7 padding from decrypted data."""
    if not data:
        raise ValueError("Empty data for PKCS7 unpad")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 32:
        raise ValueError(f"Invalid PKCS7 padding length: {pad_len}")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid PKCS7 padding bytes")
    return data[:-pad_len]


# ══════════════════════════════════════════════════════════════════
#  Signature
# ══════════════════════════════════════════════════════════════════


def calculate_signature(
    token: str,
    timestamp: str,
    nonce: str,
    encrypt: str,
) -> str:
    """
    Calculate WeCom SHA1 signature.

    Sorts [token, timestamp, nonce, encrypt] lexicographically,
    concatenates, and returns the SHA1 hex digest.
    """
    items = sorted([token, timestamp, nonce, encrypt])
    raw = "".join(items)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def verify_signature(
    token: str,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    encrypt: str,
) -> bool:
    """
    Verify a WeCom msg_signature against the expected SHA1.

    Returns True if valid, False otherwise.
    """
    expected = calculate_signature(token, timestamp, nonce, encrypt)
    return expected == msg_signature


# ══════════════════════════════════════════════════════════════════
#  AES key preparation
# ══════════════════════════════════════════════════════════════════


def _prepare_aes_key(encoding_aes_key: str) -> bytes:
    """
    Decode WeCom EncodingAESKey (43 chars) to 32-byte AES key.

    Raises ValueError if the key is invalid.
    """
    if not encoding_aes_key:
        raise ValueError("EncodingAESKey is empty")

    # Pad with '=' for base64 if needed (43 -> 44)
    padded = encoding_aes_key.strip()
    if len(padded) == 43:
        padded += "="
    elif len(padded) != 44:
        raise ValueError(
            f"EncodingAESKey must be 43 characters, got {len(encoding_aes_key.strip())}"
        )

    try:
        key = base64.b64decode(padded)
    except Exception as exc:
        raise ValueError(f"Base64 decode failed: {exc}") from exc

    if len(key) != 32:
        raise ValueError(
            f"AES key must be 32 bytes, got {len(key)} bytes"
        )

    return key


# ══════════════════════════════════════════════════════════════════
#  Decrypt WeCom encrypted message body (Encrypt field)
# ══════════════════════════════════════════════════════════════════


def _decrypt_aes_cbc(encrypted_data: bytes, aes_key: bytes) -> bytes:
    """Decrypt AES-CBC encrypted data with zero IV (first 16 bytes of key)."""
    iv = aes_key[:16]
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
    return decrypted


def _parse_decrypted_message(plaintext: bytes, corp_id: str) -> str:
    """
    Parse the decrypted WeCom message structure.

    Structure: [16 random bytes][4 bytes msg_len][msg][corp_id]
    """
    if len(plaintext) < 20:
        raise ValueError(
            f"Decrypted data too short: {len(plaintext)} bytes (min 20)"
        )

    # Read message length (4 bytes, network byte order)
    msg_len = struct.unpack(">I", plaintext[16:20])[0]

    # Extract message + corp_id
    msg_start = 20
    msg_end = msg_start + msg_len

    if msg_end > len(plaintext):
        raise ValueError(
            f"Message length {msg_len} exceeds available data "
            f"({len(plaintext) - 20} bytes)"
        )

    msg = plaintext[msg_start:msg_end].decode("utf-8", errors="replace")
    received_corp_id = plaintext[msg_end:].decode("utf-8", errors="replace")

    # Verify corp_id (case-insensitive)
    if corp_id and received_corp_id.lower() != corp_id.lower():
        raise ValueError(
            f"CorpID mismatch: expected '{corp_id}', "
            f"got '{received_corp_id}'"
        )

    return msg


def decrypt_wecom_message(
    encrypted_text: str,
    encoding_aes_key: str,
    corp_id: str,
) -> str:
    """
    Decrypt an encrypted WeCom message (the <Encrypt> field).

    Parameters
    ----------
    encrypted_text : str
        Base64-encoded encrypted message from <Encrypt> element.
    encoding_aes_key : str
        43-character WeCom EncodingAESKey.
    corp_id : str
        Enterprise WeCom CorpID (used to verify message integrity).

    Returns
    -------
    str — Decrypted plaintext XML message.

    Raises
    ------
    ValueError
        If crypto is unavailable, keys are invalid, or verification fails.
    """
    if not _CRYPTOGRAPHY_AVAILABLE:
        raise ValueError(
            "cryptography library is not installed. "
            "Run: pip install cryptography"
        )

    aes_key = _prepare_aes_key(encoding_aes_key)

    # Base64 decode the encrypted text
    try:
        encrypted_data = base64.b64decode(encrypted_text)
    except Exception as exc:
        raise ValueError(f"Base64 decode of encrypted_text failed: {exc}") from exc

    # Decrypt
    try:
        plaintext = _decrypt_aes_cbc(encrypted_data, aes_key)
        plaintext = _pkcs7_unpad(plaintext)
    except Exception as exc:
        raise ValueError(f"AES decryption failed: {exc}") from exc

    # Parse and verify
    return _parse_decrypted_message(plaintext, corp_id)


# ══════════════════════════════════════════════════════════════════
#  Decrypt echostr (URL verification)
# ══════════════════════════════════════════════════════════════════


def decrypt_wecom_echostr(
    echostr: str,
    encoding_aes_key: str,
    corp_id: str,
) -> str:
    """
    Decrypt an echostr from WeCom URL verification (GET /wecom/callback).

    The echostr is the <Encrypt> element value — decrypted the same way
    as a regular encrypted message, returning the plaintext echostr.

    Parameters
    ----------
    echostr : str
        Base64-encoded encrypted echostr from query parameter.
    encoding_aes_key : str
        43-character WeCom EncodingAESKey.
    corp_id : str
        Enterprise WeCom CorpID.

    Returns
    -------
    str — Decrypted plaintext echostr.
    """
    return decrypt_wecom_message(echostr, encoding_aes_key, corp_id)


# ══════════════════════════════════════════════════════════════════
#  Availability check
# ══════════════════════════════════════════════════════════════════


def is_cryptography_available() -> bool:
    """Return True if the cryptography package is installed."""
    return _CRYPTOGRAPHY_AVAILABLE


def is_crypto_configured() -> bool:
    """
    Quick check if WeCom crypto config is available in environment.

    Checks WECOM_CALLBACK_TOKEN, WECOM_ENCODING_AES_KEY, WECOM_CORP_ID.
    This is a lightweight check — does NOT load the full config.
    """
    import os
    token = os.environ.get("WECOM_CALLBACK_TOKEN", "").strip()
    aes_key = os.environ.get("WECOM_ENCODING_AES_KEY", "").strip()
    corp_id = os.environ.get("WECOM_CORP_ID", "").strip()
    return bool(token and aes_key and corp_id and _CRYPTOGRAPHY_AVAILABLE)
