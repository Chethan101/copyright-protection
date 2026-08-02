// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract CopyrightRegistry {
    struct ImageRecord {
        string ownerId;
        string imageHash;
        string watermarkId;
        uint256 timestamp;
        bool isRegistered;
    }

    // Mapping from imageHash to ImageRecord
    mapping(string => ImageRecord) public registry;

    event ImageRegistered(
        string indexed imageHash,
        string ownerId,
        string watermarkId,
        uint256 timestamp
    );

    function registerImage(
        string memory _imageHash,
        string memory _ownerId,
        string memory _watermarkId
    ) public {
        require(!registry[_imageHash].isRegistered, "Image already registered");

        registry[_imageHash] = ImageRecord({
            ownerId: _ownerId,
            imageHash: _imageHash,
            watermarkId: _watermarkId,
            timestamp: block.timestamp,
            isRegistered: true
        });

        emit ImageRegistered(_imageHash, _ownerId, _watermarkId, block.timestamp);
    }

    function verifyImage(string memory _imageHash) public view returns (
        string memory ownerId,
        string memory watermarkId,
        uint256 timestamp,
        bool isRegistered
    ) {
        ImageRecord memory record = registry[_imageHash];
        return (record.ownerId, record.watermarkId, record.timestamp, record.isRegistered);
    }
}
