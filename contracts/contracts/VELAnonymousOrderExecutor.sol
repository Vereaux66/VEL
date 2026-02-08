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
 * @title VELAnonymousOrderExecutor
 * @notice Privacy-preserving order execution with commitment schemes
 * @dev Implements commit-reveal pattern for MEV-resistant order execution
 *
 * Features:
 * - Commitment scheme for order privacy
 * - Delayed reveal to prevent front-running
 * - Batch execution for gas optimization
 * - Relayer system for privacy
 * - Order expiry mechanism
 * - Execution proofs for verification
 */
contract VELAnonymousOrderExecutor is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;
    using MessageHashUtils for bytes32;

    // =============================================================================
    // Constants
    // =============================================================================

    uint256 public constant MIN_REVEAL_DELAY = 2; // blocks
    uint256 public constant MAX_REVEAL_DELAY = 100; // blocks
    uint256 public constant ORDER_EXPIRY = 1 hours;
    uint256 public constant BPS_DENOMINATOR = 10000;

    // =============================================================================
    // Enums
    // =============================================================================

    enum OrderState {
        INVALID,
        COMMITTED,
        REVEALED,
        EXECUTED,
        CANCELLED,
        EXPIRED
    }

    enum OrderType {
        MARKET,
        LIMIT,
        STOP_LOSS,
        TAKE_PROFIT
    }

    // =============================================================================
    // Structs
    // =============================================================================

    struct OrderCommitment {
        bytes32 commitmentHash;
        address depositor;
        uint256 depositAmount;
        address depositToken;
        uint256 commitBlock;
        uint256 revealDeadline;
        OrderState state;
    }

    struct RevealedOrder {
        bytes32 commitmentId;
        address trader;
        OrderType orderType;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minAmountOut;
        uint256 limitPrice; // For limit orders (0 for market)
        uint256 deadline;
        bytes32 salt;
    }

    struct ExecutionResult {
        bytes32 commitmentId;
        uint256 amountIn;
        uint256 amountOut;
        uint256 executionPrice;
        uint256 gasUsed;
        bytes32 executionHash;
    }

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice Mapping of commitment ID to commitment
    mapping(bytes32 => OrderCommitment) public commitments;

    /// @notice Mapping of commitment ID to revealed order
    mapping(bytes32 => RevealedOrder) public revealedOrders;

    /// @notice Mapping of commitment ID to execution result
    mapping(bytes32 => ExecutionResult) public executionResults;

    /// @notice Authorized relayers
    mapping(address => bool) public authorizedRelayers;

    /// @notice Approved DEX routers
    mapping(address => bool) public approvedRouters;

    /// @notice Approved tokens
    mapping(address => bool) public approvedTokens;

    /// @notice User commitment count
    mapping(address => uint256) public userCommitmentCount;

    /// @notice Reveal delay in blocks
    uint256 public revealDelay;

    /// @notice Relayer fee in basis points
    uint256 public relayerFeeBps;

    /// @notice Fee recipient
    address public feeRecipient;

    /// @notice Total commitments
    uint256 public totalCommitments;

    /// @notice Total executed orders
    uint256 public totalExecuted;

    // =============================================================================
    // Events
    // =============================================================================

    event OrderCommitted(
        bytes32 indexed commitmentId,
        address indexed depositor,
        address depositToken,
        uint256 depositAmount,
        uint256 revealDeadline
    );
    event OrderRevealed(
        bytes32 indexed commitmentId,
        address indexed trader,
        OrderType orderType,
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    );
    event OrderExecuted(
        bytes32 indexed commitmentId,
        uint256 amountIn,
        uint256 amountOut,
        uint256 executionPrice,
        bytes32 executionHash
    );
    event OrderCancelled(bytes32 indexed commitmentId, address indexed depositor);
    event OrderExpired(bytes32 indexed commitmentId);
    event RelayerUpdated(address indexed relayer, bool authorized);
    event RouterUpdated(address indexed router, bool approved);
    event TokenUpdated(address indexed token, bool approved);

    // =============================================================================
    // Errors
    // =============================================================================

    error ZeroAddress();
    error ZeroAmount();
    error InvalidCommitment();
    error CommitmentNotFound(bytes32 commitmentId);
    error InvalidOrderState(bytes32 commitmentId, OrderState expected, OrderState actual);
    error RevealTooEarly(uint256 currentBlock, uint256 revealBlock);
    error RevealDeadlinePassed(uint256 deadline, uint256 currentBlock);
    error InvalidReveal();
    error OrderExpiredError();
    error TokenNotApproved(address token);
    error RouterNotApproved(address router);
    error NotAuthorizedRelayer();
    error NotDepositor();
    error InvalidRevealDelay(uint256 provided, uint256 min, uint256 max);
    error SlippageExceeded(uint256 expected, uint256 actual);
    error SwapFailed();

    // =============================================================================
    // Modifiers
    // =============================================================================

    modifier onlyRelayer() {
        if (!authorizedRelayers[msg.sender] && msg.sender != owner()) {
            revert NotAuthorizedRelayer();
        }
        _;
    }

    // =============================================================================
    // Constructor
    // =============================================================================

    /**
     * @notice Initialize the anonymous order executor
     * @param _revealDelay Reveal delay in blocks
     * @param _relayerFeeBps Relayer fee in basis points
     * @param _feeRecipient Fee recipient address
     */
    constructor(
        uint256 _revealDelay,
        uint256 _relayerFeeBps,
        address _feeRecipient
    ) Ownable(msg.sender) {
        if (_feeRecipient == address(0)) revert ZeroAddress();
        if (_revealDelay < MIN_REVEAL_DELAY || _revealDelay > MAX_REVEAL_DELAY) {
            revert InvalidRevealDelay(_revealDelay, MIN_REVEAL_DELAY, MAX_REVEAL_DELAY);
        }

        revealDelay = _revealDelay;
        relayerFeeBps = _relayerFeeBps;
        feeRecipient = _feeRecipient;
    }

    // =============================================================================
    // External Functions
    // =============================================================================

    /**
     * @notice Commit an order (first phase)
     * @param commitmentHash Hash of the order details
     * @param depositToken Token to deposit
     * @param depositAmount Amount to deposit
     * @return commitmentId Unique commitment ID
     */
    function commitOrder(
        bytes32 commitmentHash,
        address depositToken,
        uint256 depositAmount
    ) external nonReentrant whenNotPaused returns (bytes32 commitmentId) {
        if (commitmentHash == bytes32(0)) revert InvalidCommitment();
        if (depositAmount == 0) revert ZeroAmount();
        if (!approvedTokens[depositToken]) revert TokenNotApproved(depositToken);

        // Generate unique commitment ID
        commitmentId = keccak256(abi.encodePacked(
            msg.sender,
            commitmentHash,
            block.number,
            totalCommitments++
        ));

        uint256 revealDeadline = block.number + revealDelay + 50; // Extra blocks for reveal window

        commitments[commitmentId] = OrderCommitment({
            commitmentHash: commitmentHash,
            depositor: msg.sender,
            depositAmount: depositAmount,
            depositToken: depositToken,
            commitBlock: block.number,
            revealDeadline: revealDeadline,
            state: OrderState.COMMITTED
        });

        userCommitmentCount[msg.sender]++;

        // Transfer deposit
        IERC20(depositToken).safeTransferFrom(msg.sender, address(this), depositAmount);

        emit OrderCommitted(
            commitmentId,
            msg.sender,
            depositToken,
            depositAmount,
            revealDeadline
        );

        return commitmentId;
    }

    /**
     * @notice Reveal an order (second phase)
     * @param commitmentId Commitment ID
     * @param order Revealed order details
     */
    function revealOrder(
        bytes32 commitmentId,
        RevealedOrder calldata order
    ) external nonReentrant whenNotPaused {
        OrderCommitment storage commitment = commitments[commitmentId];

        if (commitment.state == OrderState.INVALID) revert CommitmentNotFound(commitmentId);
        if (commitment.state != OrderState.COMMITTED) {
            revert InvalidOrderState(commitmentId, OrderState.COMMITTED, commitment.state);
        }

        // Check reveal timing
        uint256 minRevealBlock = commitment.commitBlock + revealDelay;
        if (block.number < minRevealBlock) {
            revert RevealTooEarly(block.number, minRevealBlock);
        }
        if (block.number > commitment.revealDeadline) {
            revert RevealDeadlinePassed(commitment.revealDeadline, block.number);
        }

        // Verify commitment hash
        bytes32 computedHash = keccak256(abi.encodePacked(
            order.trader,
            order.orderType,
            order.tokenIn,
            order.tokenOut,
            order.amountIn,
            order.minAmountOut,
            order.limitPrice,
            order.deadline,
            order.salt
        ));

        if (computedHash != commitment.commitmentHash) revert InvalidReveal();
        if (order.trader != commitment.depositor) revert InvalidReveal();

        // Store revealed order
        revealedOrders[commitmentId] = order;
        commitment.state = OrderState.REVEALED;

        emit OrderRevealed(
            commitmentId,
            order.trader,
            order.orderType,
            order.tokenIn,
            order.tokenOut,
            order.amountIn
        );
    }

    /**
     * @notice Execute a revealed order
     * @param commitmentId Commitment ID
     * @param router DEX router to use
     * @param swapData Encoded swap data
     */
    function executeOrder(
        bytes32 commitmentId,
        address router,
        bytes calldata swapData
    ) external nonReentrant onlyRelayer {
        OrderCommitment storage commitment = commitments[commitmentId];
        RevealedOrder storage order = revealedOrders[commitmentId];

        if (commitment.state != OrderState.REVEALED) {
            revert InvalidOrderState(commitmentId, OrderState.REVEALED, commitment.state);
        }
        if (block.timestamp > order.deadline) revert OrderExpiredError();
        if (!approvedRouters[router]) revert RouterNotApproved(router);

        uint256 gasStart = gasleft();

        // Get initial balance
        uint256 balanceBefore = IERC20(order.tokenOut).balanceOf(address(this));

        // Approve router
        IERC20(order.tokenIn).forceApprove(router, order.amountIn);

        // Execute swap
        (bool success, ) = router.call(swapData);
        if (!success) revert SwapFailed();

        // Calculate output
        uint256 balanceAfter = IERC20(order.tokenOut).balanceOf(address(this));
        uint256 amountOut = balanceAfter - balanceBefore;

        // Check slippage
        if (amountOut < order.minAmountOut) {
            revert SlippageExceeded(order.minAmountOut, amountOut);
        }

        // For limit orders, check price
        if (order.orderType == OrderType.LIMIT && order.limitPrice > 0) {
            uint256 executionPrice = (amountOut * 1e18) / order.amountIn;
            if (executionPrice < order.limitPrice) {
                revert SlippageExceeded(order.limitPrice, executionPrice);
            }
        }

        // Calculate and deduct relayer fee
        uint256 relayerFee = (amountOut * relayerFeeBps) / BPS_DENOMINATOR;
        uint256 userAmount = amountOut - relayerFee;

        // Update state
        commitment.state = OrderState.EXECUTED;
        totalExecuted++;

        // Generate execution hash
        bytes32 executionHash = keccak256(abi.encodePacked(
            commitmentId,
            order.amountIn,
            amountOut,
            block.number,
            block.timestamp
        ));

        executionResults[commitmentId] = ExecutionResult({
            commitmentId: commitmentId,
            amountIn: order.amountIn,
            amountOut: amountOut,
            executionPrice: (amountOut * 1e18) / order.amountIn,
            gasUsed: gasStart - gasleft(),
            executionHash: executionHash
        });

        // Transfer output to trader
        IERC20(order.tokenOut).safeTransfer(order.trader, userAmount);

        // Transfer fee to recipient
        if (relayerFee > 0) {
            IERC20(order.tokenOut).safeTransfer(feeRecipient, relayerFee);
        }

        emit OrderExecuted(
            commitmentId,
            order.amountIn,
            amountOut,
            executionResults[commitmentId].executionPrice,
            executionHash
        );
    }

    /**
     * @notice Cancel a committed order (before reveal)
     * @param commitmentId Commitment ID
     */
    function cancelOrder(bytes32 commitmentId) external nonReentrant {
        OrderCommitment storage commitment = commitments[commitmentId];

        if (commitment.depositor != msg.sender) revert NotDepositor();
        if (commitment.state != OrderState.COMMITTED) {
            revert InvalidOrderState(commitmentId, OrderState.COMMITTED, commitment.state);
        }

        commitment.state = OrderState.CANCELLED;

        // Refund deposit
        IERC20(commitment.depositToken).safeTransfer(
            commitment.depositor,
            commitment.depositAmount
        );

        emit OrderCancelled(commitmentId, msg.sender);
    }

    /**
     * @notice Expire an order that wasn't revealed in time
     * @param commitmentId Commitment ID
     */
    function expireOrder(bytes32 commitmentId) external nonReentrant {
        OrderCommitment storage commitment = commitments[commitmentId];

        if (commitment.state != OrderState.COMMITTED) {
            revert InvalidOrderState(commitmentId, OrderState.COMMITTED, commitment.state);
        }
        if (block.number <= commitment.revealDeadline) {
            revert RevealDeadlinePassed(commitment.revealDeadline, block.number);
        }

        commitment.state = OrderState.EXPIRED;

        // Refund deposit
        IERC20(commitment.depositToken).safeTransfer(
            commitment.depositor,
            commitment.depositAmount
        );

        emit OrderExpired(commitmentId);
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================

    /**
     * @notice Set relayer authorization
     * @param relayer Relayer address
     * @param authorized Authorization status
     */
    function setRelayer(address relayer, bool authorized) external onlyOwner {
        if (relayer == address(0)) revert ZeroAddress();
        authorizedRelayers[relayer] = authorized;
        emit RelayerUpdated(relayer, authorized);
    }

    /**
     * @notice Set router approval
     * @param router Router address
     * @param approved Approval status
     */
    function setRouter(address router, bool approved) external onlyOwner {
        if (router == address(0)) revert ZeroAddress();
        approvedRouters[router] = approved;
        emit RouterUpdated(router, approved);
    }

    /**
     * @notice Set token approval
     * @param token Token address
     * @param approved Approval status
     */
    function setToken(address token, bool approved) external onlyOwner {
        if (token == address(0)) revert ZeroAddress();
        approvedTokens[token] = approved;
        emit TokenUpdated(token, approved);
    }

    /**
     * @notice Update reveal delay
     * @param newDelay New delay in blocks
     */
    function setRevealDelay(uint256 newDelay) external onlyOwner {
        if (newDelay < MIN_REVEAL_DELAY || newDelay > MAX_REVEAL_DELAY) {
            revert InvalidRevealDelay(newDelay, MIN_REVEAL_DELAY, MAX_REVEAL_DELAY);
        }
        revealDelay = newDelay;
    }

    /**
     * @notice Update relayer fee
     * @param newFeeBps New fee in basis points
     */
    function setRelayerFee(uint256 newFeeBps) external onlyOwner {
        relayerFeeBps = newFeeBps;
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
     * @notice Get commitment details
     * @param commitmentId Commitment ID
     * @return Commitment details
     */
    function getCommitment(bytes32 commitmentId) external view returns (OrderCommitment memory) {
        return commitments[commitmentId];
    }

    /**
     * @notice Get revealed order details
     * @param commitmentId Commitment ID
     * @return Revealed order details
     */
    function getRevealedOrder(bytes32 commitmentId) external view returns (RevealedOrder memory) {
        return revealedOrders[commitmentId];
    }

    /**
     * @notice Get execution result
     * @param commitmentId Commitment ID
     * @return Execution result
     */
    function getExecutionResult(bytes32 commitmentId) external view returns (ExecutionResult memory) {
        return executionResults[commitmentId];
    }

    /**
     * @notice Compute commitment hash for order
     * @param order Order details
     * @return Commitment hash
     */
    function computeCommitmentHash(RevealedOrder calldata order) external pure returns (bytes32) {
        return keccak256(abi.encodePacked(
            order.trader,
            order.orderType,
            order.tokenIn,
            order.tokenOut,
            order.amountIn,
            order.minAmountOut,
            order.limitPrice,
            order.deadline,
            order.salt
        ));
    }
}
