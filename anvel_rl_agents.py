#!/usr/bin/env python3
"""
ANVEL Advanced Reinforcement Learning Agents - Phase 2 Enhancement
===================================================================

Implements state-of-the-art RL algorithms for dynamic trading strategy optimization:
- PPO (Proximal Policy Optimization) - Stable policy gradient with clipping
- A2C (Advantage Actor-Critic) - Synchronous advantage estimation
- Enhanced DQN with Prioritized Experience Replay

Reference papers:
- PPO: Schulman et al., "Proximal Policy Optimization Algorithms" (2017)
- A2C: Mnih et al., "Asynchronous Methods for Deep Reinforcement Learning" (2016)
- PER: Schaul et al., "Prioritized Experience Replay" (2016)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.optim as optim
    from torch.distributions import Categorical, Normal

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

    # Create stub classes that raise clear errors when PyTorch is unavailable
    class _TorchStubMeta(type):
        """Metaclass for torch stubs that raises errors on attribute access."""

        def __getattr__(cls, name: str) -> Any:
            raise NotImplementedError(
                f"PyTorch is required to use reinforcement learning agents. "
                f"Cannot access '{name}'. Please install PyTorch: pip install torch"
            )

    class _TorchStub(metaclass=_TorchStubMeta):
        """
        Stub object used when PyTorch is not available.

        Any attribute access on this object will raise a clear error indicating that
        the 'torch' package is required for the reinforcement learning agents.
        """

        def __getattr__(self, name: str) -> Any:
            raise NotImplementedError(
                f"PyTorch is required to use reinforcement learning agents. "
                f"Cannot access '{name}'. Please install PyTorch: pip install torch"
            )

        def __call__(self, *args, **kwargs):
            raise NotImplementedError(
                "PyTorch is required to use reinforcement learning agents. "
                "Please install PyTorch: pip install torch"
            )

    # Create stubs for all PyTorch objects
    torch = _TorchStub()
    nn = _TorchStub()
    F = _TorchStub()
    optim = _TorchStub()
    Categorical = _TorchStub()
    Normal = _TorchStub()

# Setup logging
logging.basicConfig(level=logging.INFO)
_rl_logger = logging.getLogger("ANVEL.RL")


# ═══════════════════════════════════════════════════════════════════════════════
# Prioritized Experience Replay Buffer
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Experience:
    """Single experience tuple for replay buffer."""

    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


class SumTree:
    """
    Sum tree data structure for efficient prioritized sampling.

    Used by PrioritizedReplayBuffer for O(log n) sampling based on priorities.
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.tree = np.zeros(2 * capacity - 1)
        self.data = np.zeros(capacity, dtype=object)
        self.write_idx = 0
        self.n_entries = 0

    def _propagate(self, idx: int, change: float) -> None:
        """Propagate priority change up the tree."""
        parent = (idx - 1) // 2
        self.tree[parent] += change
        if parent != 0:
            self._propagate(parent, change)

    def _retrieve(self, idx: int, s: float) -> int:
        """Retrieve leaf index for given cumulative sum."""
        left = 2 * idx + 1
        right = left + 1

        if left >= len(self.tree):
            return idx

        if s <= self.tree[left]:
            return self._retrieve(left, s)
        else:
            return self._retrieve(right, s - self.tree[left])

    def total(self) -> float:
        """Return total priority."""
        return self.tree[0]

    def add(self, priority: float, data: Experience) -> None:
        """Add experience with given priority."""
        idx = self.write_idx + self.capacity - 1

        self.data[self.write_idx] = data
        self.update(idx, priority)

        self.write_idx = (self.write_idx + 1) % self.capacity
        self.n_entries = min(self.n_entries + 1, self.capacity)

    def update(self, idx: int, priority: float) -> None:
        """Update priority at given index."""
        change = priority - self.tree[idx]
        self.tree[idx] = priority
        self._propagate(idx, change)

    def get(self, s: float) -> Tuple[int, float, Experience]:
        """Get experience for given cumulative sum."""
        idx = self._retrieve(0, s)
        data_idx = idx - self.capacity + 1
        return idx, self.tree[idx], self.data[data_idx]


class PrioritizedReplayBuffer:
    """
    Prioritized Experience Replay buffer for DQN.

    Samples experiences based on TD-error priority for more efficient learning.
    Uses importance sampling weights to correct for sampling bias.
    """

    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 0.001,
        epsilon: float = 1e-6,
    ):
        """
        Initialize PER buffer.

        Args:
            capacity: Maximum buffer size
            alpha: Priority exponent (0 = uniform, 1 = full prioritization)
            beta: Importance sampling exponent (annealed to 1)
            beta_increment: Beta annealing rate
            epsilon: Small constant to ensure non-zero priorities
        """
        self.tree = SumTree(capacity)
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.epsilon = epsilon
        self.max_priority = 1.0

    def add(self, experience: Experience) -> None:
        """Add experience with max priority."""
        priority = self.max_priority**self.alpha
        self.tree.add(priority, experience)

    def sample(
        self, batch_size: int
    ) -> Tuple[List[Experience], np.ndarray, np.ndarray]:
        """
        Sample batch with priorities.

        Returns:
            experiences: List of sampled experiences
            indices: Tree indices for priority updates
            weights: Importance sampling weights
        """
        experiences = []
        indices = np.zeros(batch_size, dtype=np.int32)
        priorities = np.zeros(batch_size, dtype=np.float32)

        segment = self.tree.total() / batch_size

        self.beta = min(1.0, self.beta + self.beta_increment)

        for i in range(batch_size):
            a = segment * i
            b = segment * (i + 1)
            s = np.random.uniform(a, b)
            idx, priority, experience = self.tree.get(s)
            indices[i] = idx
            priorities[i] = priority
            experiences.append(experience)

        # Importance sampling weights
        probs = priorities / self.tree.total()
        weights = (self.tree.n_entries * probs) ** (-self.beta)
        weights /= weights.max()

        return experiences, indices, weights

    def update_priorities(self, indices: np.ndarray, td_errors: np.ndarray) -> None:
        """Update priorities based on TD errors."""
        for idx, td_error in zip(indices, td_errors):
            priority = (abs(td_error) + self.epsilon) ** self.alpha
            self.tree.update(idx, priority)
            self.max_priority = max(self.max_priority, priority)

    def __len__(self) -> int:
        return self.tree.n_entries


# ═══════════════════════════════════════════════════════════════════════════════
# Neural Network Architectures for RL
# ═══════════════════════════════════════════════════════════════════════════════

# Stub base class if torch not available
if not TORCH_AVAILABLE:

    class _DummyModule:
        """Dummy base class when torch not available."""

        pass

    nn = type("nn", (), {"Module": _DummyModule})()
    torch = type("torch", (), {"Tensor": type("Tensor", (), {})})()
    F = type("F", (), {})()
    Categorical = type("Categorical", (), {})()
    _unusedNormal = type("Normal", (), {})()
    optim = type("optim", (), {"Adam": type("Adam", (), {})})()


class ActorNetwork(nn.Module):
    """
    Actor network for policy gradient methods (PPO, A2C).

    Outputs action probabilities for discrete action spaces.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: Tuple[int, ...] = (256, 128, 64),
        dropout: float = 0.1,
    ):
        super(ActorNetwork, self).__init__()

        layers = []
        prev_dim = state_dim
        for hidden_dim in hidden_dims:
            layers.extend(
                [
                    nn.Linear(prev_dim, hidden_dim),
                    nn.LayerNorm(hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                ]
            )
            prev_dim = hidden_dim

        self.features = nn.Sequential(*layers)
        self.policy_head = nn.Linear(prev_dim, action_dim)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Return action logits."""
        features = self.features(state)
        return self.policy_head(features)

    def get_action_probs(self, state: torch.Tensor) -> torch.Tensor:
        """Return action probabilities."""
        logits = self.forward(state)
        return F.softmax(logits, dim=-1)

    def get_distribution(self, state: torch.Tensor) -> Categorical:
        """Return categorical distribution over actions."""
        probs = self.get_action_probs(state)
        return Categorical(probs)


class CriticNetwork(nn.Module):
    """
    Critic network for value estimation.

    Estimates state value V(s) for advantage calculation.
    """

    def __init__(
        self,
        state_dim: int,
        hidden_dims: Tuple[int, ...] = (256, 128, 64),
        dropout: float = 0.1,
    ):
        super(CriticNetwork, self).__init__()

        layers = []
        prev_dim = state_dim
        for hidden_dim in hidden_dims:
            layers.extend(
                [
                    nn.Linear(prev_dim, hidden_dim),
                    nn.LayerNorm(hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                ]
            )
            prev_dim = hidden_dim

        self.features = nn.Sequential(*layers)
        self.value_head = nn.Linear(prev_dim, 1)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Return state value."""
        features = self.features(state)
        return self.value_head(features).squeeze(-1)


class ActorCriticNetwork(nn.Module):
    """
    Combined Actor-Critic network with shared features.

    More parameter efficient than separate networks.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: Tuple[int, ...] = (256, 128),
        dropout: float = 0.1,
    ):
        super(ActorCriticNetwork, self).__init__()

        # Shared feature extractor
        layers = []
        prev_dim = state_dim
        for hidden_dim in hidden_dims:
            layers.extend(
                [
                    nn.Linear(prev_dim, hidden_dim),
                    nn.LayerNorm(hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                ]
            )
            prev_dim = hidden_dim

        self.shared = nn.Sequential(*layers)

        # Actor head
        self.actor_head = nn.Sequential(
            nn.Linear(prev_dim, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim),
        )

        # Critic head
        self.critic_head = nn.Sequential(
            nn.Linear(prev_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Return action logits and state value."""
        features = self.shared(state)
        action_logits = self.actor_head(features)
        value = self.critic_head(features).squeeze(-1)
        return action_logits, value

    def get_action_and_value(
        self,
        state: torch.Tensor,
        action: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get action, log probability, entropy, and value.

        If action is provided, compute log prob for that action.
        Otherwise, sample a new action.
        """
        logits, value = self.forward(state)
        probs = F.softmax(logits, dim=-1)
        dist = Categorical(probs)

        if action is None:
            action = dist.sample()

        log_prob = dist.log_prob(action)
        entropy = dist.entropy()

        return action, log_prob, entropy, value


# ═══════════════════════════════════════════════════════════════════════════════
# PPO Agent (Proximal Policy Optimization)
# ═══════════════════════════════════════════════════════════════════════════════


class PPOAgent:
    """
    Proximal Policy Optimization agent for trading.

    PPO is a policy gradient method that uses a clipped surrogate objective
    to ensure stable policy updates. It's one of the most robust RL algorithms
    for continuous control tasks.

    Key features:
    - Clipped policy ratio to prevent large policy updates
    - Generalized Advantage Estimation (GAE) for variance reduction
    - Multiple epochs of mini-batch updates per rollout
    - Risk-adjusted reward shaping for trading
    """

    def __init__(
        self,
        state_dim: int = 20,
        action_dim: int = 3,  # Buy, Hold, Sell
        hidden_dims: Tuple[int, ...] = (256, 128),
        lr: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.2,
        value_coef: float = 0.5,
        entropy_coef: float = 0.01,
        max_grad_norm: float = 0.5,
        n_epochs: int = 10,
        batch_size: int = 64,
        device: Optional[torch.device] = None,
    ):
        """
        Initialize PPO agent.

        Args:
            state_dim: Dimension of state space
            action_dim: Number of discrete actions
            hidden_dims: Hidden layer dimensions
            lr: Learning rate
            gamma: Discount factor
            gae_lambda: GAE lambda for advantage estimation
            clip_epsilon: PPO clipping parameter
            value_coef: Value loss coefficient
            entropy_coef: Entropy bonus coefficient
            max_grad_norm: Gradient clipping threshold
            n_epochs: Update epochs per rollout
            batch_size: Mini-batch size for updates
            device: Torch device
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        self.max_grad_norm = max_grad_norm
        self.n_epochs = n_epochs
        self.batch_size = batch_size

        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        # Actor-Critic network
        self.network = ActorCriticNetwork(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_dims=hidden_dims,
        ).to(self.device)

        self.optimizer = optim.Adam(self.network.parameters(), lr=lr)

        # Rollout buffer
        self.states = []
        self.actions = []
        self.rewards = []
        self.values = []
        self.log_probs = []
        self.dones = []

        # Metrics
        self.total_steps = 0
        self.episode_rewards = []

        _rl_logger.info(
            f"PPO agent initialized: state_dim={state_dim}, action_dim={action_dim}, "
            f"device={self.device}"
        )

    def select_action(self, state: np.ndarray) -> Tuple[int, float, float]:
        """
        Select action using current policy.

        Returns:
            action: Selected action
            log_prob: Log probability of action
            value: Estimated state value
        """
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        with torch.no_grad():
            action, log_prob, _, value = self.network.get_action_and_value(state_t)

        return action.item(), log_prob.item(), value.item()

    def store_transition(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        value: float,
        log_prob: float,
        done: bool,
    ) -> None:
        """Store transition in rollout buffer."""
        self.states.append(state)
        self.actions.append(action)
        self.rewards.append(reward)
        self.values.append(value)
        self.log_probs.append(log_prob)
        self.dones.append(done)

    def compute_gae(self, next_value: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute Generalized Advantage Estimation.

        GAE provides a good bias-variance tradeoff for advantage estimation.
        """
        rewards = np.array(self.rewards)
        values = np.array(self.values)
        dones = np.array(self.dones)

        advantages = np.zeros_like(rewards)
        last_gae = 0

        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_value_t = next_value
            else:
                next_value_t = values[t + 1]

            next_non_terminal = 1.0 - dones[t]
            delta = (
                rewards[t] + self.gamma * next_value_t * next_non_terminal - values[t]
            )
            advantages[t] = last_gae = (
                delta + self.gamma * self.gae_lambda * next_non_terminal * last_gae
            )

        returns = advantages + values
        return advantages, returns

    def update(self, next_value: float) -> Dict[str, float]:
        """
        Perform PPO update.

        Returns:
            Dictionary with loss metrics
        """
        # Compute advantages
        advantages, returns = self.compute_gae(next_value)

        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # Convert to tensors
        states = torch.FloatTensor(np.array(self.states)).to(self.device)
        actions = torch.LongTensor(self.actions).to(self.device)
        old_log_probs = torch.FloatTensor(self.log_probs).to(self.device)
        advantages_t = torch.FloatTensor(advantages).to(self.device)
        returns_t = torch.FloatTensor(returns).to(self.device)

        # Multiple epochs of mini-batch updates
        total_policy_loss = 0
        total_value_loss = 0
        total_entropy = 0
        n_updates = 0

        dataset_size = len(self.states)
        indices = np.arange(dataset_size)

        for _ in range(self.n_epochs):
            np.random.shuffle(indices)

            for start in range(0, dataset_size, self.batch_size):
                end = start + self.batch_size
                batch_indices = indices[start:end]

                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_advantages = advantages_t[batch_indices]
                batch_returns = returns_t[batch_indices]

                # Get new log probs and values
                _, new_log_probs, entropy, values = self.network.get_action_and_value(
                    batch_states, batch_actions
                )

                # Policy loss with clipping
                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                surr1 = ratio * batch_advantages
                surr2 = (
                    torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon)
                    * batch_advantages
                )
                policy_loss = -torch.min(surr1, surr2).mean()

                # Value loss
                value_loss = F.mse_loss(values, batch_returns)

                # Entropy bonus
                entropy_loss = -entropy.mean()

                # Total loss
                loss = (
                    policy_loss
                    + self.value_coef * value_loss
                    + self.entropy_coef * entropy_loss
                )

                # Optimize
                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.network.parameters(), self.max_grad_norm)
                self.optimizer.step()

                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                total_entropy += entropy.mean().item()
                n_updates += 1

        # Clear rollout buffer
        self.states.clear()
        self.actions.clear()
        self.rewards.clear()
        self.values.clear()
        self.log_probs.clear()
        self.dones.clear()

        return {
            "policy_loss": total_policy_loss / n_updates,
            "value_loss": total_value_loss / n_updates,
            "entropy": total_entropy / n_updates,
        }

    def calculate_trading_reward(
        self,
        action: int,
        price_change: float,
        position: float,
        portfolio_value: float,
        transaction_cost: float = 0.001,
    ) -> float:
        """
        Calculate risk-adjusted trading reward.

        Uses Sharpe-like reward shaping to encourage risk-adjusted returns.

        Args:
            action: 0=Buy, 1=Hold, 2=Sell
            price_change: Percentage price change
            position: Current position (-1 to 1)
            portfolio_value: Current portfolio value
            transaction_cost: Transaction cost as fraction

        Returns:
            Shaped reward
        """
        # Base PnL reward
        if action == 0:  # Buy
            pnl = price_change * (1 - position)
            cost = transaction_cost if position < 1 else 0
        elif action == 2:  # Sell
            pnl = -price_change * (1 + position)
            cost = transaction_cost if position > -1 else 0
        else:  # Hold
            pnl = price_change * position
            cost = 0

        reward = pnl - cost

        # Risk penalty for large positions
        position_penalty = -0.001 * abs(position)

        # Reward for reducing drawdown
        drawdown_bonus = 0.01 if reward > 0 else 0

        return reward + position_penalty + drawdown_bonus

    def save(self, path: str) -> None:
        """Save model."""
        torch.save(
            {
                "network_state_dict": self.network.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "total_steps": self.total_steps,
            },
            path,
        )
        _rl_logger.info(f"PPO agent saved to {path}")

    def load(self, path: str) -> None:
        """Load model."""
        checkpoint = torch.load(path, map_location=self.device)
        self.network.load_state_dict(checkpoint["network_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.total_steps = checkpoint.get("total_steps", 0)
        _rl_logger.info(f"PPO agent loaded from {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# A2C Agent (Advantage Actor-Critic)
# ═══════════════════════════════════════════════════════════════════════════════


class A2CAgent:
    """
    Advantage Actor-Critic agent for trading.

    A2C is a synchronous variant of A3C that uses advantage function
    for variance reduction in policy gradient updates.

    Key features:
    - Separate actor and critic networks (can share features)
    - N-step returns for faster credit assignment
    - Entropy regularization for exploration
    - Real-time adaptation suitable for live trading
    """

    def __init__(
        self,
        state_dim: int = 20,
        action_dim: int = 3,
        hidden_dims: Tuple[int, ...] = (256, 128),
        actor_lr: float = 3e-4,
        critic_lr: float = 1e-3,
        gamma: float = 0.99,
        n_steps: int = 5,
        entropy_coef: float = 0.01,
        max_grad_norm: float = 0.5,
        device: Optional[torch.device] = None,
    ):
        """
        Initialize A2C agent.

        Args:
            state_dim: Dimension of state space
            action_dim: Number of discrete actions
            hidden_dims: Hidden layer dimensions
            actor_lr: Actor learning rate
            critic_lr: Critic learning rate
            gamma: Discount factor
            n_steps: Steps for n-step returns
            entropy_coef: Entropy bonus coefficient
            max_grad_norm: Gradient clipping threshold
            device: Torch device
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.n_steps = n_steps
        self.entropy_coef = entropy_coef
        self.max_grad_norm = max_grad_norm

        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        # Separate actor and critic
        self.actor = ActorNetwork(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_dims=hidden_dims,
        ).to(self.device)

        self.critic = CriticNetwork(
            state_dim=state_dim,
            hidden_dims=hidden_dims,
        ).to(self.device)

        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=critic_lr)

        # N-step buffer
        self.states = []
        self.actions = []
        self.rewards = []
        self.dones = []

        # Metrics
        self.total_steps = 0

        _rl_logger.info(
            f"A2C agent initialized: state_dim={state_dim}, action_dim={action_dim}, "
            f"n_steps={n_steps}, device={self.device}"
        )

    def select_action(self, state: np.ndarray) -> Tuple[int, torch.Tensor]:
        """
        Select action using current policy.

        Returns:
            action: Selected action
            log_prob: Log probability tensor (for gradient computation)
        """
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        dist = self.actor.get_distribution(state_t)
        action = dist.sample()
        log_prob = dist.log_prob(action)

        return action.item(), log_prob

    def store_transition(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        done: bool,
    ) -> None:
        """Store transition in n-step buffer."""
        self.states.append(state)
        self.actions.append(action)
        self.rewards.append(reward)
        self.dones.append(done)

    def compute_n_step_returns(self, next_state: np.ndarray) -> np.ndarray:
        """Compute n-step returns."""
        n = len(self.rewards)
        returns = np.zeros(n)

        # Bootstrap from value of next state
        next_state_t = torch.FloatTensor(next_state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            next_value = self.critic(next_state_t).item()

        R = next_value
        for t in reversed(range(n)):
            R = self.rewards[t] + self.gamma * R * (1 - self.dones[t])
            returns[t] = R

        return returns

    def update(self, next_state: np.ndarray) -> Dict[str, float]:
        """
        Perform A2C update.

        Returns:
            Dictionary with loss metrics
        """
        if len(self.states) < self.n_steps:
            return {}

        # Compute returns
        returns = self.compute_n_step_returns(next_state)

        # Convert to tensors
        states = torch.FloatTensor(np.array(self.states)).to(self.device)
        actions = torch.LongTensor(self.actions).to(self.device)
        returns_t = torch.FloatTensor(returns).to(self.device)

        # Get values and advantages
        values = self.critic(states)
        advantages = returns_t - values.detach()

        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # Actor loss
        dist = self.actor.get_distribution(states)
        log_probs = dist.log_prob(actions)
        entropy = dist.entropy().mean()

        actor_loss = -(log_probs * advantages).mean() - self.entropy_coef * entropy

        # Critic loss
        critic_loss = F.mse_loss(values, returns_t)

        # Update actor
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        nn.utils.clip_grad_norm_(self.actor.parameters(), self.max_grad_norm)
        self.actor_optimizer.step()

        # Update critic
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        nn.utils.clip_grad_norm_(self.critic.parameters(), self.max_grad_norm)
        self.critic_optimizer.step()

        # Clear buffer
        self.states.clear()
        self.actions.clear()
        self.rewards.clear()
        self.dones.clear()

        return {
            "actor_loss": actor_loss.item(),
            "critic_loss": critic_loss.item(),
            "entropy": entropy.item(),
        }

    def calculate_trading_reward(
        self,
        action: int,
        price_change: float,
        position: float,
        volatility: float = 0.02,
    ) -> float:
        """
        Calculate volatility-adjusted trading reward.

        Normalizes rewards by volatility for more stable learning.
        """
        # Base reward
        if action == 0:  # Buy
            base_reward = price_change * (1 - position)
        elif action == 2:  # Sell
            base_reward = -price_change * (1 + position)
        else:  # Hold
            base_reward = price_change * position

        # Volatility normalization
        normalized_reward = base_reward / (volatility + 1e-8)

        # Clip to prevent extreme rewards
        return np.clip(normalized_reward, -10, 10)

    def save(self, path: str) -> None:
        """Save model."""
        torch.save(
            {
                "actor_state_dict": self.actor.state_dict(),
                "critic_state_dict": self.critic.state_dict(),
                "actor_optimizer_state_dict": self.actor_optimizer.state_dict(),
                "critic_optimizer_state_dict": self.critic_optimizer.state_dict(),
                "total_steps": self.total_steps,
            },
            path,
        )
        _rl_logger.info(f"A2C agent saved to {path}")

    def load(self, path: str) -> None:
        """Load model."""
        checkpoint = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(checkpoint["actor_state_dict"])
        self.critic.load_state_dict(checkpoint["critic_state_dict"])
        self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer_state_dict"])
        self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer_state_dict"])
        self.total_steps = checkpoint.get("total_steps", 0)
        _rl_logger.info(f"A2C agent loaded from {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Enhanced DQN with Prioritized Experience Replay
# ═══════════════════════════════════════════════════════════════════════════════


class DuelingDQN(nn.Module):
    """
    Dueling DQN architecture.

    Separates value and advantage streams for better learning.
    Q(s,a) = V(s) + A(s,a) - mean(A(s,:))
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: Tuple[int, ...] = (256, 128),
    ):
        super(DuelingDQN, self).__init__()

        # Shared feature extractor
        layers = []
        prev_dim = state_dim
        for hidden_dim in hidden_dims:
            layers.extend(
                [
                    nn.Linear(prev_dim, hidden_dim),
                    nn.ReLU(),
                ]
            )
            prev_dim = hidden_dim

        self.features = nn.Sequential(*layers)

        # Value stream
        self.value_stream = nn.Sequential(
            nn.Linear(prev_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

        # Advantage stream
        self.advantage_stream = nn.Sequential(
            nn.Linear(prev_dim, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Return Q-values using dueling architecture."""
        features = self.features(state)
        value = self.value_stream(features)
        advantages = self.advantage_stream(features)

        # Combine: Q = V + (A - mean(A))
        q_values = value + advantages - advantages.mean(dim=-1, keepdim=True)
        return q_values


class EnhancedDQNAgent:
    """
    Enhanced DQN agent with modern improvements.

    Combines:
    - Dueling architecture
    - Prioritized Experience Replay
    - Double DQN
    - Noisy networks (optional)
    """

    def __init__(
        self,
        state_dim: int = 20,
        action_dim: int = 3,
        hidden_dims: Tuple[int, ...] = (256, 128),
        lr: float = 1e-4,
        gamma: float = 0.99,
        tau: float = 0.005,  # Soft update parameter
        buffer_size: int = 100000,
        batch_size: int = 64,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.01,
        epsilon_decay: float = 0.995,
        update_freq: int = 4,
        device: Optional[torch.device] = None,
    ):
        """
        Initialize Enhanced DQN agent.

        Args:
            state_dim: Dimension of state space
            action_dim: Number of discrete actions
            hidden_dims: Hidden layer dimensions
            lr: Learning rate
            gamma: Discount factor
            tau: Soft target update parameter
            buffer_size: Replay buffer capacity
            batch_size: Training batch size
            epsilon_start: Initial exploration rate
            epsilon_end: Final exploration rate
            epsilon_decay: Exploration decay rate
            update_freq: Steps between updates
            device: Torch device
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.update_freq = update_freq

        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        # Dueling DQN networks
        self.policy_net = DuelingDQN(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_dims=hidden_dims,
        ).to(self.device)

        self.target_net = DuelingDQN(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_dims=hidden_dims,
        ).to(self.device)

        self.target_net.load_state_dict(self.policy_net.state_dict())

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=lr)

        # Prioritized replay buffer
        self.replay_buffer = PrioritizedReplayBuffer(capacity=buffer_size)

        # Step counter
        self.total_steps = 0

        _rl_logger.info(
            f"Enhanced DQN agent initialized: state_dim={state_dim}, "
            f"action_dim={action_dim}, device={self.device}"
        )

    def select_action(self, state: np.ndarray) -> int:
        """Select action using epsilon-greedy policy."""
        if np.random.random() < self.epsilon:
            return np.random.randint(self.action_dim)

        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        with torch.no_grad():
            q_values = self.policy_net(state_t)

        return q_values.argmax().item()

    def store_transition(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        """Store transition in replay buffer."""
        experience = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
        )
        self.replay_buffer.add(experience)

    def update(self) -> Optional[Dict[str, float]]:
        """
        Perform DQN update with prioritized replay.

        Returns:
            Dictionary with loss metrics, or None if buffer too small
        """
        self.total_steps += 1

        # Only update every update_freq steps
        if self.total_steps % self.update_freq != 0:
            return None

        if len(self.replay_buffer) < self.batch_size:
            return None

        # Sample from prioritized buffer
        experiences, indices, weights = self.replay_buffer.sample(self.batch_size)

        # Convert to tensors
        states = torch.FloatTensor(np.array([e.state for e in experiences])).to(
            self.device
        )
        actions = torch.LongTensor([e.action for e in experiences]).to(self.device)
        rewards = torch.FloatTensor([e.reward for e in experiences]).to(self.device)
        next_states = torch.FloatTensor(
            np.array([e.next_state for e in experiences])
        ).to(self.device)
        dones = torch.FloatTensor([e.done for e in experiences]).to(self.device)
        weights_t = torch.FloatTensor(weights).to(self.device)

        # Current Q values
        current_q = self.policy_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)

        # Double DQN: use policy net to select action, target net to evaluate
        with torch.no_grad():
            next_actions = self.policy_net(next_states).argmax(dim=1)
            next_q = (
                self.target_net(next_states)
                .gather(1, next_actions.unsqueeze(1))
                .squeeze(1)
            )
            target_q = rewards + (1 - dones) * self.gamma * next_q

        # TD errors for priority update
        td_errors = (current_q - target_q).detach().cpu().numpy()

        # Weighted loss
        loss = (weights_t * F.mse_loss(current_q, target_q, reduction="none")).mean()

        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()

        # Update priorities
        self.replay_buffer.update_priorities(indices, td_errors)

        # Soft update target network
        for target_param, policy_param in zip(
            self.target_net.parameters(), self.policy_net.parameters()
        ):
            target_param.data.copy_(
                self.tau * policy_param.data + (1 - self.tau) * target_param.data
            )

        # Decay epsilon
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)

        return {
            "loss": loss.item(),
            "epsilon": self.epsilon,
            "mean_td_error": np.abs(td_errors).mean(),
        }

    def calculate_trading_reward(
        self,
        action: int,
        price_change: float,
        position: float,
        sharpe_window: List[float],
    ) -> float:
        """
        Calculate Sharpe-ratio based reward.

        Uses rolling Sharpe ratio for reward shaping to encourage
        risk-adjusted returns.
        """
        # Base PnL
        if action == 0:  # Buy
            pnl = price_change * (1 - position)
        elif action == 2:  # Sell
            pnl = -price_change * (1 + position)
        else:  # Hold
            pnl = price_change * position

        # Update Sharpe window
        sharpe_window.append(pnl)
        if len(sharpe_window) > 20:
            sharpe_window.pop(0)

        # Sharpe-based reward
        if len(sharpe_window) >= 5:
            returns = np.array(sharpe_window)
            sharpe = returns.mean() / (returns.std() + 1e-8)
            reward = pnl + 0.1 * sharpe  # Add Sharpe bonus
        else:
            reward = pnl

        return reward

    def save(self, path: str) -> None:
        """Save model."""
        torch.save(
            {
                "policy_net_state_dict": self.policy_net.state_dict(),
                "target_net_state_dict": self.target_net.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "epsilon": self.epsilon,
                "total_steps": self.total_steps,
            },
            path,
        )
        _rl_logger.info(f"Enhanced DQN agent saved to {path}")

    def load(self, path: str) -> None:
        """Load model."""
        checkpoint = torch.load(path, map_location=self.device)
        self.policy_net.load_state_dict(checkpoint["policy_net_state_dict"])
        self.target_net.load_state_dict(checkpoint["target_net_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.epsilon = checkpoint.get("epsilon", self.epsilon_end)
        self.total_steps = checkpoint.get("total_steps", 0)
        _rl_logger.info(f"Enhanced DQN agent loaded from {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# RL Agent Factory
# ═══════════════════════════════════════════════════════════════════════════════


class RLAgentFactory:
    """Factory for creating RL agents."""

    @staticmethod
    def create(
        agent_type: str, state_dim: int = 20, action_dim: int = 3, **kwargs
    ) -> Any:
        """
        Create an RL agent.

        Args:
            agent_type: One of 'ppo', 'a2c', 'dqn'
            state_dim: State dimension
            action_dim: Action dimension
            **kwargs: Additional agent-specific arguments

        Returns:
            RL agent instance
        """
        agent_type = agent_type.lower()

        if agent_type == "ppo":
            return PPOAgent(state_dim=state_dim, action_dim=action_dim, **kwargs)
        elif agent_type == "a2c":
            return A2CAgent(state_dim=state_dim, action_dim=action_dim, **kwargs)
        elif agent_type == "dqn":
            return EnhancedDQNAgent(
                state_dim=state_dim, action_dim=action_dim, **kwargs
            )
        else:
            raise ValueError(
                f"Unknown agent type: {agent_type}. Use 'ppo', 'a2c', or 'dqn'"
            )


# Export public classes
__all__ = [
    "PPOAgent",
    "A2CAgent",
    "EnhancedDQNAgent",
    "PrioritizedReplayBuffer",
    "RLAgentFactory",
    "ActorNetwork",
    "CriticNetwork",
    "ActorCriticNetwork",
    "DuelingDQN",
]
