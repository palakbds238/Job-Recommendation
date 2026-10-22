"""
blockchain.py — thin Python client for contracts/CredentialRegistry.sol

Modes (env BLOCKCHAIN_MODE):
  local   (default) in-memory Ethereum test chain via eth-tester. Zero setup.
                    The chain resets on restart; app.py replays recorded hashes
                    into the fresh chain, so this is a *simulated* ledger — good
                    for development and demos, not for real immutability.
  remote            any EVM chain (e.g. Sepolia). Requires:
                      BLOCKCHAIN_RPC_URL, ISSUER_PRIVATE_KEY, and optionally
                      CONTRACT_ADDRESS (if empty, the contract is deployed once
                      and the address is printed — put it in your env).
  off               feature disabled; the rest of the app keeps working.

Only 32-byte hashes ever go on-chain. Personal data stays in the database.
"""
import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path

log = logging.getLogger("blockchain")
ARTIFACT = Path(__file__).parent / "contracts" / "CredentialRegistry.json"


class ChainError(Exception):
    """Raised for any blockchain failure; callers decide how to degrade."""


# ── hashing helpers (pure, no chain needed) ─────────────────────────────────
def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def credential_hash(user_id: int, title: str, issuer_name: str,
                    skills: list, issued_on: str, salt: str) -> str:
    """sha256 over a canonical JSON record. The random per-credential `salt`
    stops anyone brute-forcing the hash from guessable fields."""
    return hashlib.sha256(_canonical({
        "type": "credential", "user_id": user_id, "title": title.strip(),
        "issuer": issuer_name.strip(),
        "skills": sorted(s.strip().lower() for s in skills),
        "issued_on": issued_on, "salt": salt,
    })).hexdigest()


def application_hash(user_id: int, job_id: int, job_title: str,
                     company: str, applied_at: str, salt: str) -> str:
    return hashlib.sha256(_canonical({
        "type": "application", "user_id": user_id, "job_id": job_id,
        "title": job_title, "company": company,
        "applied_at": applied_at, "salt": salt,
    })).hexdigest()


def _b32(hex_hash: str) -> bytes:
    h = hex_hash[2:] if hex_hash.startswith("0x") else hex_hash
    if len(h) != 64:
        raise ChainError("hash must be 32 bytes (64 hex chars)")
    return bytes.fromhex(h)


# ── client ──────────────────────────────────────────────────────────────────
class ChainClient:
    def __init__(self):
        self.mode = os.environ.get("BLOCKCHAIN_MODE", "local").lower()
        self.w3 = None
        self.contract = None
        self.account = None
        self.private_key = None
        self.network = "disabled"
        self.error = None
        self._lock = threading.Lock()
        self._ready = False

    # lazy init so importing the app never needs a chain
    def _init(self):
        if self._ready or self.mode == "off":
            return
        try:
            from web3 import Web3
            art = json.loads(ARTIFACT.read_text())
            if self.mode == "remote":
                url = os.environ["BLOCKCHAIN_RPC_URL"]
                self.w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
                self.private_key = os.environ["ISSUER_PRIVATE_KEY"]
                self.account = self.w3.eth.account.from_key(self.private_key).address
                self.network = f"chain-id {self.w3.eth.chain_id}"
                addr = os.environ.get("CONTRACT_ADDRESS", "").strip()
                if addr:
                    self.contract = self.w3.eth.contract(
                        address=Web3.to_checksum_address(addr), abi=art["abi"])
                else:
                    self.contract = self._deploy(art)
                    log.warning("Deployed CredentialRegistry at %s — set "
                                "CONTRACT_ADDRESS to reuse it.", self.contract.address)
            else:  # local
                from web3 import EthereumTesterProvider
                self.w3 = Web3(EthereumTesterProvider())
                self.account = self.w3.eth.accounts[0]
                self.network = "local simulated chain (resets on restart)"
                self.contract = self._deploy(art)
            self._ready = True
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"
            log.error("Blockchain init failed: %s", self.error)
            raise ChainError(self.error) from e

    def _deploy(self, art):
        factory = self.w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
        txh = self._send(factory.constructor())
        rcpt = self.w3.eth.wait_for_transaction_receipt(txh, timeout=120)
        return self.w3.eth.contract(address=rcpt.contractAddress, abi=art["abi"])

    def _send(self, fn):
        """Send a contract call as the issuer account; returns tx hash."""
        if self.mode == "remote":
            tx = fn.build_transaction({
                "from": self.account,
                "nonce": self.w3.eth.get_transaction_count(self.account),
                "chainId": self.w3.eth.chain_id,
            })
            signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
            return self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return fn.transact({"from": self.account})

    def _tx(self, fn):
        self._init()
        with self._lock:
            try:
                txh = self._send(fn)
                rcpt = self.w3.eth.wait_for_transaction_receipt(txh, timeout=120)
            except Exception as e:  # noqa: BLE001
                raise ChainError(_clean(e)) from e
        if rcpt.status != 1:
            raise ChainError("transaction reverted")
        return {"tx_hash": "0x" + bytes(rcpt.transactionHash).hex(),
                "block": rcpt.blockNumber}

    # ── public API ──────────────────────────────────────────────────────────
    @property
    def enabled(self):
        return self.mode != "off"

    def status(self):
        info = {"enabled": self.enabled, "mode": self.mode, "network": self.network,
                "contract": None, "issuer": None, "ok": False, "error": self.error}
        if not self.enabled:
            return info
        try:
            self._init()
            info.update(contract=self.contract.address, issuer=self.account,
                        network=self.network, ok=True, error=None)
        except ChainError as e:
            info["error"] = str(e)
        return info

    def issue_credential(self, hex_hash):
        return self._tx(self.contract_fn("issue", _b32(hex_hash)))

    def revoke_credential(self, hex_hash):
        return self._tx(self.contract_fn("revoke", _b32(hex_hash)))

    def anchor_application(self, hex_hash):
        return self._tx(self.contract_fn("anchorApplication", _b32(hex_hash)))

    def verify_credential(self, hex_hash):
        self._init()
        try:
            exists, revoked, issuer, ts = self.contract.functions.verify(
                _b32(hex_hash)).call()
        except Exception as e:  # noqa: BLE001
            raise ChainError(_clean(e)) from e
        return {"exists": exists, "revoked": revoked,
                "issuer": issuer if exists else None, "issued_at": ts}

    def application_time(self, hex_hash):
        self._init()
        try:
            return self.contract.functions.applicationTime(_b32(hex_hash)).call()
        except Exception as e:  # noqa: BLE001
            raise ChainError(_clean(e)) from e

    def contract_fn(self, name, *args):
        self._init()
        return getattr(self.contract.functions, name)(*args)


_REVERT = re.compile(r"revert(?:ed)?:?\s+(?:VM Exception while processing "
                     r"transaction: revert\s+)?([A-Za-z][A-Za-z0-9 ,.\-]*)")


def _clean(e):
    """Short, human-readable message (extracts the contract's revert reason)."""
    msg = str(e)
    m = _REVERT.search(msg)
    if m:
        return "Contract rejected the transaction: " + m.group(1).strip()
    return msg if len(msg) < 300 else msg[:300] + "…"


chain = ChainClient()
