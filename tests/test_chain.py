import pytest
from blockchain import ChainClient, ChainError, credential_hash, application_hash


@pytest.fixture()
def c():
    cl = ChainClient()
    cl.mode = "local"
    cl._init()
    return cl


H = "ab" * 32


def test_issue_verify_revoke(c):
    assert c.verify_credential(H)["exists"] is False
    c.issue_credential(H)
    v = c.verify_credential(H)
    assert v["exists"] and not v["revoked"] and v["issuer"] == c.account
    c.revoke_credential(H)
    assert c.verify_credential(H)["revoked"] is True


def test_duplicate_issue_rejected(c):
    c.issue_credential(H)
    with pytest.raises(ChainError):
        c.issue_credential(H)


def test_only_issuers_can_issue(c):
    stranger = c.w3.eth.accounts[1]
    with pytest.raises(Exception, match="Not an issuer"):
        c.contract.functions.issue(bytes.fromhex(H)).transact({"from": stranger})


def test_only_original_issuer_can_revoke(c):
    other = c.w3.eth.accounts[1]
    c.contract.functions.addIssuer(other).transact({"from": c.account})
    c.issue_credential(H)
    with pytest.raises(Exception, match="Only original issuer"):
        c.contract.functions.revoke(bytes.fromhex(H)).transact({"from": other})


def test_application_anchor_is_one_time(c):
    assert c.application_time(H) == 0
    c.anchor_application(H)
    assert c.application_time(H) > 0
    with pytest.raises(ChainError):
        c.anchor_application(H)


def test_hash_is_salted_and_deterministic():
    a = credential_hash(1, "T", "I", ["Python", "SQL"], "2026-01-01", "s1")
    assert a == credential_hash(1, "T", "I", ["sql", "python"], "2026-01-01", "s1")
    assert a != credential_hash(1, "T", "I", ["Python", "SQL"], "2026-01-01", "s2")
    assert len(application_hash(1, 2, "t", "c", "now", "s")) == 64


def test_bad_hash_length_rejected(c):
    with pytest.raises(ChainError):
        c.issue_credential("abcd")
