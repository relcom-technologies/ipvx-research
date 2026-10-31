// SPDX-License-Identifier: MIT
pragma solidity 0.8.38;

import {INodeRegistry} from "./INodeRegistry.sol";

/// @dev Shared proposal/consent state. A stored proposal is effective only when
/// both explicit consents and both current active node epochs still match.
abstract contract BilateralPolicy {
    INodeRegistry public immutable registry;

    struct Agreement {
        uint256 source;
        uint256 destination;
        uint64 version;
        uint64 sourceEpoch;
        uint64 destinationEpoch;
        uint8 consents;
    }
    mapping(bytes32 => Agreement) internal _agreements;

    error InvalidRegistry();
    error InvalidEndpoints();
    error NotPartyOwner();
    error InactiveParty();
    error MissingRule();
    error StaleVersion();
    error StaleEpoch();
    error InvalidParameters();

    event Proposed(bytes32 indexed ruleId, uint64 version, uint256 source, uint256 destination,
                   uint64 sourceEpoch, uint64 destinationEpoch);
    event Consented(bytes32 indexed ruleId, uint64 version, uint256 indexed partyNft, uint64 epoch);
    event Withdrawn(bytes32 indexed ruleId, uint64 version, uint256 indexed partyNft);

    constructor(address nodeRegistry) {
        if (nodeRegistry.code.length == 0) revert InvalidRegistry();
        registry = INodeRegistry(nodeRegistry);
    }

    function consent(bytes32 ruleId, uint64 expectedVersion, uint256 partyNft) external {
        Agreement storage a = _existing(ruleId, expectedVersion);
        uint8 bit = _partyBit(a, partyNft);
        // OwnerOf allows no delegated ERC-721 approval to consent.
        if (registry.ownerOf(partyNft) != msg.sender) revert NotPartyOwner();
        (, uint64 sourceEpoch) = _active(a.source);
        (, uint64 destinationEpoch) = _active(a.destination);
        if (sourceEpoch != a.sourceEpoch || destinationEpoch != a.destinationEpoch) revert StaleEpoch();
        a.consents |= bit;
        emit Consented(ruleId, a.version, partyNft, partyNft == a.source ? sourceEpoch : destinationEpoch);
    }

    /// @notice Either current owner can withdraw, including after a node becomes
    /// inactive. A new version clears BOTH consents; old approvals cannot revive.
    function withdraw(bytes32 ruleId, uint64 expectedVersion, uint256 partyNft) external {
        Agreement storage a = _existing(ruleId, expectedVersion);
        _partyBit(a, partyNft);
        if (registry.ownerOf(partyNft) != msg.sender) revert NotPartyOwner();
        a.version += 1;
        a.consents = 0;
        emit Withdrawn(ruleId, a.version, partyNft);
    }

    function _propose(bytes32 ruleId, uint256 source, uint256 destination) internal {
        if (source == destination) revert InvalidEndpoints();
        (address sourceOwner, uint64 sourceEpoch) = _active(source);
        (address destinationOwner, uint64 destinationEpoch) = _active(destination);
        if (msg.sender != sourceOwner && msg.sender != destinationOwner) revert NotPartyOwner();
        Agreement storage a = _agreements[ruleId];
        if (a.version != 0 && (a.source != source || a.destination != destination)) revert InvalidEndpoints();
        a.source = source;
        a.destination = destination;
        a.version += 1;
        a.sourceEpoch = sourceEpoch;
        a.destinationEpoch = destinationEpoch;
        a.consents = 0;
        emit Proposed(ruleId, a.version, source, destination, sourceEpoch, destinationEpoch);
    }

    function _active(uint256 nft) internal view returns (address owner, uint64 epoch) {
        bytes32 signingKey;
        bytes32 encryptionKey;
        uint8 status;
        uint8 roles;
        (owner, epoch, signingKey, encryptionKey, status, roles) = registry.node(nft);
        if (status != 1 || owner == address(0) || epoch == 0 || roles == 0 || roles > 3
            || signingKey == 0 || encryptionKey == 0 || registry.ownerOf(nft) != owner) revert InactiveParty();
    }

    function _effective(Agreement storage a) internal view returns (bool) {
        if (a.version == 0 || a.consents != 3) return false;
        (address ownerA, uint64 epochA,,, uint8 statusA,) = registry.node(a.source);
        (address ownerB, uint64 epochB,,, uint8 statusB,) = registry.node(a.destination);
        return statusA == 1 && statusB == 1 && epochA == a.sourceEpoch && epochB == a.destinationEpoch
            && ownerA != address(0) && ownerB != address(0)
            && registry.ownerOf(a.source) == ownerA && registry.ownerOf(a.destination) == ownerB;
    }

    function _existing(bytes32 ruleId, uint64 expectedVersion) private view returns (Agreement storage a) {
        a = _agreements[ruleId];
        if (a.version == 0) revert MissingRule();
        if (a.version != expectedVersion) revert StaleVersion();
    }

    function _partyBit(Agreement storage a, uint256 partyNft) private view returns (uint8) {
        if (partyNft == a.source) return 1;
        if (partyNft == a.destination) return 2;
        revert InvalidEndpoints();
    }

    function _validateTraffic(uint32 trafficMask, uint16 maxCiphertext) internal pure {
        if (trafficMask == 0 || trafficMask > 7 || maxCiphertext < 16 || maxCiphertext > 1500) {
            revert InvalidParameters();
        }
    }
}
