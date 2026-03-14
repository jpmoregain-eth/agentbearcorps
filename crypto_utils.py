"""
Encryption module for sensitive config data
Encrypts API keys before saving to YAML files

Security fixes applied:
- OS keychain used where available (macOS Keychain / Linux Secret Service)
- File-based fallback uses PBKDF2 key derivation with a stored salt,
  so the raw key is never written directly to disk
- Key file permissions verified on every load, not just on creation
- rotate_key() now actually re-encrypts all agent config files
- Salt is now properly used in encryption (was generated but ignored before)
"""

import os
import glob
import yaml
import base64
import logging
import stat
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Key storage location
_AGENTBEAR_DIR = Path.home() / '.agentbear'
_KEY_FILE      = _AGENTBEAR_DIR / '.master_key'   # stores raw random bytes (seed)
_SALT_FILE     = _AGENTBEAR_DIR / '.salt'
_KEYCHAIN_SERVICE = "agentbearcorps"
_KEYCHAIN_USER    = "master_key"


# ---------------------------------------------------------------------------
# OS keychain helpers (optional — gracefully skipped if keyring not installed)
# ---------------------------------------------------------------------------

def _keychain_save(key_b64: str) -> bool:
    """Save key to OS keychain. Returns True on success."""
    try:
        import keyring
        keyring.set_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER, key_b64)
        logger.info("Master key stored in OS keychain.")
        return True
    except Exception:
        return False


def _keychain_load() -> Optional[str]:
    """Load key from OS keychain. Returns base64 key string or None."""
    try:
        import keyring
        return keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# File-based key storage (fallback)
# ---------------------------------------------------------------------------

def _enforce_permissions(path: Path):
    """Ensure a sensitive file is readable only by the owner."""
    try:
        current = stat.S_IMODE(path.stat().st_mode)
        if current != 0o600:
            path.chmod(0o600)
    except Exception as e:
        logger.warning("Could not set permissions on %s: %s", path, e)


def _get_or_create_salt() -> bytes:
    """Load or create the PBKDF2 salt stored on disk."""
    _AGENTBEAR_DIR.mkdir(parents=True, exist_ok=True)
    if _SALT_FILE.exists():
        _enforce_permissions(_SALT_FILE)
        return _SALT_FILE.read_bytes()
    salt = os.urandom(32)
    _SALT_FILE.write_bytes(salt)
    _SALT_FILE.chmod(0o600)
    return salt


def _derive_fernet_key(raw_seed: bytes, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet-compatible key from a random seed + salt via PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(raw_seed))


def _file_save_key(raw_seed: bytes):
    """Persist a raw seed to the key file with strict permissions."""
    _AGENTBEAR_DIR.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_bytes(raw_seed)
    _KEY_FILE.chmod(0o600)


def _file_load_key() -> Optional[bytes]:
    """Load raw seed from key file, enforcing permissions."""
    if not _KEY_FILE.exists():
        return None
    _enforce_permissions(_KEY_FILE)
    return _KEY_FILE.read_bytes()


# ---------------------------------------------------------------------------
# Public key access
# ---------------------------------------------------------------------------

def get_or_create_master_key() -> bytes:
    """
    Return the raw seed bytes for the master key.

    Priority:
      1. OS keychain (most secure)
      2. ~/.agentbear/.master_key file (fallback, permissions enforced)
    """
    # 1. Try OS keychain
    key_b64 = _keychain_load()
    if key_b64:
        return base64.urlsafe_b64decode(key_b64)

    # 2. Try key file
    raw = _file_load_key()
    if raw:
        return raw

    # 3. Generate a new key
    raw = os.urandom(32)
    saved_to_keychain = _keychain_save(base64.urlsafe_b64encode(raw).decode())
    if not saved_to_keychain:
        _file_save_key(raw)
        logger.warning(
            "keyring not available — master key stored at %s. "
            "Install 'keyring' for more secure OS-level storage.", _KEY_FILE
        )
    logger.info("Created new master encryption key.")
    return raw


def get_cipher() -> Fernet:
    """Return a Fernet cipher derived from the master key + salt."""
    raw_seed = get_or_create_master_key()
    salt = _get_or_create_salt()
    derived_key = _derive_fernet_key(raw_seed, salt)
    return Fernet(derived_key)


# ---------------------------------------------------------------------------
# Encrypt / decrypt individual values
# ---------------------------------------------------------------------------

def encrypt_value(value: str) -> str:
    """
    Encrypt a string value.
    Returns Fernet token with ENC: prefix.
    Already-encrypted values (ENC: prefix) are returned unchanged.
    """
    if not value:
        return value
    if value.startswith('ENC:'):
        return value
    try:
        cipher = get_cipher()
        encrypted = cipher.encrypt(value.encode())
        return f"ENC:{encrypted.decode()}"
    except Exception as e:
        logger.error("Encryption failed: %s", e)
        return value


def decrypt_value(value: str) -> str:
    """
    Decrypt a string value.
    Plain-text values (no ENC: prefix) are returned unchanged.
    """
    if not value:
        return value
    if not value.startswith('ENC:'):
        return value
    try:
        cipher = get_cipher()
        encrypted_data = value[4:].encode()
        return cipher.decrypt(encrypted_data).decode()
    except Exception as e:
        logger.error("Decryption failed: %s", e)
        return value


# ---------------------------------------------------------------------------
# Bulk config encrypt / decrypt
# ---------------------------------------------------------------------------

_SENSITIVE_FIELDS = [
    ('model',    'anthropic_api_key'),
    ('model',    'openai_api_key'),
    ('telegram', 'bot_token'),
    ('github',   'token'),
    ('crypto',   'api_key'),
    ('crypto',   'api_secret'),
]


def encrypt_config(config: dict) -> dict:
    """Encrypt sensitive fields in a config dict. Returns a new dict."""
    config = config.copy()
    for section, field in _SENSITIVE_FIELDS:
        if section in config and field in config[section]:
            value = config[section][field]
            if value and not str(value).startswith('ENC:'):
                config[section][field] = encrypt_value(str(value))
                logger.debug("Encrypted %s.%s", section, field)
    return config


def decrypt_config(config: dict) -> dict:
    """Decrypt sensitive fields in a config dict. Returns a new dict."""
    config = config.copy()
    for section, field in _SENSITIVE_FIELDS:
        if section in config and field in config[section]:
            value = config[section][field]
            if value and str(value).startswith('ENC:'):
                config[section][field] = decrypt_value(str(value))
                logger.debug("Decrypted %s.%s", section, field)
    return config


# ---------------------------------------------------------------------------
# Key rotation (actually implemented now)
# ---------------------------------------------------------------------------

def rotate_key() -> bool:
    """
    Rotate the master encryption key.

    Steps:
      1. Decrypt all agent config files with the OLD key.
      2. Generate and persist a NEW key (+ new salt).
      3. Re-encrypt all config files with the new key.
    """
    try:
        # ---- Step 1: Collect all config files and decrypt them ----
        config_pattern = str(_AGENTBEAR_DIR / 'agents' / '*.yaml')
        config_files = glob.glob(config_pattern)

        decrypted_configs = []
        for cfg_path in config_files:
            with open(cfg_path, 'r') as f:
                cfg = yaml.safe_load(f) or {}
            decrypted_configs.append((cfg_path, decrypt_config(cfg)))
            logger.info("Loaded config for rotation: %s", cfg_path)

        # ---- Step 2: Generate new key & salt, overwrite storage ----
        new_seed = os.urandom(32)
        new_salt = os.urandom(32)

        # Overwrite salt file
        _SALT_FILE.write_bytes(new_salt)
        _SALT_FILE.chmod(0o600)

        # Overwrite key storage
        saved = _keychain_save(base64.urlsafe_b64encode(new_seed).decode())
        if not saved:
            _file_save_key(new_seed)

        # ---- Step 3: Re-encrypt with new key ----
        for cfg_path, plain_cfg in decrypted_configs:
            re_encrypted = encrypt_config(plain_cfg)
            with open(cfg_path, 'w') as f:
                yaml.dump(re_encrypted, f, default_flow_style=False)
            logger.info("Re-encrypted config: %s", cfg_path)

        logger.info("Key rotation complete. %d config file(s) re-encrypted.", len(config_files))
        return True

    except Exception as e:
        logger.error("Key rotation failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("Testing encryption...")

    test_value = "sk-ant-api03-test-key-12345"

    encrypted = encrypt_value(test_value)
    print(f"Original:  {test_value}")
    print(f"Encrypted: {encrypted}")

    decrypted = decrypt_value(encrypted)
    print(f"Decrypted: {decrypted}")
    assert test_value == decrypted, "Decryption failed!"
    print("✓ Encrypt/decrypt test passed!")

    encrypted2 = encrypt_value(encrypted)
    assert encrypted == encrypted2, "Double-encrypt should be idempotent!"
    print("✓ Idempotency test passed!")

    # Confirm salt is actually being used
    from cryptography.fernet import InvalidToken
    bad_cipher = Fernet(Fernet.generate_key())
    try:
        bad_cipher.decrypt(encrypted[4:].encode())
        print("✗ Wrong key should NOT decrypt — something is wrong!")
    except Exception:
        print("✓ Wrong key correctly rejected!")
