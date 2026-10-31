// SPDX-License-Identifier: MIT
pragma solidity 0.8.38;

/// @notice The frozen BCP 0.2 read interface. No chain/finality assertion.
interface INodeRegistry {
    function ownerOf(uint256 tokenId) external view returns (address owner);
    function node(uint256 tokenId) external view returns (
        address owner, uint64 keyEpoch, bytes32 signingKey,
        bytes32 encryptionKey, uint8 status, uint8 roles
    );
}
