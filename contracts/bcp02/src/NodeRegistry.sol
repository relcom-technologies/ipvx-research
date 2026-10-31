// SPDX-License-Identifier: MIT
pragma solidity 0.8.38;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";

/// @notice Permissionless identity registration, NOT permission to forward traffic.
/// No administrator, payments, proxy, recovery backdoor, burn or token-id reuse.
contract NodeRegistry is ERC721 {
    struct Record {
        uint64 keyEpoch;
        bytes32 signingKey;
        bytes32 encryptionKey;
        uint8 status;
        uint8 roles;
    }
    mapping(uint256 => Record) internal _nodes;
    uint256 private _nextTokenId = 1;

    error NotNodeOwner();
    error InvalidKeysOrRoles();
    error InactiveNode();

    event NodeChanged(uint256 indexed tokenId, address indexed owner, uint64 keyEpoch,
                      bytes32 signingKey, bytes32 encryptionKey, uint8 status, uint8 roles);

    constructor() ERC721("IPvX BCP 0.2 Node", "BCPN") {}

    function ownerOf(uint256 tokenId) public view override returns (address owner) {
        return super.ownerOf(tokenId);
    }

    function register(bytes32 signingKey, bytes32 encryptionKey, uint8 roles) external returns (uint256 tokenId) {
        _validateKeys(signingKey, encryptionKey, roles);
        tokenId = _nextTokenId++;
        _nodes[tokenId] = Record(1, signingKey, encryptionKey, 1, roles);
        // The record and id counter exist before any receiver callback. _update
        // emits NodeChanged before the callback; no stale post-callback writes.
        _safeMint(msg.sender, tokenId);
    }

    /// @notice Owner-only rotation or explicit reactivation after transfer/revoke.
    /// ERC-721 approvals authorize transfer, never operational keys or policies.
    function setKeys(uint256 tokenId, bytes32 signingKey, bytes32 encryptionKey, uint8 roles) external {
        _requireNodeOwner(tokenId);
        _validateKeys(signingKey, encryptionKey, roles);
        Record storage r = _nodes[tokenId];
        r.keyEpoch += 1; // checked uint64 arithmetic; wrap/reuse is forbidden
        r.signingKey = signingKey;
        r.encryptionKey = encryptionKey;
        r.status = 1;
        r.roles = roles;
        _emitNode(tokenId, msg.sender, r);
    }

    function revoke(uint256 tokenId) external {
        _requireNodeOwner(tokenId);
        Record storage r = _nodes[tokenId];
        if (r.status != 1) revert InactiveNode();
        _invalidate(r);
        _emitNode(tokenId, msg.sender, r);
    }

    function node(uint256 tokenId) external view returns (
        address owner, uint64 keyEpoch, bytes32 signingKey,
        bytes32 encryptionKey, uint8 status, uint8 roles
    ) {
        owner = _ownerOf(tokenId);
        if (owner == address(0)) return (address(0), 0, 0, 0, 0, 0);
        Record storage r = _nodes[tokenId];
        return (owner, r.keyEpoch, r.signingKey, r.encryptionKey, r.status, r.roles);
    }

    function _update(address to, uint256 tokenId, address auth) internal override returns (address from) {
        from = super._update(to, tokenId, auth);
        Record storage r = _nodes[tokenId];
        // Covers transferFrom, both safeTransferFrom variants and approved
        // operators. Even self-transfer invalidates old keys/consents.
        if (from != address(0)) _invalidate(r);
        _emitNode(tokenId, to, r);
    }

    function _invalidate(Record storage r) private {
        r.keyEpoch += 1;
        r.signingKey = 0;
        r.encryptionKey = 0;
        r.status = 2;
        r.roles = 0;
    }

    function _requireNodeOwner(uint256 tokenId) private view {
        if (ownerOf(tokenId) != msg.sender) revert NotNodeOwner();
    }

    function _validateKeys(bytes32 signingKey, bytes32 encryptionKey, uint8 roles) private pure {
        if (signingKey == 0 || encryptionKey == 0 || signingKey == encryptionKey || roles == 0 || roles > 3) {
            revert InvalidKeysOrRoles();
        }
    }

    function _emitNode(uint256 tokenId, address owner, Record storage r) private {
        emit NodeChanged(tokenId, owner, r.keyEpoch, r.signingKey, r.encryptionKey, r.status, r.roles);
    }
}
