// SPDX-License-Identifier: MIT
pragma solidity 0.8.38;

// Test-only contracts; excluded from compilation evidence and any operational
// release. These deliberately expose state injection for overflow regression.
import {NodeRegistry} from "../src/NodeRegistry.sol";
import {TransitPolicy} from "../src/TransitPolicy.sol";
import {ConnectionPolicy} from "../src/ConnectionPolicy.sol";
import {IERC721Receiver} from "@openzeppelin/contracts/token/ERC721/IERC721Receiver.sol";

contract EpochHarness is NodeRegistry {
    function forceEpoch(uint256 token, uint64 epoch) external { _nodes[token].keyEpoch = epoch; }
}

contract TransitHarness is TransitPolicy {
    constructor(address r) TransitPolicy(r) {}
    function forceVersion(bytes32 rule, uint64 version) external { _agreements[rule].version = version; }
}

contract ConnectionHarness is ConnectionPolicy {
    constructor(address r, address t) ConnectionPolicy(r, t) {}
    function forceVersion(bytes32 rule, uint64 version) external { _agreements[rule].version = version; }
}

contract ObservingReceiver is IERC721Receiver {
    NodeRegistry public immutable registry;
    uint8 public observedStatus;
    uint64 public observedEpoch;
    bool public observedKeysZero;
    bool public reactivate;
    constructor(address r) { registry = NodeRegistry(r); }
    function setReactivate(bool enabled) external { reactivate = enabled; }
    function registerNode(bytes32 s, bytes32 e, uint8 roles) external returns (uint256) {
        return registry.register(s,e,roles);
    }
    function onERC721Received(address, address, uint256 token, bytes calldata) external returns (bytes4) {
        require(msg.sender == address(registry));
        (address owner, uint64 epoch, bytes32 s, bytes32 e, uint8 status,) = registry.node(token);
        require(owner == address(this));
        observedStatus = status;
        observedEpoch = epoch;
        observedKeysZero = s == 0 && e == 0;
        if (reactivate) registry.setKeys(token, bytes32(uint256(501)), bytes32(uint256(502)), 1);
        return IERC721Receiver.onERC721Received.selector;
    }
}

contract RejectingReceiver is IERC721Receiver {
    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) { return 0; }
}
