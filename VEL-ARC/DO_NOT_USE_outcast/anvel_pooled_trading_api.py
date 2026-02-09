#!/usr/bin/env python3
"""
ANVEL Pooled Trading API Routes

Production API endpoints for the pooled trading system.
Integrates with the API gateway for authentication and rate limiting.

All endpoints follow REST conventions and return JSON responses.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from flask import Blueprint, g, jsonify, request

from anvel_pooled_trading_integration import (
    get_pooled_trading_service,
    DepositTier,
    MINIMUM_DEPOSIT_USD,
    MINIMUM_WITHDRAWAL_USD,
    DEFAULT_TIER_CONFIGS,
)

logger = logging.getLogger(__name__)

# Create blueprint for pooled trading routes
pooled_trading_bp = Blueprint('pooled_trading', __name__, url_prefix='/api/v1/pooled')


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def _parse_decimal(value, field_name: str) -> Decimal:
    """Parse decimal value from request with validation."""
    if value is None:
        raise ValueError(f"Missing required field: {field_name}")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid {field_name}: must be a valid number")


def _parse_tier(tier_value: str) -> DepositTier:
    """Parse deposit tier from string."""
    tier_map = {
        'three_month': DepositTier.THREE_MONTH,
        '3_month': DepositTier.THREE_MONTH,
        '3month': DepositTier.THREE_MONTH,
        'six_month': DepositTier.SIX_MONTH,
        '6_month': DepositTier.SIX_MONTH,
        '6month': DepositTier.SIX_MONTH,
        'nine_month': DepositTier.NINE_MONTH,
        '9_month': DepositTier.NINE_MONTH,
        '9month': DepositTier.NINE_MONTH,
    }
    tier = tier_map.get(tier_value.lower())
    if not tier:
        valid = ', '.join(tier_map.keys())
        raise ValueError(f"Invalid tier: {tier_value}. Valid tiers: {valid}")
    return tier


def _get_service():
    """Get pooled trading service instance."""
    # In production, this would use properly initialized services
    # passed from the application context
    return get_pooled_trading_service()


# ==============================================================================
# DEPOSIT ENDPOINTS
# ==============================================================================

@pooled_trading_bp.route('/tiers', methods=['GET'])
def get_tiers():
    """
    Get available deposit tiers with their configurations.
    
    Returns:
        JSON array of tier configurations
    """
    try:
        tiers = []
        for tier, config in DEFAULT_TIER_CONFIGS.items():
            tiers.append({
                'name': tier.value,
                'lock_period_days': config.lock_period_days,
                'annual_yield_percent': float(config.yield_bps) / 100,
                'min_deposit_usd': float(config.min_deposit_usd),
                'max_deposit_usd': float(config.max_deposit_usd),
                'is_active': config.is_active,
            })
        
        return jsonify({
            'tiers': tiers,
            'minimum_deposit_usd': float(MINIMUM_DEPOSIT_USD),
            'minimum_withdrawal_usd': float(MINIMUM_WITHDRAWAL_USD),
        })
    except Exception as e:
        logger.error(f"Failed to get tiers: {e}")
        return jsonify({'error': 'Failed to retrieve tier information'}), 500


@pooled_trading_bp.route('/deposit', methods=['POST'])
def create_deposit():
    """
    Create a new pooled deposit.
    
    Request body:
        - amount: Deposit amount in USD (required)
        - tier: Deposit tier (required: three_month, six_month, nine_month)
        - referral_code: Optional referral code
        - tx_hash: Optional on-chain transaction hash
        - chain_id: Optional blockchain chain ID
        
    Returns:
        Deposit confirmation with ID and unlock time
    """
    # Get authenticated user ID from gateway
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        # Parse and validate inputs
        amount = _parse_decimal(data.get('amount'), 'amount')
        tier = _parse_tier(data.get('tier', ''))
        referral_code = data.get('referral_code')
        tx_hash = data.get('tx_hash')
        chain_id = data.get('chain_id')

        # Validate amount
        if amount < MINIMUM_DEPOSIT_USD:
            return jsonify({
                'error': f'Minimum deposit is ${MINIMUM_DEPOSIT_USD}',
                'minimum': float(MINIMUM_DEPOSIT_USD),
            }), 400

        # Get tier config for validation
        tier_config = DEFAULT_TIER_CONFIGS.get(tier)
        if not tier_config or not tier_config.is_active:
            return jsonify({'error': 'Tier not available'}), 400
        
        if amount < tier_config.min_deposit_usd:
            return jsonify({
                'error': f'Minimum for {tier.value} tier is ${tier_config.min_deposit_usd}',
                'minimum': float(tier_config.min_deposit_usd),
            }), 400
            
        if amount > tier_config.max_deposit_usd:
            return jsonify({
                'error': f'Maximum for {tier.value} tier is ${tier_config.max_deposit_usd}',
                'maximum': float(tier_config.max_deposit_usd),
            }), 400

        # Create deposit
        service = _get_service()
        deposit = service.deposit(
            user_id=user_id,
            amount=amount,
            tier=tier,
            referral_code=referral_code,
            tx_hash=tx_hash,
            chain_id=chain_id,
        )

        return jsonify({
            'status': 'success',
            'deposit_id': deposit.deposit_id,
            'amount': float(deposit.amount),
            'tier': tier.value,
            'deposit_timestamp': deposit.deposit_timestamp,
            'unlock_timestamp': deposit.unlock_timestamp,
            'lock_days': tier_config.lock_period_days,
        }), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to create deposit: {e}")
        return jsonify({'error': 'Failed to create deposit'}), 500


@pooled_trading_bp.route('/deposits', methods=['GET'])
def get_deposits():
    """
    Get user's deposits.
    
    Returns:
        JSON array of deposit records
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        service = _get_service()
        deposits = service.get_user_deposits(user_id)
        
        return jsonify({
            'deposits': [
                {
                    'deposit_id': d.deposit_id,
                    'amount': float(d.amount),
                    'tier': d.tier.value,
                    'deposit_timestamp': d.deposit_timestamp,
                    'unlock_timestamp': d.unlock_timestamp,
                    'accumulated_earnings': float(d.accumulated_earnings),
                    'reinvestment_count': d.reinvestment_count,
                    'is_active': d.is_active,
                }
                for d in deposits
            ],
            'total_count': len(deposits),
        })
    except Exception as e:
        logger.error(f"Failed to get deposits: {e}")
        return jsonify({'error': 'Failed to retrieve deposits'}), 500


@pooled_trading_bp.route('/deposits/<deposit_id>/withdraw', methods=['POST'])
def withdraw_deposit(deposit_id: str):
    """
    Withdraw a deposit after lock period.
    
    Path params:
        - deposit_id: ID of the deposit to withdraw
        
    Returns:
        Withdrawal confirmation with amount
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        service = _get_service()
        amount = service.withdraw_deposit(user_id, deposit_id)
        
        return jsonify({
            'status': 'success',
            'deposit_id': deposit_id,
            'amount_withdrawn': float(amount),
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to withdraw deposit: {e}")
        return jsonify({'error': 'Failed to withdraw deposit'}), 500


@pooled_trading_bp.route('/deposits/<deposit_id>/reinvest', methods=['POST'])
def reinvest_deposit(deposit_id: str):
    """
    Reinvest a deposit after lock period with bonus.
    
    Path params:
        - deposit_id: ID of the deposit to reinvest
        
    Request body:
        - additional_amount: Additional USD to add (optional, default 0)
        - new_tier: New tier for the deposit (required)
        
    Returns:
        Updated deposit information
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        data = request.get_json() or {}
        
        additional_amount = _parse_decimal(data.get('additional_amount', 0), 'additional_amount')
        new_tier = _parse_tier(data.get('new_tier', 'three_month'))

        service = _get_service()
        deposit = service.reinvest_deposit(
            user_id=user_id,
            deposit_id=deposit_id,
            additional_amount=additional_amount,
            new_tier=new_tier,
        )
        
        return jsonify({
            'status': 'success',
            'deposit_id': deposit.deposit_id,
            'new_amount': float(deposit.amount),
            'new_tier': new_tier.value,
            'unlock_timestamp': deposit.unlock_timestamp,
            'reinvestment_count': deposit.reinvestment_count,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to reinvest deposit: {e}")
        return jsonify({'error': 'Failed to reinvest deposit'}), 500


# ==============================================================================
# EARNINGS ENDPOINTS
# ==============================================================================

@pooled_trading_bp.route('/earnings', methods=['GET'])
def get_earnings():
    """
    Get user's earnings balance.
    
    Returns:
        Earnings balance and withdrawal status
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        service = _get_service()
        earnings = service.get_user_earnings(user_id)
        
        return jsonify({
            'claimable_earnings': float(earnings),
            'minimum_withdrawal': float(MINIMUM_WITHDRAWAL_USD),
            'can_withdraw': earnings >= MINIMUM_WITHDRAWAL_USD,
        })
    except Exception as e:
        logger.error(f"Failed to get earnings: {e}")
        return jsonify({'error': 'Failed to retrieve earnings'}), 500


@pooled_trading_bp.route('/earnings/withdraw', methods=['POST'])
def withdraw_earnings():
    """
    Withdraw accumulated earnings.
    
    Earnings can be withdrawn weekly after meeting the minimum threshold.
    
    Returns:
        Withdrawal confirmation with amount
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        service = _get_service()
        amount = service.withdraw_earnings(user_id)
        
        return jsonify({
            'status': 'success',
            'amount_withdrawn': float(amount),
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to withdraw earnings: {e}")
        return jsonify({'error': 'Failed to withdraw earnings'}), 500


# ==============================================================================
# REFERRAL ENDPOINTS
# ==============================================================================

@pooled_trading_bp.route('/referral/code', methods=['POST'])
def generate_referral_code():
    """
    Generate a referral code for the user.
    
    User must have an active deposit to generate a code.
    
    Returns:
        Generated referral code
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        service = _get_service()
        code = service.generate_referral_code(user_id)
        
        return jsonify({
            'status': 'success',
            'referral_code': code,
            'referrer_bonus_percent': 5.0,
            'referred_bonus_percent': 2.0,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to generate referral code: {e}")
        return jsonify({'error': 'Failed to generate referral code'}), 500


# ==============================================================================
# POOL STATS ENDPOINTS
# ==============================================================================

@pooled_trading_bp.route('/stats', methods=['GET'])
def get_pool_stats():
    """
    Get pool statistics.
    
    Returns:
        Pool summary statistics
    """
    try:
        service = _get_service()
        stats = service.get_pool_stats()
        
        return jsonify({
            'total_pool_value': stats.get('total_pool_value', 0),
            'total_deposits': stats.get('total_deposits', 0),
            'active_deposits': stats.get('active_deposits', 0),
            'total_users': stats.get('total_users', 0),
            'total_trades_executed': stats.get('total_trades_executed', 0),
            'supported_chains': stats.get('supported_chains', 0),
            'supported_dexes': stats.get('supported_dexes', 0),
        })
    except Exception as e:
        logger.error(f"Failed to get pool stats: {e}")
        return jsonify({'error': 'Failed to retrieve pool statistics'}), 500


@pooled_trading_bp.route('/chains', methods=['GET'])
def get_supported_chains():
    """
    Get supported blockchain networks.
    
    Returns:
        List of supported chains with details
    """
    try:
        service = _get_service()
        chains = service.get_supported_chains()
        
        return jsonify({
            'chains': [
                {
                    'chain_id': c.chain_id,
                    'name': c.chain_name,
                    'layer': c.layer.value,
                    'native_token': c.native_token,
                    'is_active': c.is_active,
                    'supported_dexes': c.supported_dexes,
                }
                for c in chains
            ],
        })
    except Exception as e:
        logger.error(f"Failed to get chains: {e}")
        return jsonify({'error': 'Failed to retrieve supported chains'}), 500


@pooled_trading_bp.route('/dexes', methods=['GET'])
def get_supported_dexes():
    """
    Get supported decentralized exchanges.
    
    Returns:
        List of supported DEXes with details
    """
    try:
        service = _get_service()
        dexes = service.get_supported_dexes()
        
        return jsonify({
            'dexes': [
                {
                    'name': d.name,
                    'chain_ids': d.chain_ids,
                    'fee_tiers': d.fee_tiers,
                    'is_active': d.is_active,
                }
                for d in dexes
            ],
        })
    except Exception as e:
        logger.error(f"Failed to get DEXes: {e}")
        return jsonify({'error': 'Failed to retrieve supported DEXes'}), 500


# ==============================================================================
# ADMIN ENDPOINTS (Protected)
# ==============================================================================

@pooled_trading_bp.route('/admin/distribute', methods=['POST'])
def distribute_profits():
    """
    Trigger profit distribution to depositors.
    
    Admin only endpoint.
    
    Returns:
        Distribution summary
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    # Check admin permission
    user_permissions = g.get('permissions', [])
    if 'admin' not in user_permissions and 'pooled_admin' not in user_permissions:
        return jsonify({'error': 'Admin permission required'}), 403

    try:
        service = _get_service()
        distribution = service.distribute_profits()
        
        return jsonify({
            'status': 'success',
            'distribution_id': distribution.distribution_id,
            'total_profits': float(distribution.total_profits),
            'recipient_count': distribution.distribution_count,
            'timestamp': distribution.timestamp,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to distribute profits: {e}")
        return jsonify({'error': 'Failed to distribute profits'}), 500


@pooled_trading_bp.route('/admin/pause', methods=['POST'])
def pause_service():
    """
    Pause the pooled trading service.
    
    Admin only endpoint.
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    user_permissions = g.get('permissions', [])
    if 'admin' not in user_permissions:
        return jsonify({'error': 'Admin permission required'}), 403

    try:
        service = _get_service()
        service.set_paused(True)
        
        return jsonify({'status': 'paused'})
    except Exception as e:
        logger.error(f"Failed to pause service: {e}")
        return jsonify({'error': 'Failed to pause service'}), 500


@pooled_trading_bp.route('/admin/unpause', methods=['POST'])
def unpause_service():
    """
    Unpause the pooled trading service.
    
    Admin only endpoint.
    """
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    user_permissions = g.get('permissions', [])
    if 'admin' not in user_permissions:
        return jsonify({'error': 'Admin permission required'}), 403

    try:
        service = _get_service()
        service.set_paused(False)
        
        return jsonify({'status': 'active'})
    except Exception as e:
        logger.error(f"Failed to unpause service: {e}")
        return jsonify({'error': 'Failed to unpause service'}), 500


# ==============================================================================
# REGISTRATION FUNCTION
# ==============================================================================

def register_pooled_trading_routes(app, gateway=None):
    """
    Register pooled trading routes with Flask app.
    
    Args:
        app: Flask application
        gateway: Optional APIGateway for authentication decorators
        
    Usage:
        from anvel_pooled_trading_api import register_pooled_trading_routes
        register_pooled_trading_routes(app, gateway)
    """
    app.register_blueprint(pooled_trading_bp)
    logger.info("Pooled trading API routes registered at /api/v1/pooled")


# ==============================================================================
# MODULE EXPORTS
# ==============================================================================

__all__ = [
    'pooled_trading_bp',
    'register_pooled_trading_routes',
]
