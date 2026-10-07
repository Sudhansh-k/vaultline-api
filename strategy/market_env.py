"""Person 4 - Gymnasium market-making environment (one item category, one step = one day)."""
import gymnasium as gym
import numpy as np
from gymnasium import spaces

START_CAPITAL = 500_000.0
MAX_INVENTORY = 20
HORIZON = 90
HOLDING_RATE = 0.001           # 0.1% of FMV per item per day (storage + cost of capital)
MIN_SPREAD, MAX_SPREAD = 0.01, 0.40
LOW_CAPITAL_FRAC = 0.10
CAPITAL_PENALTY = 0.2          # in units of FMV, charged per day while capital is exhausted
SELLER_ARRIVAL_P = 0.5         # chance per day a customer offers us an item
LIQUIDATION_HAIRCUT = 0.80     # terminal mark-to-market of leftover stock


def spreads_from_action(a):
    a = np.clip(np.asarray(a, dtype=np.float32), 0.0, 1.0)
    return MIN_SPREAD + a * (MAX_SPREAD - MIN_SPREAD)


def make_obs(inventory, capital, fmv, days_to_sell):
    return np.array([inventory / MAX_INVENTORY, capital / START_CAPITAL,
                     min(fmv / 100_000, 5.0), min(days_to_sell / 60, 5.0)], dtype=np.float32)


class MarketMakerEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self):
        super().__init__()
        # action = [bid_spread, ask_spread] in [0,1] -> mapped to [1%, 40%] around FMV
        self.action_space = spaces.Box(0.0, 1.0, shape=(2,), dtype=np.float32)
        # state = [inventory depth, remaining capital, fair market value, expected days to sell]
        self.observation_space = spaces.Box(0.0, 5.0, shape=(4,), dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        r = self.np_random
        self.fmv = float(np.clip(r.lognormal(np.log(30_000), 0.7), 3_000, 150_000))
        self.days = float(r.uniform(5, 60))
        self.capital = START_CAPITAL
        self.inv = []                                        # cost basis per unit held
        for _ in range(int(r.integers(0, 9))):               # varied starting inventory
            cost = self.fmv * 0.8
            if self.capital >= cost:
                self.capital -= cost
                self.inv.append(cost)
        self.t = 0
        return self._obs(), {}

    def _obs(self):
        return make_obs(len(self.inv), self.capital, self.fmv, self.days)

    def step(self, action):
        r = self.np_random
        sb, sa = spreads_from_action(action)
        bid, ask = self.fmv * (1 - sb), self.fmv * (1 + sa)
        pnl = 0.0

        # 1) customer offers to sell to us; accepts if our bid beats their reservation price
        if r.random() < SELLER_ARRIVAL_P and len(self.inv) < MAX_INVENTORY and self.capital >= bid:
            reservation = self.fmv * r.normal(0.75, 0.10)
            if bid >= reservation:
                self.capital -= bid
                self.inv.append(bid)

        # 2) each held unit sells with a hazard that falls as our ask rises above FMV
        mult = float(np.clip(np.exp(-5.0 * (sa - 0.05)), 0.05, 2.0))
        p_sale = 1 - np.exp(-mult / self.days)
        kept = []
        for cost in self.inv:
            if r.random() < p_sale:
                self.capital += ask
                pnl += ask - cost                            # realized PnL
            else:
                kept.append(cost)
        self.inv = kept

        # 3) costs: holding cost per item-day + capital-exhaustion penalty
        holding = HOLDING_RATE * self.fmv * len(self.inv)
        penalty = CAPITAL_PENALTY * self.fmv if self.capital < LOW_CAPITAL_FRAC * START_CAPITAL else 0.0
        reward = pnl - holding - penalty

        self.fmv *= float(np.exp(r.normal(0, 0.01)))         # FMV random walk
        self.t += 1
        truncated = self.t >= HORIZON
        if truncated:                                        # mark leftover stock to market
            reward += sum(self.fmv * LIQUIDATION_HAIRCUT - c for c in self.inv)
        return self._obs(), float(reward / self.fmv), False, truncated, {}
