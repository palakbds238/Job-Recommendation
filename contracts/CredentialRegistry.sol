// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * CredentialRegistry
 * ------------------
 * Stores ONLY hashes — never personal data.
 *
 *  1. Credentials : an authorised issuer anchors the hash of a credential
 *                   (degree, certificate, skill badge). Anyone can verify it.
 *  2. Applications: the platform anchors the hash of a job application so
 *                   neither side can later dispute that / when it was made.
 */
contract CredentialRegistry {
    address public owner;
    mapping(address => bool) public issuers;

    struct Credential {
        address issuer;
        uint64  issuedAt;
        bool    revoked;
    }

    mapping(bytes32 => Credential) private credentials;
    mapping(bytes32 => uint64)     private applications;

    event IssuerAdded(address indexed issuer);
    event IssuerRemoved(address indexed issuer);
    event CredentialIssued(bytes32 indexed credentialHash, address indexed issuer);
    event CredentialRevoked(bytes32 indexed credentialHash, address indexed issuer);
    event ApplicationAnchored(bytes32 indexed applicationHash, uint64 anchoredAt);

    modifier onlyOwner()  { require(msg.sender == owner, "Not owner");  _; }
    modifier onlyIssuer() { require(issuers[msg.sender], "Not an issuer"); _; }

    constructor() {
        owner = msg.sender;
        issuers[msg.sender] = true;
        emit IssuerAdded(msg.sender);
    }

    // ── Issuer management ────────────────────────────────────────────────
    function addIssuer(address a) external onlyOwner {
        issuers[a] = true;
        emit IssuerAdded(a);
    }

    function removeIssuer(address a) external onlyOwner {
        require(a != owner, "Cannot remove owner");
        issuers[a] = false;
        emit IssuerRemoved(a);
    }

    // ── Credentials ──────────────────────────────────────────────────────
    function issue(bytes32 h) external onlyIssuer {
        require(credentials[h].issuedAt == 0, "Already issued");
        credentials[h] = Credential(msg.sender, uint64(block.timestamp), false);
        emit CredentialIssued(h, msg.sender);
    }

    /// Only the issuer that issued a credential can revoke it.
    function revoke(bytes32 h) external onlyIssuer {
        Credential storage c = credentials[h];
        require(c.issuedAt != 0, "Unknown credential");
        require(c.issuer == msg.sender, "Only original issuer");
        require(!c.revoked, "Already revoked");
        c.revoked = true;
        emit CredentialRevoked(h, msg.sender);
    }

    function verify(bytes32 h) external view
        returns (bool exists, bool revoked, address issuer, uint64 issuedAt)
    {
        Credential memory c = credentials[h];
        return (c.issuedAt != 0, c.revoked, c.issuer, c.issuedAt);
    }

    // ── Applications ─────────────────────────────────────────────────────
    function anchorApplication(bytes32 h) external onlyIssuer {
        require(applications[h] == 0, "Already anchored");
        applications[h] = uint64(block.timestamp);
        emit ApplicationAnchored(h, uint64(block.timestamp));
    }

    function applicationTime(bytes32 h) external view returns (uint64) {
        return applications[h];
    }
}
