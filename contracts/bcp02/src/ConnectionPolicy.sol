// SPDX-License-Identifier: MIT
pragma solidity 0.8.38;

import {BilateralPolicy} from "./BilateralPolicy.sol";
import {TransitPolicy} from "./TransitPolicy.sol";

contract ConnectionPolicy is BilateralPolicy {
    bytes32 private constant RULE_DOMAIN = keccak256("IPvX-BCP/0.2/connection-rule");
    uint256 public constant MAX_ALLOWED_EDGES = 64;
    TransitPolicy public immutable transit;

    struct Terms {
        uint32 trafficMask;
        uint8 maxHops;
        uint16 maxCiphertext;
        bytes32[] edges;
    }
    mapping(bytes32 => Terms) internal _terms;
    mapping(bytes32 => mapping(bytes32 => uint64)) private _edgeVersions;

    constructor(address nodeRegistry, address transitPolicy) BilateralPolicy(nodeRegistry) {
        if (transitPolicy.code.length == 0) revert InvalidRegistry();
        transit = TransitPolicy(transitPolicy);
        if (address(transit.registry()) != nodeRegistry) revert InvalidRegistry();
    }

    function ruleIdFor(uint256 sourceNft, uint256 destinationNft, bytes32 salt) public view returns (bytes32) {
        return keccak256(abi.encode(RULE_DOMAIN, block.chainid, address(this), sourceNft, destinationNft, salt));
    }

    /// @notice Bounded, strictly sorted ids. Every referenced edge must currently
    /// be active; its exact version is pinned, preventing silent future widening.
    function propose(uint256 sourceNft, uint256 destinationNft, bytes32 salt, uint32 trafficMask,
                     uint8 maxHops, uint16 maxCiphertext, bytes32[] calldata allowedEdges)
        external returns (bytes32 ruleId)
    {
        _validateTraffic(trafficMask, maxCiphertext);
        if (maxHops == 0 || maxHops > 7 || allowedEdges.length == 0 || allowedEdges.length > MAX_ALLOWED_EDGES) {
            revert InvalidParameters();
        }
        ruleId = ruleIdFor(sourceNft, destinationNft, salt);
        _propose(ruleId, sourceNft, destinationNft);
        (,,,,, uint8 sourceRoles) = registry.node(sourceNft);
        (,,,,, uint8 destinationRoles) = registry.node(destinationNft);
        if ((sourceRoles & 1) == 0 || (destinationRoles & 1) == 0) revert InvalidEndpoints();
        Terms storage t = _terms[ruleId];
        // Clear the old bounded set, including removed ids. No stale permissions.
        for (uint256 i; i < t.edges.length; ++i) delete _edgeVersions[ruleId][t.edges[i]];
        delete t.edges;
        bytes32 previous;
        for (uint256 i; i < allowedEdges.length; ++i) {
            bytes32 edgeId = allowedEdges[i];
            if (edgeId <= previous) revert InvalidParameters();
            (,, uint64 version,,,,,, uint8 status) = transit.edge(edgeId);
            if (status != 1) revert InactiveParty();
            _edgeVersions[ruleId][edgeId] = version;
            t.edges.push(edgeId);
            previous = edgeId;
        }
        t.trafficMask = trafficMask;
        t.maxHops = maxHops;
        t.maxCiphertext = maxCiphertext;
    }

    function connection(bytes32 ruleId) external view returns (
        uint256 sourceNft, uint256 destinationNft, uint64 version, uint64 sourceEpoch,
        uint64 destinationEpoch, uint32 trafficMask, uint8 maxHops, uint16 maxCiphertext, uint8 status
    ) {
        Agreement storage a = _agreements[ruleId];
        if (a.version == 0) return (0, 0, 0, 0, 0, 0, 0, 0, 0);
        Terms storage t = _terms[ruleId];
        return (a.source, a.destination, a.version, a.sourceEpoch, a.destinationEpoch,
                t.trafficMask, t.maxHops, t.maxCiphertext, _effective(a) ? 1 : 2);
    }

    function allowsEdge(bytes32 connectionRule, bytes32 edgeRule) external view returns (bool allowed) {
        if (!_effective(_agreements[connectionRule])) return false;
        uint64 pinned = _edgeVersions[connectionRule][edgeRule];
        if (pinned == 0) return false;
        (,, uint64 version,,,,,, uint8 status) = transit.edge(edgeRule);
        return status == 1 && version == pinned;
    }
}
