// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title VELAddressRegistry
 * @notice Central registry for all VEL contract addresses per network
 * @dev Provides upgrade-safe address management with versioning
 *
 * Features:
 * - Central source of truth for contract addresses
 * - Version tracking for each contract
 * - Role-based access control for updates
 * - Emergency freeze capability
 * - Historical address tracking
 */
contract VELAddressRegistry is AccessControl, Pausable {
    // =============================================================================
    // Roles
    // =============================================================================

    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE");
    bytes32 public constant EMERGENCY_ROLE = keccak256("EMERGENCY_ROLE");

    // =============================================================================
    // Structs
    // =============================================================================

    struct ContractInfo {
        address currentAddress;
        uint256 version;
        uint256 updatedAt;
        bool isActive;
        string description;
    }

    struct AddressUpdate {
        address previousAddress;
        address newAddress;
        uint256 version;
        uint256 timestamp;
        address updatedBy;
    }

    // =============================================================================
    // Events
    // =============================================================================

    event ContractRegistered(
        bytes32 indexed contractId,
        address indexed contractAddress,
        uint256 version,
        string description
    );

    event ContractUpdated(
        bytes32 indexed contractId,
        address indexed previousAddress,
        address indexed newAddress,
        uint256 version
    );

    event ContractDeactivated(bytes32 indexed contractId, address indexed contractAddress);
    event ContractReactivated(bytes32 indexed contractId, address indexed contractAddress);
    event RegistryFrozen(address indexed by);
    event RegistryUnfrozen(address indexed by);

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice Mapping of contract ID to contract info
    mapping(bytes32 => ContractInfo) public contracts;

    /// @notice Mapping of contract ID to update history
    mapping(bytes32 => AddressUpdate[]) public updateHistory;

    /// @notice List of all registered contract IDs
    bytes32[] public contractIds;

    /// @notice Whether the registry is frozen (no updates allowed)
    bool public isFrozen;

    /// @notice Network/chain identifier
    uint256 public immutable chainId;

    /// @notice Registry version
    uint256 public constant REGISTRY_VERSION = 1;

    // =============================================================================
    // Standard Contract IDs
    // =============================================================================

    bytes32 public constant MULTI_DEX_ROUTER = keccak256("MULTI_DEX_ROUTER");
    bytes32 public constant POOLED_VAULT = keccak256("POOLED_VAULT");
    bytes32 public constant CROSSCHAIN_BRIDGE = keccak256("CROSSCHAIN_BRIDGE");
    bytes32 public constant ATOMIC_SWAP_HTLC = keccak256("ATOMIC_SWAP_HTLC");
    bytes32 public constant ANONYMOUS_EXECUTOR = keccak256("ANONYMOUS_EXECUTOR");
    bytes32 public constant TRADE_EXECUTOR = keccak256("TRADE_EXECUTOR");

    // =============================================================================
    // Constructor
    // =============================================================================

    constructor(address admin) {
        require(admin != address(0), "Invalid admin");
        
        chainId = block.chainid;
        
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE, admin);
        _grantRole(UPDATER_ROLE, admin);
        _grantRole(EMERGENCY_ROLE, admin);
    }

    // =============================================================================
    // Modifiers
    // =============================================================================

    modifier notFrozen() {
        require(!isFrozen, "Registry is frozen");
        _;
    }

    // =============================================================================
    // External Functions - Registration
    // =============================================================================

    /**
     * @notice Register a new contract in the registry
     * @param contractId Unique identifier for the contract
     * @param contractAddress Address of the contract
     * @param description Human-readable description
     */
    function registerContract(
        bytes32 contractId,
        address contractAddress,
        string calldata description
    ) external onlyRole(ADMIN_ROLE) notFrozen whenNotPaused {
        require(contractAddress != address(0), "Invalid address");
        require(contracts[contractId].currentAddress == address(0), "Already registered");

        contracts[contractId] = ContractInfo({
            currentAddress: contractAddress,
            version: 1,
            updatedAt: block.timestamp,
            isActive: true,
            description: description
        });

        contractIds.push(contractId);

        // Record in history
        updateHistory[contractId].push(AddressUpdate({
            previousAddress: address(0),
            newAddress: contractAddress,
            version: 1,
            timestamp: block.timestamp,
            updatedBy: msg.sender
        }));

        emit ContractRegistered(contractId, contractAddress, 1, description);
    }

    /**
     * @notice Update an existing contract address
     * @param contractId Contract identifier
     * @param newAddress New contract address
     */
    function updateContract(
        bytes32 contractId,
        address newAddress
    ) external onlyRole(UPDATER_ROLE) notFrozen whenNotPaused {
        require(newAddress != address(0), "Invalid address");
        
        ContractInfo storage info = contracts[contractId];
        require(info.currentAddress != address(0), "Not registered");
        require(info.isActive, "Contract deactivated");
        require(newAddress != info.currentAddress, "Same address");

        address previousAddress = info.currentAddress;
        uint256 newVersion = info.version + 1;

        info.currentAddress = newAddress;
        info.version = newVersion;
        info.updatedAt = block.timestamp;

        // Record in history
        updateHistory[contractId].push(AddressUpdate({
            previousAddress: previousAddress,
            newAddress: newAddress,
            version: newVersion,
            timestamp: block.timestamp,
            updatedBy: msg.sender
        }));

        emit ContractUpdated(contractId, previousAddress, newAddress, newVersion);
    }

    /**
     * @notice Deactivate a contract (marks as inactive, doesn't delete)
     * @param contractId Contract identifier
     */
    function deactivateContract(
        bytes32 contractId
    ) external onlyRole(ADMIN_ROLE) notFrozen {
        ContractInfo storage info = contracts[contractId];
        require(info.currentAddress != address(0), "Not registered");
        require(info.isActive, "Already deactivated");

        info.isActive = false;
        info.updatedAt = block.timestamp;

        emit ContractDeactivated(contractId, info.currentAddress);
    }

    /**
     * @notice Reactivate a deactivated contract
     * @param contractId Contract identifier
     */
    function reactivateContract(
        bytes32 contractId
    ) external onlyRole(ADMIN_ROLE) notFrozen {
        ContractInfo storage info = contracts[contractId];
        require(info.currentAddress != address(0), "Not registered");
        require(!info.isActive, "Already active");

        info.isActive = true;
        info.updatedAt = block.timestamp;

        emit ContractReactivated(contractId, info.currentAddress);
    }

    // =============================================================================
    // External Functions - Emergency
    // =============================================================================

    /**
     * @notice Freeze the registry (prevent all updates)
     * @dev Only callable by emergency role, use with caution
     */
    function freezeRegistry() external onlyRole(EMERGENCY_ROLE) {
        require(!isFrozen, "Already frozen");
        isFrozen = true;
        emit RegistryFrozen(msg.sender);
    }

    /**
     * @notice Unfreeze the registry
     * @dev Only callable by admin role
     */
    function unfreezeRegistry() external onlyRole(ADMIN_ROLE) {
        require(isFrozen, "Not frozen");
        isFrozen = false;
        emit RegistryUnfrozen(msg.sender);
    }

    /**
     * @notice Pause the registry (pausable operations)
     */
    function pause() external onlyRole(EMERGENCY_ROLE) {
        _pause();
    }

    /**
     * @notice Unpause the registry
     */
    function unpause() external onlyRole(ADMIN_ROLE) {
        _unpause();
    }

    // =============================================================================
    // External Functions - View
    // =============================================================================

    /**
     * @notice Get the current address for a contract
     * @param contractId Contract identifier
     * @return Current contract address
     */
    function getAddress(bytes32 contractId) external view returns (address) {
        ContractInfo storage info = contracts[contractId];
        require(info.isActive, "Contract not active");
        return info.currentAddress;
    }

    /**
     * @notice Get the current address with safety check
     * @param contractId Contract identifier
     * @return addr Contract address
     * @return active Whether contract is active
     * @return version Current version
     */
    function getAddressSafe(
        bytes32 contractId
    ) external view returns (address addr, bool active, uint256 version) {
        ContractInfo storage info = contracts[contractId];
        return (info.currentAddress, info.isActive, info.version);
    }

    /**
     * @notice Get full contract info
     * @param contractId Contract identifier
     */
    function getContractInfo(
        bytes32 contractId
    ) external view returns (ContractInfo memory) {
        return contracts[contractId];
    }

    /**
     * @notice Get update history for a contract
     * @param contractId Contract identifier
     */
    function getUpdateHistory(
        bytes32 contractId
    ) external view returns (AddressUpdate[] memory) {
        return updateHistory[contractId];
    }

    /**
     * @notice Get address at a specific version
     * @param contractId Contract identifier
     * @param version Version to look up
     */
    function getAddressAtVersion(
        bytes32 contractId,
        uint256 version
    ) external view returns (address) {
        AddressUpdate[] storage history = updateHistory[contractId];
        
        for (uint256 i = 0; i < history.length; i++) {
            if (history[i].version == version) {
                return history[i].newAddress;
            }
        }
        
        revert("Version not found");
    }

    /**
     * @notice Get count of registered contracts
     */
    function getContractCount() external view returns (uint256) {
        return contractIds.length;
    }

    /**
     * @notice Get all registered contract IDs
     */
    function getAllContractIds() external view returns (bytes32[] memory) {
        return contractIds;
    }

    /**
     * @notice Batch get addresses for multiple contract IDs
     * @param ids Array of contract identifiers
     */
    function batchGetAddresses(
        bytes32[] calldata ids
    ) external view returns (address[] memory addresses) {
        addresses = new address[](ids.length);
        
        for (uint256 i = 0; i < ids.length; i++) {
            ContractInfo storage info = contracts[ids[i]];
            addresses[i] = info.isActive ? info.currentAddress : address(0);
        }
    }

    // =============================================================================
    // External Functions - Standard Contract Getters
    // =============================================================================

    function getMultiDEXRouter() external view returns (address) {
        return contracts[MULTI_DEX_ROUTER].currentAddress;
    }

    function getPooledVault() external view returns (address) {
        return contracts[POOLED_VAULT].currentAddress;
    }

    function getCrosschainBridge() external view returns (address) {
        return contracts[CROSSCHAIN_BRIDGE].currentAddress;
    }

    function getAtomicSwapHTLC() external view returns (address) {
        return contracts[ATOMIC_SWAP_HTLC].currentAddress;
    }

    function getAnonymousExecutor() external view returns (address) {
        return contracts[ANONYMOUS_EXECUTOR].currentAddress;
    }

    function getTradeExecutor() external view returns (address) {
        return contracts[TRADE_EXECUTOR].currentAddress;
    }
}
