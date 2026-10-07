"""Pinned Ed25519 controller authentication and encrypted, signed results.

The relay URL and both public keys are shareable. Private keys stay at their
respective ends; no provider credential is included in the protocol.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = 1


def encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode(value, length=None):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid protocol encoding.")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if length is not None and len(raw) != length:
        raise ValueError("Invalid protocol key or nonce length.")
    return raw


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def raw_private(key):
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def raw_public(key):
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class ControllerKeys:
    def __init__(self, signing=None, encryption=None):
        self.signing = signing or Ed25519PrivateKey.generate()
        self.encryption = encryption or X25519PrivateKey.generate()

    def public(self):
        return {"version": VERSION, "signing_key": encode(raw_public(self.signing.public_key())),
                "encryption_key": encode(raw_public(self.encryption.public_key()))}

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite an existing controller identity implicitly.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"version": VERSION, "signing_private": encode(raw_private(self.signing)),
                       "encryption_private": encode(raw_private(self.encryption))}, output)

    @classmethod
    def load(cls, path):
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        if record.get("version") != VERSION:
            raise ValueError("Unsupported controller key version.")
        return cls(Ed25519PrivateKey.from_private_bytes(decode(record["signing_private"], 32)),
                   X25519PrivateKey.from_private_bytes(decode(record["encryption_private"], 32)))


def public_keys(record):
    if record.get("version") != VERSION:
        raise ValueError("Unsupported controller key version.")
    return (Ed25519PublicKey.from_public_bytes(decode(record["signing_key"], 32)),
            X25519PublicKey.from_public_bytes(decode(record["encryption_key"], 32)))


def fingerprint(record):
    public_keys(record)
    return hashlib.sha256(canonical(record)).hexdigest()[:24]


def request_message(method, path, body, timestamp, nonce):
    return canonical({"version": VERSION, "method": method, "path": path,
                      "body_hash": hashlib.sha256(body).hexdigest(), "time": timestamp, "nonce": nonce})


def sign_request(keys, method, path, body, timestamp=None, nonce=None):
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    nonce = nonce or uuid.uuid4().hex
    return {"X-Agent-Time": timestamp, "X-Agent-Nonce": nonce,
            "X-Agent-Signature": encode(keys.signing.sign(request_message(method, path, body, timestamp, nonce)))}


class RequestVerifier:
    def __init__(self, public, clock=time.time):
        self.signing, self.encryption = public_keys(public)
        self.clock, self.seen, self.lock = clock, {}, threading.Lock()

    def verify(self, method, path, body, headers):
        timestamp, nonce = headers.get("X-Agent-Time"), headers.get("X-Agent-Nonce")
        if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]{1,12}", timestamp):
            raise ValueError("Invalid request time.")
        if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce):
            raise ValueError("Invalid request nonce.")
        current = self.clock()
        if abs(current - int(timestamp)) > 90:
            raise ValueError("Expired request.")
        self.signing.verify(decode(headers.get("X-Agent-Signature"), 64), request_message(method, path, body, timestamp, nonce))
        with self.lock:
            self.seen = {key: expiry for key, expiry in self.seen.items() if expiry > current}
            if nonce in self.seen or len(self.seen) >= 4096:
                raise ValueError("Repeated request or replay cache full.")
            self.seen[nonce] = current + 180
        return nonce


def derive_key(shared):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"app-agent-remote-results-v1").derive(shared)


def encrypt_result(encryption_public, signing_private, value, request_nonce):
    ephemeral = X25519PrivateKey.generate()
    iv = os.urandom(12)
    cipher = AESGCM(derive_key(ephemeral.exchange(encryption_public)))
    envelope = {"version": VERSION, "request_nonce": request_nonce,
                "ephemeral_key": encode(raw_public(ephemeral.public_key())), "iv": encode(iv),
                "ciphertext": encode(cipher.encrypt(iv, canonical(value), request_nonce.encode("ascii")))}
    return {**envelope, "signature": encode(signing_private.sign(canonical(envelope)))}


def decrypt_result(keys, signing_public, envelope, request_nonce):
    record = dict(envelope)
    signature = decode(record.pop("signature"), 64)
    signing_public.verify(signature, canonical(record))
    if record.get("version") != VERSION or record.get("request_nonce") != request_nonce:
        raise ValueError("Response belongs to another request or protocol.")
    ephemeral = X25519PublicKey.from_public_bytes(decode(record["ephemeral_key"], 32))
    cipher = AESGCM(derive_key(keys.encryption.exchange(ephemeral)))
    return json.loads(cipher.decrypt(decode(record["iv"], 12), decode(record["ciphertext"]), request_nonce.encode("ascii")))
