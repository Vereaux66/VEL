// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title VELPooledTradingVault
 * @notice Production-grade pooled trading vault for institutional fund management
 * @dev Manages pooled capital with tiered deposits, profit distribution, and risk controls
 *
 * Features:
 * - Tiered deposit system with lock periods (3/6/9 months)
 * - Profit distribution based on contribution weight
 * - Withdrawal queuing for large redemptions
 * - Emergency withdrawal with penalty
 * - Performance fee mechanism
 * - NAV (Net Asset Value) tracking
 */
contract VELPooledTradingVault is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // =============================================================================
    // Constants
    // =============================================================================

    uint256 public constant BPS_DENOMINATOR = 10000;
    uint256 public constant MAX_PERFORMANCE_FEE = 3000; // 30% max
    uint256 public constant MAX_MANAGEMENT_FEE = 200; // 2% max annual
    uint256 public constant WITHDRAWAL_DELAY = 1 days;
    uint256 public constant EMERGENCY_WITHDRAWAL_PENALTY = 500; // 5%

    // =============================================================================
    // Enums
    // =============================================================================

    enum DepositTier {
        THREE_MONTH,
        SIX_MONTH,
        NINE_MONTH
    }

    enum WithdrawalStatus {
        PENDING,
        READY,
        COMPLETED,
        CANCELLED
    }

    // =============================================================================
    // Structs
    // =============================================================================

    struct Deposit {
        uint256 amount;
        uint256 shares;
        DepositTier tier;
        uint256 depositTime;
        uint256 unlockTime;
        bool withdrawn;
    }

    struct WithdrawalRequest {
        address user;
        uint256 shares;
        uint256 requestTime;
        uint256 readyTime;
        WithdrawalStatus status;
    }

    struct VaultStats {
        uint256 totalDeposits;
        uint256 totalShares;
        uint256 totalProfitDistributed;
        uint256 highWaterMark;
        uint256 lastFeeCollection;
    }

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice Base asset token (e.g., USDC)
    IERC20 public immutable baseAsset;

    /// @notice Decimals of base asset
    uint8 public immutable baseAssetDecimals;

    /// @notice Authorized trader address
    address public trader;

    /// @notice Performance fee in basis points
    uint256 public performanceFeeBps;

    /// @notice Management fee in basis points (annual)
    uint256 public managementFeeBps;

    /// @notice Fee recipient address
    address public feeRecipient;

    /// @notice Vault statistics
    VaultStats public vaultStats;

    /// @notice Mapping of user address to deposits
    mapping(address => Deposit[]) public userDeposits;

    /// @notice User's total shares
    mapping(address => uint256) public userShares;

    /// @notice Withdrawal request queue
    WithdrawalRequest[] public withdrawalQueue;

    /// @notice User to withdrawal request index
    mapping(address => uint256[]) public userWithdrawalRequests;

    /// @notice Lock period for each tier (in seconds)
    mapping(DepositTier => uint256) public tierLockPeriod;

    /// @notice Bonus multiplier for each tier (in basis points, 10000 = 1x)
    mapping(DepositTier => uint256) public tierBonusMultiplier;

    /// @notice Total assets under management
    uint256 public totalAUM;

    // =============================================================================
    // Events
    // =============================================================================

    event DepositMade(
        address indexed user,
        uint256 amount,
        uint256 shares,
        DepositTier tier,
        uint256 depositIndex,
        uint256 unlockTime
    );
    event WithdrawalRequested(
        address indexed user,
        uint256 shares,
        uint256 requestIndex,
        uint256 readyTime
    );
    event WithdrawalCompleted(
        address indexed user,
        uint256 shares,
        uint256 amount,
        uint256 requestIndex
    );
    event EmergencyWithdrawal(
        address indexed user,
        uint256 shares,
        uint256 amount,
        uint256 penalty
    );
    event ProfitDistributed(uint256 profit, uint256 performanceFee);
    event TraderUpdated(address oldTrader, address newTrader);
    event FeesCollected(uint256 performanceFee, uint256 managementFee);

    // =============================================================================
    // Errors
    // =============================================================================

    error ZeroAddress();
    error ZeroAmount();
    error InsufficientShares(uint256 requested, uint256 available);
    error DepositStillLocked(uint256 unlockTime, uint256 currentTime);
    error WithdrawalNotReady(uint256 readyTime, uint256 currentTime);
    error InvalidWithdrawalStatus();
    error InvalidTier();
    error InvalidFee(uint256 fee);
    error NotAuthorized();
    error DepositAlreadyWithdrawn();

    // =============================================================================
    // Modifiers
    // =============================================================================

    modifier onlyTrader() {
        if (msg.sender != trader && msg.sender != owner()) revert NotAuthorized();
        _;
    }

    // =============================================================================
    // Constructor
    // =============================================================================

    /**
     * @notice Initialize the pooled trading vault
     * @param _baseAsset Base asset token address
     * @param _baseAssetDecimals Decimals of base asset
     * @param _trader Authorized trader address
     * @param _feeRecipient Fee recipient address
     * @param _performanceFeeBps Performance fee in basis points
     * @param _managementFeeBps Management fee in basis points
     */
    constructor(
        address _baseAsset,
        uint8 _baseAssetDecimals,
        address _trader,
        address _feeRecipient,
        uint256 _performanceFeeBps,
        uint256 _managementFeeBps
    ) Ownable(msg.sender) {
        if (_baseAsset == address(0) || _trader == address(0) || _feeRecipient == address(0)) {
            revert ZeroAddress();
        }
        if (_performanceFeeBps > MAX_PERFORMANCE_FEE) revert InvalidFee(_performanceFeeBps);
        if (_managementFeeBps > MAX_MANAGEMENT_FEE) revert InvalidFee(_managementFeeBps);

        baseAsset = IERC20(_baseAsset);
        baseAssetDecimals = _baseAssetDecimals;
        trader = _trader;
        feeRecipient = _feeRecipient;
        performanceFeeBps = _performanceFeeBps;
        managementFeeBps = _managementFeeBps;

        // Initialize tier lock periods
        tierLockPeriod[DepositTier.THREE_MONTH] = 90 days;
        tierLockPeriod[DepositTier.SIX_MONTH] = 180 days;
        tierLockPeriod[DepositTier.NINE_MONTH] = 270 days;

        // Initialize tier bonus multipliers (higher tier = higher share of profits)
        tierBonusMultiplier[DepositTier.THREE_MONTH] = 10000; // 1.0x
        tierBonusMultiplier[DepositTier.SIX_MONTH] = 11000;   // 1.1x
        tierBonusMultiplier[DepositTier.NINE_MONTH] = 12500;  // 1.25x

        vaultStats.lastFeeCollection = block.timestamp;
    }

    // =============================================================================
    // External Functions
    // =============================================================================

    /**
     * @notice Deposit funds into the vault
     * @param amount Amount of base asset to deposit
     * @param tier Deposit tier (lock period)
     * @return depositIndex Index of the deposit
     * @return shares Number of shares minted
     */
    function deposit(
        uint256 amount,
        DepositTier tier
    ) external nonReentrant whenNotPaused returns (uint256 depositIndex, uint256 shares) {
        if (amount == 0) revert ZeroAmount();

        // Transfer tokens
        baseAsset.safeTransferFrom(msg.sender, address(this), amount);

        // Calculate shares (with tier bonus)
        shares = _calculateShares(amount, tier);

        // Create deposit record
        uint256 unlockTime = block.timestamp + tierLockPeriod[tier];
        depositIndex = userDeposits[msg.sender].length;

        userDeposits[msg.sender].push(Deposit({
            amount: amount,
            shares: shares,
            tier: tier,
            depositTime: block.timestamp,
            unlockTime: unlockTime,
            withdrawn: false
        }));

        // Update state
        userShares[msg.sender] += shares;
        vaultStats.totalDeposits += amount;
        vaultStats.totalShares += shares;
        totalAUM += amount;

        emit DepositMade(msg.sender, amount, shares, tier, depositIndex, unlockTime);

        return (depositIndex, shares);
    }

    /**
     * @notice Request a withdrawal
     * @param shares Number of shares to withdraw
     * @return requestIndex Index of the withdrawal request
     */
    function requestWithdrawal(
        uint256 shares
    ) external nonReentrant whenNotPaused returns (uint256 requestIndex) {
        if (shares == 0) revert ZeroAmount();
        if (shares > userShares[msg.sender]) {
            revert InsufficientShares(shares, userShares[msg.sender]);
        }

        uint256 readyTime = block.timestamp + WITHDRAWAL_DELAY;
        requestIndex = withdrawalQueue.length;

        withdrawalQueue.push(WithdrawalRequest({
            user: msg.sender,
            shares: shares,
            requestTime: block.timestamp,
            readyTime: readyTime,
            status: WithdrawalStatus.PENDING
        }));

        userWithdrawalRequests[msg.sender].push(requestIndex);

        // Lock the shares
        userShares[msg.sender] -= shares;

        emit WithdrawalRequested(msg.sender, shares, requestIndex, readyTime);

        return requestIndex;
    }

    /**
     * @notice Complete a withdrawal request
     * @param requestIndex Index of the withdrawal request
     */
    function completeWithdrawal(uint256 requestIndex) external nonReentrant {
        WithdrawalRequest storage request = withdrawalQueue[requestIndex];
        
        if (request.user != msg.sender) revert NotAuthorized();
        if (request.status != WithdrawalStatus.PENDING) revert InvalidWithdrawalStatus();
        if (block.timestamp < request.readyTime) {
            revert WithdrawalNotReady(request.readyTime, block.timestamp);
        }

        // Calculate amount based on current NAV
        uint256 amount = _calculateWithdrawalAmount(request.shares);

        // Update request status
        request.status = WithdrawalStatus.COMPLETED;

        // Update vault stats
        vaultStats.totalShares -= request.shares;
        totalAUM -= amount;

        // Transfer tokens
        baseAsset.safeTransfer(msg.sender, amount);

        emit WithdrawalCompleted(msg.sender, request.shares, amount, requestIndex);
    }

    /**
     * @notice Emergency withdrawal with penalty (bypasses lock period)
     * @param depositIndex Index of the deposit to withdraw
     */
    function emergencyWithdraw(uint256 depositIndex) external nonReentrant {
        Deposit storage dep = userDeposits[msg.sender][depositIndex];
        
        if (dep.withdrawn) revert DepositAlreadyWithdrawn();
        if (dep.shares > userShares[msg.sender]) {
            revert InsufficientShares(dep.shares, userShares[msg.sender]);
        }

        // Calculate amount with penalty
        uint256 grossAmount = _calculateWithdrawalAmount(dep.shares);
        uint256 penalty = (grossAmount * EMERGENCY_WITHDRAWAL_PENALTY) / BPS_DENOMINATOR;
        uint256 netAmount = grossAmount - penalty;

        // Mark deposit as withdrawn
        dep.withdrawn = true;

        // Update state
        userShares[msg.sender] -= dep.shares;
        vaultStats.totalShares -= dep.shares;
        totalAUM -= grossAmount;

        // Transfer penalty to fee recipient
        if (penalty > 0) {
            baseAsset.safeTransfer(feeRecipient, penalty);
        }

        // Transfer net amount to user
        baseAsset.safeTransfer(msg.sender, netAmount);

        emit EmergencyWithdrawal(msg.sender, dep.shares, netAmount, penalty);
    }

    /**
     * @notice Distribute profits to shareholders
     * @param profit Total profit to distribute
     */
    function distributeProfits(uint256 profit) external onlyTrader {
        if (profit == 0) revert ZeroAmount();

        // Calculate performance fee (only on profit above high water mark)
        uint256 performanceFee = 0;
        if (totalAUM + profit > vaultStats.highWaterMark) {
            uint256 profitAboveHWM = totalAUM + profit - vaultStats.highWaterMark;
            performanceFee = (profitAboveHWM * performanceFeeBps) / BPS_DENOMINATOR;
            vaultStats.highWaterMark = totalAUM + profit;
        }

        uint256 netProfit = profit - performanceFee;

        // Update total AUM
        totalAUM += netProfit;
        vaultStats.totalProfitDistributed += netProfit;

        // Transfer performance fee
        if (performanceFee > 0) {
            baseAsset.safeTransfer(feeRecipient, performanceFee);
        }

        emit ProfitDistributed(netProfit, performanceFee);
    }

    /**
     * @notice Collect management fees
     */
    function collectManagementFees() external onlyTrader {
        uint256 timeSinceLastCollection = block.timestamp - vaultStats.lastFeeCollection;
        uint256 annualFee = (totalAUM * managementFeeBps) / BPS_DENOMINATOR;
        uint256 fee = (annualFee * timeSinceLastCollection) / 365 days;

        if (fee > 0) {
            vaultStats.lastFeeCollection = block.timestamp;
            totalAUM -= fee;
            baseAsset.safeTransfer(feeRecipient, fee);

            emit FeesCollected(0, fee);
        }
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================

    /**
     * @notice Update trader address
     * @param newTrader New trader address
     */
    function setTrader(address newTrader) external onlyOwner {
        if (newTrader == address(0)) revert ZeroAddress();
        address oldTrader = trader;
        trader = newTrader;
        emit TraderUpdated(oldTrader, newTrader);
    }

    /**
     * @notice Update performance fee
     * @param newFeeBps New fee in basis points
     */
    function setPerformanceFee(uint256 newFeeBps) external onlyOwner {
        if (newFeeBps > MAX_PERFORMANCE_FEE) revert InvalidFee(newFeeBps);
        performanceFeeBps = newFeeBps;
    }

    /**
     * @notice Update management fee
     * @param newFeeBps New fee in basis points
     */
    function setManagementFee(uint256 newFeeBps) external onlyOwner {
        if (newFeeBps > MAX_MANAGEMENT_FEE) revert InvalidFee(newFeeBps);
        managementFeeBps = newFeeBps;
    }

    /**
     * @notice Pause the vault
     */
    function pause() external onlyOwner {
        _pause();
    }

    /**
     * @notice Unpause the vault
     */
    function unpause() external onlyOwner {
        _unpause();
    }

    // =============================================================================
    // View Functions
    // =============================================================================

    /**
     * @notice Get current NAV per share
     * @return NAV per share in base asset units
     */
    function getNavPerShare() public view returns (uint256) {
        if (vaultStats.totalShares == 0) return 10 ** baseAssetDecimals;
        return (totalAUM * (10 ** baseAssetDecimals)) / vaultStats.totalShares;
    }

    /**
     * @notice Get user's total value
     * @param user User address
     * @return Total value in base asset units
     */
    function getUserValue(address user) external view returns (uint256) {
        return (userShares[user] * getNavPerShare()) / (10 ** baseAssetDecimals);
    }

    /**
     * @notice Get user's deposits
     * @param user User address
     * @return Array of deposits
     */
    function getUserDeposits(address user) external view returns (Deposit[] memory) {
        return userDeposits[user];
    }

    /**
     * @notice Get vault statistics
     * @return Vault statistics
     */
    function getVaultStats() external view returns (VaultStats memory) {
        return vaultStats;
    }

    // =============================================================================
    // Internal Functions
    // =============================================================================

    /**
     * @notice Calculate shares for a deposit amount
     * @param amount Deposit amount
     * @param tier Deposit tier
     * @return shares Number of shares
     */
    function _calculateShares(uint256 amount, DepositTier tier) internal view returns (uint256 shares) {
        uint256 navPerShare = getNavPerShare();
        uint256 baseShares = (amount * (10 ** baseAssetDecimals)) / navPerShare;
        
        // Apply tier bonus
        shares = (baseShares * tierBonusMultiplier[tier]) / BPS_DENOMINATOR;
    }

    /**
     * @notice Calculate withdrawal amount for shares
     * @param shares Number of shares
     * @return amount Amount in base asset
     */
    function _calculateWithdrawalAmount(uint256 shares) internal view returns (uint256 amount) {
        uint256 navPerShare = getNavPerShare();
        amount = (shares * navPerShare) / (10 ** baseAssetDecimals);
    }
}
