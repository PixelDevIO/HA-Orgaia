"""Keys, signatures and encryption, byte for byte as in Orgaia's packages/protocol/src/crypto.ts.

Ed25519, X25519 and HKDF-SHA256 come from ``cryptography``, which Home Assistant ships.
XChaCha20-Poly1305 is not in ``cryptography``; it is ChaCha20-Poly1305 with a key derived by
HChaCha20 from the first 16 bytes of the 24 byte nonce, so only HChaCha20 is written out here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import struct
from typing import Any

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .b64 import from_b64, to_b64


class CryptoError(Exception):
    """A signature or an encryption did not check out."""


def to_json(value: Any) -> str:
    """JSON as JavaScript's JSON.stringify writes it: no spaces, non-ASCII as is."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def random_bytes(n: int) -> bytes:
    return os.urandom(n)


def _hkdf(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _derive(seed: bytes, info: str, length: int = 32) -> bytes:
    return _hkdf(seed, b"orgaia-v1", info.encode(), length)


# --- XChaCha20-Poly1305 ----------------------------------------------------------------------

_MASK = 0xFFFFFFFF


def _rotl(v: int, c: int) -> int:
    return ((v << c) & _MASK) | (v >> (32 - c))


def _quarter(s: list[int], a: int, b: int, c: int, d: int) -> None:
    s[a] = (s[a] + s[b]) & _MASK
    s[d] = _rotl(s[d] ^ s[a], 16)
    s[c] = (s[c] + s[d]) & _MASK
    s[b] = _rotl(s[b] ^ s[c], 12)
    s[a] = (s[a] + s[b]) & _MASK
    s[d] = _rotl(s[d] ^ s[a], 8)
    s[c] = (s[c] + s[d]) & _MASK
    s[b] = _rotl(s[b] ^ s[c], 7)


def hchacha20(key: bytes, nonce16: bytes) -> bytes:
    """The HChaCha20 subkey of RFC draft-irtf-cfrg-xchacha."""
    if len(key) != 32 or len(nonce16) != 16:
        raise ValueError("hchacha20 needs a 32 byte key and a 16 byte nonce")
    s = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *struct.unpack("<8I", key), *struct.unpack("<4I", nonce16)]
    for _ in range(10):
        _quarter(s, 0, 4, 8, 12)
        _quarter(s, 1, 5, 9, 13)
        _quarter(s, 2, 6, 10, 14)
        _quarter(s, 3, 7, 11, 15)
        _quarter(s, 0, 5, 10, 15)
        _quarter(s, 1, 6, 11, 12)
        _quarter(s, 2, 7, 8, 13)
        _quarter(s, 3, 4, 9, 14)
    return struct.pack("<8I", *s[0:4], *s[12:16])


def _xchacha(key: bytes, nonce: bytes) -> tuple[ChaCha20Poly1305, bytes]:
    if len(nonce) != 24:
        raise ValueError("xchacha20 needs a 24 byte nonce")
    return ChaCha20Poly1305(hchacha20(key, nonce[:16])), b"\x00\x00\x00\x00" + nonce[16:]


def xchacha_encrypt(key: bytes, nonce: bytes, plain: bytes, aad: bytes | None = None) -> bytes:
    aead, n = _xchacha(key, nonce)
    return aead.encrypt(n, plain, aad)


def xchacha_decrypt(key: bytes, nonce: bytes, cipher: bytes, aad: bytes | None = None) -> bytes:
    aead, n = _xchacha(key, nonce)
    try:
        return aead.decrypt(n, cipher, aad)
    except InvalidTag as err:
        raise CryptoError("cannot decrypt") from err


# --- Identity ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Identity:
    """A member's keys, all derived from a 32 byte seed."""

    seed: bytes
    sign_key: Ed25519PrivateKey
    sign_pub: str
    box_key: X25519PrivateKey
    box_pub: str
    box_sig: str

    @classmethod
    def from_seed(cls, seed: bytes) -> Identity:
        if len(seed) != 32:
            raise ValueError("seed must be 32 bytes")
        sign_key = Ed25519PrivateKey.from_private_bytes(_derive(seed, "sign"))
        box_key = X25519PrivateKey.from_private_bytes(_derive(seed, "box"))
        sign_pub = sign_key.public_key().public_bytes_raw()
        box_pub = box_key.public_key().public_bytes_raw()
        return cls(
            seed=seed,
            sign_key=sign_key,
            sign_pub=to_b64(sign_pub),
            box_key=box_key,
            box_pub=to_b64(box_pub),
            box_sig=to_b64(sign_key.sign(b"orgaia-box:" + box_pub)),
        )

    @classmethod
    def create(cls) -> Identity:
        return cls.from_seed(random_bytes(32))

    def sign(self, message: bytes) -> str:
        return to_b64(self.sign_key.sign(message))


def verify(sig: str, message: bytes, sign_pub: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(from_b64(sign_pub)).verify(from_b64(sig), message)
    except (InvalidSignature, ValueError):
        return False
    return True


def verify_box_key(sign_pub: str, box_pub: str, box_sig: str) -> bool:
    try:
        return verify(box_sig, b"orgaia-box:" + from_b64(box_pub), sign_pub)
    except ValueError:
        return False


def fingerprint(sign_pub: str) -> str:
    """The short safety number people compare, as the app shows it."""
    return to_b64(hashlib.sha256(from_b64(sign_pub)).digest()[:6])


def private_space(seed: bytes) -> tuple[str, bytes]:
    return "p" + to_b64(_derive(seed, "private-space-id", 15)), _derive(seed, "private-space-key")


# --- Records of a space ------------------------------------------------------------------------


def _record_sig_input(space_id: str, epoch: int, nonce: bytes, cipher: bytes) -> bytes:
    return f"orgaia-op:{space_id}:{epoch}:".encode() + nonce + cipher


def seal_record(
    space_id: str, epoch: int, key: bytes, author: Identity, payload: Any, nonce: bytes | None = None
) -> dict[str, Any]:
    """Encrypts and signs a change (or a snapshot) for the sync service."""
    nonce = nonce if nonce is not None else random_bytes(24)
    cipher = xchacha_encrypt(key, nonce, to_json(payload).encode(), f"{space_id}:{epoch}".encode())
    return {
        "e": epoch,
        "n": to_b64(nonce),
        "c": to_b64(cipher),
        "a": author.sign_pub,
        "s": author.sign(_record_sig_input(space_id, epoch, nonce, cipher)),
    }


def open_record(space_id: str, key: bytes, rec: dict[str, Any]) -> Any:
    """Checks the author's signature and decrypts. Raises CryptoError when either fails."""
    try:
        epoch = rec["e"]
        nonce = from_b64(rec["n"])
        cipher = from_b64(rec["c"])
        author = rec["a"]
        sig = rec["s"]
    except (KeyError, TypeError, ValueError) as err:
        raise CryptoError("malformed record") from err
    if not isinstance(epoch, int) or not verify(sig, _record_sig_input(space_id, epoch, nonce, cipher), author):
        raise CryptoError("bad signature")
    plain = xchacha_decrypt(key, nonce, cipher, f"{space_id}:{epoch}".encode())
    try:
        return json.loads(plain.decode())
    except (UnicodeDecodeError, ValueError) as err:
        raise CryptoError("bad payload") from err


# --- Payloads for one recipient ----------------------------------------------------------------


def seal_for(
    recipient_box_pub: str,
    sender: Identity,
    context: str,
    payload: Any,
    eph_secret: bytes | None = None,
    nonce: bytes | None = None,
) -> str:
    """Encrypts for the holder of ``recipient_box_pub`` and signs as ``sender`` (join requests, key envelopes)."""
    eph = X25519PrivateKey.from_private_bytes(eph_secret if eph_secret is not None else random_bytes(32))
    eph_pub = eph.public_key().public_bytes_raw()
    recipient = from_b64(recipient_box_pub)
    shared = eph.exchange(X25519PublicKey.from_public_bytes(recipient))
    key = _hkdf(shared, eph_pub + recipient, ("orgaia-seal:" + context).encode())
    nonce = nonce if nonce is not None else random_bytes(24)
    body = eph_pub + nonce + xchacha_encrypt(key, nonce, to_json(payload).encode())
    sig = sender.sign(("orgaia-seal:" + context + ":").encode() + recipient + body)
    return to_b64(body) + "." + sender.sign_pub + "." + sig


def open_sealed(sealed: str, me: Identity, context: str) -> tuple[Any, str]:
    """Opens what ``seal_for`` made for ``me``. Returns the payload and the sender's signing key."""
    parts = sealed.split(".") if isinstance(sealed, str) else []
    if len(parts) != 3 or not all(parts):
        raise CryptoError("malformed sealed payload")
    body_text, sender, sig = parts
    try:
        body = from_b64(body_text)
    except ValueError as err:
        raise CryptoError("malformed sealed payload") from err
    my_pub = from_b64(me.box_pub)
    if len(body) < 56 + 16 or not verify(sig, ("orgaia-seal:" + context + ":").encode() + my_pub + body, sender):
        raise CryptoError("bad signature")
    eph_pub, nonce, cipher = body[:32], body[32:56], body[56:]
    try:
        shared = me.box_key.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    except ValueError as err:
        raise CryptoError("bad key") from err
    key = _hkdf(shared, eph_pub + my_pub, ("orgaia-seal:" + context).encode())
    plain = xchacha_decrypt(key, nonce, cipher)
    try:
        return json.loads(plain.decode()), sender
    except (UnicodeDecodeError, ValueError) as err:
        raise CryptoError("bad payload") from err
