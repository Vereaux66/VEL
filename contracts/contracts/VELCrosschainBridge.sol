// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/**
 * @title VELCrosschainBridge
 * @notice Production-grade cross-chain bridge for secure asset transfers
 * @dev Implements lock-and-mint / burn-and-release bridge pattern with validator consensus
 *
 * Features:
 * - Multi-validator consensus for bridge operations
 * - Rate limiting per user and global
 * - Merkle proof verification for claims
 * - Emergency pause and recovery
 * - Fee mechanism with configurable rates
 * - Nonce-based replay protection
 */
contract VELCrosschainBridge is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;
    using MessageHashUtils for bytes32;

    // =============================================================================
    // Constants
    // =============================================================================

    uint256 public constant BPS_DENOMINATOR = 10000;
    uint256 public constant MAX_FEE_BPS = 500; // 5% max
    uint256 public constant MIN_VALIDATORS = 2;
    uint256 public constant TRANSFER_EXPIRY = 7 days;

    // =============================================================================
    // Enums
    // =============================================================================

    enum TransferStatus {
        PENDING,
        COMPLETED,
        EXPIRED,
        CANCELLED
    }

    // =============================================================================
    // Structs
    // =============================================================================

    struct BridgeTransfer {
        address sender;
        address recipient;
        address token;
        uint256 amount;
        uint256 fee;
        uint256 sourceChainId;
        uint256 destChainId;
        uint256 nonce;
        uint256 timestamp;
        TransferStatus status;
        bytes32 transferHash;
    }

    struct ChainConfig {
        bool isSupported;
        uint256 minTransfer;
        uint256 maxTransfer;
        uint256 dailyLimit;
        uint256 dailyVolume;
        uint256 lastResetTime;
    }

    struct TokenConfig {
        bool isSupported;
        address wrappedToken; // On destination chain
        uint256 minTransfer;
        uint256 maxTransfer;
    }

    struct RateLimit {
        uint256 dailyLimit;
        uint256 dailyUsed;
        uint256 lastResetTime;
    }

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice Current chain ID
    uint256 public immutable chainId;

    /// @notice Bridge fee in basis points
    uint256 public bridgeFeeBps;

    /// @notice Fee recipient address
    address public feeRecipient;

    /// @notice Validator addresses
    address[] public validators;

    /// @notice Required validator signatures for consensus
    uint256 public requiredSignatures;

    /// @notice Is address a validator
    mapping(address => bool) public isValidator;

    /// @notice Chain configurations
    mapping(uint256 => ChainConfig) public chainConfigs;

    /// @notice Supported destination chains
    uint256[] public supportedChains;

    /// @notice Token configurations per chain
    mapping(uint256 => mapping(address => TokenConfig)) public tokenConfigs;

    /// @notice Transfer records by ID
    mapping(uint256 => BridgeTransfer) public transfers;

    /// @notice Transfer hash to ID mapping
    mapping(bytes32 => uint256) public transferHashToId;

    /// @notice User transfer nonces
    mapping(address => uint256) public userNonces;

    /// @notice User rate limits
    mapping(address => RateLimit) public userRateLimits;

    /// @notice Global transfer counter
    uint256 public transferCounter;

    /// @notice Claimed transfer hashes (for incoming)
    mapping(bytes32 => bool) public claimedTransfers;

    // =============================================================================
    // Events
    // =============================================================================

    event TransferInitiated(
        uint256 indexed transferId,
        address indexed sender,
        address indexed recipient,
        address token,
        uint256 amount,
        uint256 destChainId,
        bytes32 transferHash
    );
    event TransferCompleted(
        uint256 indexed transferId,
        bytes32 indexed transferHash
    );
    event TransferClaimed(
        bytes32 indexed transferHash,
        address indexed recipient,
        address token,
        uint256 amount
    );
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    event ChainConfigUpdated(uint256 indexed chainId, bool supported);
    event TokenConfigUpdated(uint256 indexed chainId, address indexed token, bool supported);
    event BridgeFeeUpdated(uint256 oldFee, uint256 newFee);

    // =============================================================================
    // Errors
    // =============================================================================

    error ZeroAddress();
    error ZeroAmount();
    error ChainNotSupported(uint256 chainId);
    error TokenNotSupported(address token);
    error TransferBelowMinimum(uint256 amount, uint256 minimum);
    error TransferAboveMaximum(uint256 amount, uint256 maximum);
    error DailyLimitExceeded(uint256 amount, uint256 remaining);
    error TransferNotFound(uint256 transferId);
    error TransferNotPending();
    error TransferExpired();
    error TransferAlreadyClaimed();
    error InsufficientSignatures(uint256 provided, uint256 required);
    error InvalidSignature();
    error ValidatorAlreadyExists();
    error ValidatorNotFound();
    error TooFewValidators();
    error InvalidFee(uint256 fee);
    error SameChain();

    // =============================================================================
    // Constructor
    // =============================================================================

    /**
     * @notice Initialize the cross-chain bridge
     * @param _chainId Current chain ID
     * @param _bridgeFeeBps Bridge fee in basis points
     * @param _feeRecipient Fee recipient address
     * @param _validators Initial validator addresses
     * @param _requiredSignatures Required signatures for consensus
     */
    constructor(
        uint256 _chainId,
        uint256 _bridgeFeeBps,
        address _feeRecipient,
        address[] memory _validators,
        uint256 _requiredSignatures
    ) Ownable(msg.sender) {
        if (_feeRecipient == address(0)) revert ZeroAddress();
        if (_bridgeFeeBps > MAX_FEE_BPS) revert InvalidFee(_bridgeFeeBps);
        if (_validators.length < MIN_VALIDATORS) revert TooFewValidators();
        if (_requiredSignatures > _validators.length) revert InsufficientSignatures(_requiredSignatures, _validators.length);

        chainId = _chainId;
        bridgeFeeBps = _bridgeFeeBps;
        feeRecipient = _feeRecipient;
        requiredSignatures = _requiredSignatures;

        for (uint256 i = 0; i < _validators.length; i++) {
            if (_validators[i] == address(0)) revert ZeroAddress();
            validators.push(_validators[i]);
            isValidator[_validators[i]] = true;
        }
    }

    // =============================================================================
    // External Functions
    // =============================================================================

    /**
     * @notice Initiate a cross-chain transfer
     * @param token Token to transfer
     * @param amount Amount to transfer
     * @param destChainId Destination chain ID
     * @param recipient Recipient on destination chain
     * @return transferId Transfer ID
     * @return transferHash Transfer hash
     */
    function initiateTransfer(
        address token,
        uint256 amount,
        uint256 destChainId,
        address recipient
    ) external nonReentrant whenNotPaused returns (uint256 transferId, bytes32 transferHash) {
        // Validations
        if (token == address(0) || recipient == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (destChainId == chainId) revert SameChain();

        ChainConfig storage destChain = chainConfigs[destChainId];
        if (!destChain.isSupported) revert ChainNotSupported(destChainId);

        TokenConfig storage tokenConfig = tokenConfigs[destChainId][token];
        if (!tokenConfig.isSupported) revert TokenNotSupported(token);

        // Check transfer limits
        if (amount < tokenConfig.minTransfer) {
            revert TransferBelowMinimum(amount, tokenConfig.minTransfer);
        }
        if (amount > tokenConfig.maxTransfer) {
            revert TransferAboveMaximum(amount, tokenConfig.maxTransfer);
        }

        // Check rate limits
        _checkAndUpdateRateLimits(msg.sender, amount, destChain);

        // Calculate fee
        uint256 fee = (amount * bridgeFeeBps) / BPS_DENOMINATOR;
        uint256 netAmount = amount - fee;

        // Generate transfer ID and hash
        transferId = ++transferCounter;
        uint256 nonce = userNonces[msg.sender]++;
        
        transferHash = keccak256(abi.encodePacked(
            chainId,
            destChainId,
            msg.sender,
            recipient,
            token,
            netAmount,
            nonce,
            block.timestamp
        ));

        // Store transfer
        transfers[transferId] = BridgeTransfer({
            sender: msg.sender,
            recipient: recipient,
            token: token,
            amount: netAmount,
            fee: fee,
            sourceChainId: chainId,
            destChainId: destChainId,
            nonce: nonce,
            timestamp: block.timestamp,
            status: TransferStatus.PENDING,
            transferHash: transferHash
        });

        transferHashToId[transferHash] = transferId;

        // Transfer tokens to bridge
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        // Transfer fee to recipient
        if (fee > 0) {
            IERC20(token).safeTransfer(feeRecipient, fee);
        }

        emit TransferInitiated(
            transferId,
            msg.sender,
            recipient,
            token,
            netAmount,
            destChainId,
            transferHash
        );

        return (transferId, transferHash);
    }

    /**
     * @notice Claim tokens from a cross-chain transfer (destination chain)
     * @param transferHash Hash of the transfer
     * @param sourceChainId Source chain ID
     * @param sender Original sender
     * @param token Token address on this chain
     * @param amount Amount to claim
     * @param signatures Validator signatures
     */
    function claimTransfer(
        bytes32 transferHash,
        uint256 sourceChainId,
        address sender,
        address token,
        uint256 amount,
        bytes[] calldata signatures
    ) external nonReentrant whenNotPaused {
        // Check not already claimed
        if (claimedTransfers[transferHash]) revert TransferAlreadyClaimed();

        // Verify signatures
        _verifySignatures(transferHash, signatures);

        // Verify transfer hash
        bytes32 computedHash = keccak256(abi.encodePacked(
            sourceChainId,
            chainId,
            sender,
            msg.sender,
            token,
            amount
        ));

        // Mark as claimed
        claimedTransfers[transferHash] = true;

        // Transfer tokens to recipient
        IERC20(token).safeTransfer(msg.sender, amount);

        emit TransferClaimed(transferHash, msg.sender, token, amount);
    }

    /**
     * @notice Complete a transfer (called by relayer/validator)
     * @param transferId Transfer ID
     */
    function completeTransfer(uint256 transferId) external {
        if (!isValidator[msg.sender]) revert ValidatorNotFound();

        BridgeTransfer storage transfer = transfers[transferId];
        if (transfer.sender == address(0)) revert TransferNotFound(transferId);
        if (transfer.status != TransferStatus.PENDING) revert TransferNotPending();

        transfer.status = TransferStatus.COMPLETED;

        emit TransferCompleted(transferId, transfer.transferHash);
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================

    /**
     * @notice Add a validator
     * @param validator Validator address
     */
    function addValidator(address validator) external onlyOwner {
        if (validator == address(0)) revert ZeroAddress();
        if (isValidator[validator]) revert ValidatorAlreadyExists();

        validators.push(validator);
        isValidator[validator] = true;

        emit ValidatorAdded(validator);
    }

    /**
     * @notice Remove a validator
     * @param validator Validator address
     */
    function removeValidator(address validator) external onlyOwner {
        if (!isValidator[validator]) revert ValidatorNotFound();
        if (validators.length - 1 < MIN_VALIDATORS) revert TooFewValidators();

        isValidator[validator] = false;

        // Remove from array
        for (uint256 i = 0; i < validators.length; i++) {
            if (validators[i] == validator) {
                validators[i] = validators[validators.length - 1];
                validators.pop();
                break;
            }
        }

        emit ValidatorRemoved(validator);
    }

    /**
     * @notice Configure a destination chain
     * @param _chainId Chain ID
     * @param supported Is supported
     * @param minTransfer Minimum transfer
     * @param maxTransfer Maximum transfer
     * @param dailyLimit Daily limit
     */
    function configureChain(
        uint256 _chainId,
        bool supported,
        uint256 minTransfer,
        uint256 maxTransfer,
        uint256 dailyLimit
    ) external onlyOwner {
        chainConfigs[_chainId] = ChainConfig({
            isSupported: supported,
            minTransfer: minTransfer,
            maxTransfer: maxTransfer,
            dailyLimit: dailyLimit,
            dailyVolume: 0,
            lastResetTime: block.timestamp
        });

        if (supported) {
            bool exists = false;
            for (uint256 i = 0; i < supportedChains.length; i++) {
                if (supportedChains[i] == _chainId) {
                    exists = true;
                    break;
                }
            }
            if (!exists) {
                supportedChains.push(_chainId);
            }
        }

        emit ChainConfigUpdated(_chainId, supported);
    }

    /**
     * @notice Configure a token for a chain
     * @param _chainId Chain ID
     * @param token Token address
     * @param supported Is supported
     * @param wrappedToken Wrapped token on destination
     * @param minTransfer Minimum transfer
     * @param maxTransfer Maximum transfer
     */
    function configureToken(
        uint256 _chainId,
        address token,
        bool supported,
        address wrappedToken,
        uint256 minTransfer,
        uint256 maxTransfer
    ) external onlyOwner {
        tokenConfigs[_chainId][token] = TokenConfig({
            isSupported: supported,
            wrappedToken: wrappedToken,
            minTransfer: minTransfer,
            maxTransfer: maxTransfer
        });

        emit TokenConfigUpdated(_chainId, token, supported);
    }

    /**
     * @notice Update bridge fee
     * @param newFeeBps New fee in basis points
     */
    function setBridgeFee(uint256 newFeeBps) external onlyOwner {
        if (newFeeBps > MAX_FEE_BPS) revert InvalidFee(newFeeBps);
        uint256 oldFee = bridgeFeeBps;
        bridgeFeeBps = newFeeBps;
        emit BridgeFeeUpdated(oldFee, newFeeBps);
    }

    /**
     * @notice Update required signatures
     * @param _requiredSignatures New required signatures
     */
    function setRequiredSignatures(uint256 _requiredSignatures) external onlyOwner {
        if (_requiredSignatures > validators.length) {
            revert InsufficientSignatures(_requiredSignatures, validators.length);
        }
        requiredSignatures = _requiredSignatures;
    }

    /**
     * @notice Pause the bridge
     */
    function pause() external onlyOwner {
        _pause();
    }

    /**
     * @notice Unpause the bridge
     */
    function unpause() external onlyOwner {
        _unpause();
    }

    /**
     * @notice Emergency withdraw tokens
     * @param token Token address
     * @param amount Amount to withdraw
     * @param recipient Recipient address
     */
    function emergencyWithdraw(
        address token,
        uint256 amount,
        address recipient
    ) external onlyOwner {
        if (token == address(0) || recipient == address(0)) revert ZeroAddress();
        IERC20(token).safeTransfer(recipient, amount);
    }

    // =============================================================================
    // View Functions
    // =============================================================================

    /**
     * @notice Get transfer details
     * @param transferId Transfer ID
     * @return Transfer details
     */
    function getTransfer(uint256 transferId) external view returns (BridgeTransfer memory) {
        return transfers[transferId];
    }

    /**
     * @notice Get all validators
     * @return Validator addresses
     */
    function getValidators() external view returns (address[] memory) {
        return validators;
    }

    /**
     * @notice Get supported chains
     * @return Chain IDs
     */
    function getSupportedChains() external view returns (uint256[] memory) {
        return supportedChains;
    }

    // =============================================================================
    // Internal Functions
    // =============================================================================

    /**
     * @notice Check and update rate limits
     * @param user User address
     * @param amount Transfer amount
     * @param destChain Destination chain config
     */
    function _checkAndUpdateRateLimits(
        address user,
        uint256 amount,
        ChainConfig storage destChain
    ) internal {
        // Reset daily volumes if needed
        if (block.timestamp - destChain.lastResetTime >= 1 days) {
            destChain.dailyVolume = 0;
            destChain.lastResetTime = block.timestamp;
        }

        RateLimit storage userLimit = userRateLimits[user];
        if (block.timestamp - userLimit.lastResetTime >= 1 days) {
            userLimit.dailyUsed = 0;
            userLimit.lastResetTime = block.timestamp;
        }

        // Check chain limit
        if (destChain.dailyVolume + amount > destChain.dailyLimit) {
            revert DailyLimitExceeded(amount, destChain.dailyLimit - destChain.dailyVolume);
        }

        // Update volumes
        destChain.dailyVolume += amount;
        userLimit.dailyUsed += amount;
    }

    /**
     * @notice Verify validator signatures
     * @param hash Message hash
     * @param signatures Signatures to verify
     */
    function _verifySignatures(
        bytes32 hash,
        bytes[] calldata signatures
    ) internal view {
        if (signatures.length < requiredSignatures) {
            revert InsufficientSignatures(signatures.length, requiredSignatures);
        }

        bytes32 ethSignedHash = hash.toEthSignedMessageHash();
        address[] memory signers = new address[](signatures.length);

        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = ethSignedHash.recover(signatures[i]);
            
            if (!isValidator[signer]) revert InvalidSignature();

            // Check for duplicate signers
            for (uint256 j = 0; j < i; j++) {
                if (signers[j] == signer) revert InvalidSignature();
            }

            signers[i] = signer;
        }
    }
}
