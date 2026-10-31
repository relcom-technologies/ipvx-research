// SPDX-License-Identifier: MIT
pragma solidity 0.8.38;

import {BilateralPolicy} from "./BilateralPolicy.sol";

contract TransitPolicy is BilateralPolicy {
    bytes32 private constant RULE_DOMAIN = keccak256("IPvX-BCP/0.2/transit-rule");
    struct Terms { uint32 cost; uint16 maxCiphertext; uint32 trafficMask; }
    mapping(bytes32 => Terms) internal _terms;

    constructor(address nodeRegistry) BilateralPolicy(nodeRegistry) {}

    function ruleIdFor(uint256 fromNft, uint256 toNft, bytes32 salt) public view returns (bytes32) {
        return keccak256(abi.encode(RULE_DOMAIN, block.chainid, address(this), fromNft, toNft, salt));
    }

    function propose(uint256 fromNft, uint256 toNft, bytes32 salt, uint32 cost,
                     uint16 maxCiphertext, uint32 trafficMask) external returns (bytes32 ruleId) {
        _validateTraffic(trafficMask, maxCiphertext);
        ruleId = ruleIdFor(fromNft, toNft, salt);
        _propose(ruleId, fromNft, toNft);
        _terms[ruleId] = Terms(cost, maxCiphertext, trafficMask);
    }

    function edge(bytes32 ruleId) external view returns (
        uint256 fromNft, uint256 toNft, uint64 version, uint64 fromEpoch, uint64 toEpoch,
        uint32 cost, uint16 maxCiphertext, uint32 trafficMask, uint8 status
    ) {
        Agreement storage a = _agreements[ruleId];
        if (a.version == 0) return (0, 0, 0, 0, 0, 0, 0, 0, 0);
        Terms storage t = _terms[ruleId];
        return (a.source, a.destination, a.version, a.sourceEpoch, a.destinationEpoch,
                t.cost, t.maxCiphertext, t.trafficMask, _effective(a) ? 1 : 2);
    }
}
