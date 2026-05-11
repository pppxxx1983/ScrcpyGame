"""Reinforcement Learning optimizer stub (TODO #30).
Provides a lightweight multi-armed bandit / Q-table layer on top of
static runtime rules, allowing the agent to learn optimal action sequences.
"""
from __future__ import annotations

import json
import random
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from log_manager import LogManager


@dataclass
class ActionValue:
    q_value: float = 0.0
    visits: int = 0
    successes: int = 0
    failures: int = 0
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 0.5
        return self.successes / total

    def ucb_score(self, total_parent_visits: int, c: float = 1.414) -> float:
        if self.visits == 0:
            return float('inf')
        exploitation = self.q_value
        exploration = c * math.sqrt(math.log(total_parent_visits) / self.visits)
        return exploitation + exploration


@dataclass
class StateNode:
    state_key: str
    actions: Dict[str, ActionValue] = field(default_factory=dict)
    total_visits: int = 0


class RLOptimizer:
    """Simple tabular RL (Q-learning + UCB) for action selection."""

    def __init__(self, save_path: Path, alpha: float = 0.1, gamma: float = 0.9, epsilon: float = 0.1):
        self.save_path = save_path
        self.alpha = alpha      # learning rate
        self.gamma = gamma      # discount factor
        self.epsilon = epsilon  # exploration rate
        self.states: Dict[str, StateNode] = {}
        self._load()

    def _load(self):
        if self.save_path.exists():
            try:
                data = json.loads(self.save_path.read_text(encoding="utf-8"))
                for sk, node_data in data.get("states", {}).items():
                    node = StateNode(state_key=sk)
                    for ak, av_data in node_data.get("actions", {}).items():
                        node.actions[ak] = ActionValue(**av_data)
                    node.total_visits = node_data.get("total_visits", 0)
                    self.states[sk] = node
            except Exception as e:
                LogManager().append(f"[RL] load failed: {e}")

    def save(self):
        data = {
            "states": {
                sk: {
                    "actions": {
                        ak: {
                            "q_value": av.q_value,
                            "visits": av.visits,
                            "successes": av.successes,
                            "failures": av.failures,
                            "last_used": av.last_used,
                        }
                        for ak, av in node.actions.items()
                    },
                    "total_visits": node.total_visits,
                }
                for sk, node in self.states.items()
            }
        }
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        self.save_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def ensure_state(self, state_key: str) -> StateNode:
        if state_key not in self.states:
            self.states[state_key] = StateNode(state_key=state_key)
        return self.states[state_key]

    def select_action(self, state_key: str, available_actions: List[str]) -> Tuple[str, bool]:
        """Return (selected_action_key, is_exploration)."""
        if not available_actions:
            return ("", False)
        node = self.ensure_state(state_key)
        # Register missing actions
        for ak in available_actions:
            if ak not in node.actions:
                node.actions[ak] = ActionValue()

        # Epsilon-greedy with UCB fallback
        if random.random() < self.epsilon:
            chosen = random.choice(available_actions)
            return (chosen, True)

        # UCB selection among known actions
        best_action = None
        best_score = -float('inf')
        for ak in available_actions:
            av = node.actions[ak]
            score = av.ucb_score(node.total_visits)
            if score > best_score:
                best_score = score
                best_action = ak
        return (best_action, False) if best_action else (random.choice(available_actions), True)

    def update(self, state_key: str, action_key: str, reward: float, next_state_key: Optional[str] = None):
        """Standard Q-learning update."""
        node = self.ensure_state(state_key)
        av = node.actions.get(action_key)
        if av is None:
            av = ActionValue()
            node.actions[action_key] = av

        # Compute next best Q
        next_q = 0.0
        if next_state_key and next_state_key in self.states:
            next_node = self.states[next_state_key]
            if next_node.actions:
                next_q = max(a.q_value for a in next_node.actions.values())

        # TD update
        td_target = reward + self.gamma * next_q
        td_error = td_target - av.q_value
        av.q_value += self.alpha * td_error
        av.visits += 1
        av.last_used = __import__("time").time()
        node.total_visits += 1

        if reward > 0:
            av.successes += 1
        elif reward < 0:
            av.failures += 1

        self.save()

    def report(self) -> dict:
        total_states = len(self.states)
        total_actions = sum(len(s.actions) for s in self.states.values())
        avg_q = (
            sum(av.q_value for s in self.states.values() for av in s.actions.values()) / max(1, total_actions)
        )
        return {
            "states": total_states,
            "actions": total_actions,
            "avg_q": round(avg_q, 4),
            "file": str(self.save_path),
        }


class AdaptivePolicy:
    """High-level wrapper that combines Runtime Rules + RL weights (TODO #27 hybrid)."""

    def __init__(self, rl: RLOptimizer, rule_bonus: float = 0.1):
        self.rl = rl
        self.rule_bonus = rule_bonus

    def rank_actions(self, state_key: str, candidates: List[dict]) -> List[dict]:
        """Re-rank candidate actions using RL Q-values + rule confidence."""
        node = self.rl.ensure_state(state_key)
        scored = []
        for cand in candidates:
            ak = cand.get("rule_key") or cand.get("element_name") or "unknown"
            av = node.actions.get(ak)
            q = av.q_value if av else 0.0
            base_conf = cand.get("confidence", 0.5)
            # Blend rule confidence with learned Q
            blended = base_conf + self.rule_bonus * math.tanh(q)
            scored.append((blended, cand))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]
