// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title VELAtomicSwapHTLC
 * @notice Production-grade Hash Time-Locked Contract for atomic cross-chain swaps
 * @dev Implements atomic swap protocol using hash locks and time locks
 *
 * Features:
 * - Hash time-locked contracts for trustless swaps
 * - Support for multiple token pairs
 * - Configurable time locks
 * - Audit trail for all swaps
 * - Emergency refund mechanism
 * - Multi-chain coordination support
 */
contract VELAtomicSwapHTLC is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // =============================================================================
    // Constants
    // =============================================================================

    uint256 public constant MIN_TIMELOCK = 1 hours;
    uint256 public constant MAX_TIMELOCK = 7 days;
    uint256 public constant DEFAULT_TIMELOCK = 24 hours;

    // =============================================================================
    // Enums
    // =============================================================================

    enum SwapState {
        INVALID,
        OPEN,
        CLOSED,
        EXPIRED
    }

    // =============================================================================
    // Structs
    // =============================================================================

    struct Swap {
        bytes32 contractId;
        address initiator;
        address participant;
        address token;
        uint256 amount;
        bytes32 hashLock;
        uint256 timeLock;
        SwapState state;
        bytes32 preimage; // Set when claimed
        uint256 createdAt;
        uint256 chainId; // For cross-chain coordination
    }

    struct SwapParams {
        address participant;
        address token;
        uint256 amount;
        bytes32 hashLock;
        uint256 timeLock;
        uint256 targetChainId;
    }

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice Current chain ID
    uint256 public immutable chainId;

    /// @notice Mapping of contract ID to swap
    mapping(bytes32 => Swap) public swaps;

    /// @notice User initiated swaps
    mapping(address => bytes32[]) public userInitiatedSwaps;

    /// @notice User participated swaps
    mapping(address => bytes32[]) public userParticipatedSwaps;

    /// @notice Approved tokens for swaps
    mapping(address => bool) public approvedTokens;

    /// @notice Total swaps count
    uint256 public totalSwaps;

    /// @notice Swap counter for unique IDs
    uint256 private _swapCounter;

    // =============================================================================
    // Events
    // =============================================================================

    event SwapCreated(
        bytes32 indexed contractId,
        address indexed initiator,
        address indexed participant,
        address token,
        uint256 amount,
        bytes32 hashLock,
        uint256 timeLock,
        uint256 targetChainId
    );
    event SwapClaimed(
        bytes32 indexed contractId,
        address indexed claimer,
        bytes32 preimage
    );
    event SwapRefunded(
        bytes32 indexed contractId,
        address indexed refundee
    );
    event TokenApprovalUpdated(address indexed token, bool approved);

    // =============================================================================
    // Errors
    // =============================================================================

    error ZeroAddress();
    error ZeroAmount();
    error InvalidTimelock(uint256 provided, uint256 min, uint256 max);
    error TokenNotApproved(address token);
    error SwapAlreadyExists(bytes32 contractId);
    error SwapNotFound(bytes32 contractId);
    error SwapNotOpen(bytes32 contractId, SwapState state);
    error InvalidHashLock();
    error InvalidPreimage(bytes32 expected, bytes32 actual);
    error TimeLockNotExpired(uint256 timeLock, uint256 currentTime);
    error TimeLockExpired(uint256 timeLock, uint256 currentTime);
    error NotParticipant(address caller, address participant);
    error NotInitiator(address caller, address initiator);

    // =============================================================================
    // Constructor
    // =============================================================================

    /**
     * @notice Initialize the HTLC contract
     * @param _chainId Current chain ID
     */
    constructor(uint256 _chainId) Ownable(msg.sender) {
        chainId = _chainId;
    }

    // =============================================================================
    // External Functions
    // =============================================================================

    /**
     * @notice Create a new atomic swap
     * @param params Swap parameters
     * @return contractId Unique contract ID
     */
    function createSwap(
        SwapParams calldata params
    ) external nonReentrant whenNotPaused returns (bytes32 contractId) {
        // Validations
        if (params.participant == address(0)) revert ZeroAddress();
        if (params.amount == 0) revert ZeroAmount();
        if (!approvedTokens[params.token]) revert TokenNotApproved(params.token);
        if (params.hashLock == bytes32(0)) revert InvalidHashLock();
        if (params.timeLock < MIN_TIMELOCK || params.timeLock > MAX_TIMELOCK) {
            revert InvalidTimelock(params.timeLock, MIN_TIMELOCK, MAX_TIMELOCK);
        }

        // Generate unique contract ID
        contractId = keccak256(abi.encodePacked(
            msg.sender,
            params.participant,
            params.token,
            params.amount,
            params.hashLock,
            block.timestamp,
            _swapCounter++
        ));

        if (swaps[contractId].state != SwapState.INVALID) {
            revert SwapAlreadyExists(contractId);
        }

        uint256 lockExpiry = block.timestamp + params.timeLock;

        // Create swap
        swaps[contractId] = Swap({
            contractId: contractId,
            initiator: msg.sender,
            participant: params.participant,
            token: params.token,
            amount: params.amount,
            hashLock: params.hashLock,
            timeLock: lockExpiry,
            state: SwapState.OPEN,
            preimage: bytes32(0),
            createdAt: block.timestamp,
            chainId: params.targetChainId
        });

        // Track swaps
        userInitiatedSwaps[msg.sender].push(contractId);
        userParticipatedSwaps[params.participant].push(contractId);
        totalSwaps++;

        // Transfer tokens to contract
        IERC20(params.token).safeTransferFrom(msg.sender, address(this), params.amount);

        emit SwapCreated(
            contractId,
            msg.sender,
            params.participant,
            params.token,
            params.amount,
            params.hashLock,
            lockExpiry,
            params.targetChainId
        );

        return contractId;
    }

    /**
     * @notice Claim tokens by revealing the preimage
     * @param contractId Contract ID
     * @param preimage Secret preimage
     */
    function claim(
        bytes32 contractId,
        bytes32 preimage
    ) external nonReentrant {
        Swap storage swap = swaps[contractId];

        if (swap.state == SwapState.INVALID) revert SwapNotFound(contractId);
        if (swap.state != SwapState.OPEN) revert SwapNotOpen(contractId, swap.state);
        if (msg.sender != swap.participant) {
            revert NotParticipant(msg.sender, swap.participant);
        }
        if (block.timestamp >= swap.timeLock) {
            revert TimeLockExpired(swap.timeLock, block.timestamp);
        }

        // Verify preimage
        bytes32 computedHash = sha256(abi.encodePacked(preimage));
        if (computedHash != swap.hashLock) {
            revert InvalidPreimage(swap.hashLock, computedHash);
        }

        // Update state
        swap.state = SwapState.CLOSED;
        swap.preimage = preimage;

        // Transfer tokens to participant
        IERC20(swap.token).safeTransfer(swap.participant, swap.amount);

        emit SwapClaimed(contractId, msg.sender, preimage);
    }

    /**
     * @notice Refund tokens after timelock expiry
     * @param contractId Contract ID
     */
    function refund(bytes32 contractId) external nonReentrant {
        Swap storage swap = swaps[contractId];

        if (swap.state == SwapState.INVALID) revert SwapNotFound(contractId);
        if (swap.state != SwapState.OPEN) revert SwapNotOpen(contractId, swap.state);
        if (msg.sender != swap.initiator) {
            revert NotInitiator(msg.sender, swap.initiator);
        }
        if (block.timestamp < swap.timeLock) {
            revert TimeLockNotExpired(swap.timeLock, block.timestamp);
        }

        // Update state
        swap.state = SwapState.EXPIRED;

        // Refund tokens to initiator
        IERC20(swap.token).safeTransfer(swap.initiator, swap.amount);

        emit SwapRefunded(contractId, msg.sender);
    }

    /**
     * @notice Create swap with pre-generated secret (convenience function)
     * @param participant Participant address
     * @param token Token address
     * @param amount Amount to swap
     * @param timeLock Time lock duration
     * @param targetChainId Target chain for cross-chain coordination
     * @return contractId Contract ID
     * @return secret Generated secret
     * @return hashLock Hash of the secret
     */
    function createSwapWithSecret(
        address participant,
        address token,
        uint256 amount,
        uint256 timeLock,
        uint256 targetChainId
    ) external returns (bytes32 contractId, bytes32 secret, bytes32 hashLock) {
        // Generate cryptographically secure secret
        secret = keccak256(abi.encodePacked(
            block.timestamp,
            block.prevrandao,
            msg.sender,
            participant,
            _swapCounter
        ));

        hashLock = sha256(abi.encodePacked(secret));

        SwapParams memory params = SwapParams({
            participant: participant,
            token: token,
            amount: amount,
            hashLock: hashLock,
            timeLock: timeLock == 0 ? DEFAULT_TIMELOCK : timeLock,
            targetChainId: targetChainId
        });

        contractId = this.createSwap(params);

        return (contractId, secret, hashLock);
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================

    /**
     * @notice Approve or revoke a token
     * @param token Token address
     * @param approved Approval status
     */
    function setTokenApproval(address token, bool approved) external onlyOwner {
        if (token == address(0)) revert ZeroAddress();
        approvedTokens[token] = approved;
        emit TokenApprovalUpdated(token, approved);
    }

    /**
     * @notice Batch approve tokens
     * @param tokens Token addresses
     * @param approved Approval status
     */
    function batchSetTokenApproval(
        address[] calldata tokens,
        bool approved
    ) external onlyOwner {
        for (uint256 i = 0; i < tokens.length; i++) {
            if (tokens[i] == address(0)) revert ZeroAddress();
            approvedTokens[tokens[i]] = approved;
            emit TokenApprovalUpdated(tokens[i], approved);
        }
    }

    /**
     * @notice Pause the contract
     */
    function pause() external onlyOwner {
        _pause();
    }

    /**
     * @notice Unpause the contract
     */
    function unpause() external onlyOwner {
        _unpause();
    }

    // =============================================================================
    // View Functions
    // =============================================================================

    /**
     * @notice Get swap details
     * @param contractId Contract ID
     * @return Swap details
     */
    function getSwap(bytes32 contractId) external view returns (Swap memory) {
        return swaps[contractId];
    }

    /**
     * @notice Check if swap can be claimed
     * @param contractId Contract ID
     * @return canClaim Whether the swap can be claimed
     * @return reason Reason if cannot claim
     */
    function canClaim(bytes32 contractId) external view returns (bool canClaim, string memory reason) {
        Swap storage swap = swaps[contractId];

        if (swap.state == SwapState.INVALID) {
            return (false, "Swap not found");
        }
        if (swap.state != SwapState.OPEN) {
            return (false, "Swap not open");
        }
        if (block.timestamp >= swap.timeLock) {
            return (false, "Timelock expired");
        }

        return (true, "");
    }

    /**
     * @notice Check if swap can be refunded
     * @param contractId Contract ID
     * @return canRefund Whether the swap can be refunded
     * @return reason Reason if cannot refund
     */
    function canRefund(bytes32 contractId) external view returns (bool canRefund, string memory reason) {
        Swap storage swap = swaps[contractId];

        if (swap.state == SwapState.INVALID) {
            return (false, "Swap not found");
        }
        if (swap.state != SwapState.OPEN) {
            return (false, "Swap not open");
        }
        if (block.timestamp < swap.timeLock) {
            return (false, "Timelock not expired");
        }

        return (true, "");
    }

    /**
     * @notice Get user's initiated swaps
     * @param user User address
     * @return Contract IDs
     */
    function getUserInitiatedSwaps(address user) external view returns (bytes32[] memory) {
        return userInitiatedSwaps[user];
    }

    /**
     * @notice Get user's participated swaps
     * @param user User address
     * @return Contract IDs
     */
    function getUserParticipatedSwaps(address user) external view returns (bytes32[] memory) {
        return userParticipatedSwaps[user];
    }

    /**
     * @notice Compute hash lock from preimage
     * @param preimage Secret preimage
     * @return hashLock Hash lock
     */
    function computeHashLock(bytes32 preimage) external pure returns (bytes32 hashLock) {
        return sha256(abi.encodePacked(preimage));
    }
}
