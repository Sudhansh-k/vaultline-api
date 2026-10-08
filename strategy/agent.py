"""Person 4 - PPO training + generate_quotes().

  python -m strategy.agent train 300000
  python -m strategy.agent eval
"""
import os
import sys
import numpy as np

# NOTE: stable_baselines3 (and therefore PyTorch) is imported lazily inside the
# functions below, so the API server can run the heuristic without installing torch.
from strategy.market_env import (MarketMakerEnv, MAX_INVENTORY, START_CAPITAL,
                                 make_obs, spreads_from_action)

MODEL_PATH = "strategy/mm_ppo"


def train(timesteps=300_000):
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env
    env = make_vec_env(MarketMakerEnv, n_envs=4)
    model = PPO("MlpPolicy", env, n_steps=512, batch_size=256, learning_rate=3e-4,
                gamma=0.99, ent_coef=0.005, verbose=1)
    model.learn(timesteps)
    model.save(MODEL_PATH)


def evaluate(n_episodes=50):
    """Compare trained PPO against a fixed-spread baseline (mean episode reward, FMV-normalised)."""
    from stable_baselines3 import PPO
    model = PPO.load(MODEL_PATH)
    env = MarketMakerEnv()
    for name, policy in {"PPO": lambda o: model.predict(o, deterministic=True)[0],
                         "fixed (bid 25% / ask 10%)": lambda o: np.array([0.6, 0.2])}.items():
        totals = []
        for ep in range(n_episodes):
            obs, _ = env.reset(seed=ep)
            done, total = False, 0.0
            while not done:
                obs, r, term, trunc, _ = env.step(policy(obs))
                total += r
                done = term or trunc
            totals.append(total)
        print(f"{name:28s} mean={np.mean(totals):8.3f}  std={np.std(totals):.3f}")


_model = None


def generate_quotes(fair_value, days_to_sell, current_inventory, capital=START_CAPITAL):
    """-> (bid_price, ask_price, action_label). Falls back to a heuristic if no trained model exists."""
    global _model
    if _model is None and os.path.exists(MODEL_PATH + ".zip"):
        try:
            from stable_baselines3 import PPO          # only needed if a trained model exists
            _model = PPO.load(MODEL_PATH)
        except ImportError:
            _model = None                              # torch not installed -> use heuristic

    if _model is not None:
        obs = make_obs(current_inventory, capital, fair_value, days_to_sell)
        a, _ = _model.predict(obs, deterministic=True)
        sb, sa = (float(x) for x in spreads_from_action(a))
    else:  # widen with inventory, scarce capital, slow-moving items
        inv, cap = current_inventory / MAX_INVENTORY, capital / START_CAPITAL
        sb = float(np.clip(0.10 + 0.20 * inv + 0.10 * (1 - cap) + 0.05 * days_to_sell / 60, 0.01, 0.40))
        sa = float(np.clip(0.05 + 0.10 * inv + 0.05 * days_to_sell / 60, 0.01, 0.40))

    bid, ask = float(fair_value) * (1 - sb), float(fair_value) * (1 + sa)
    if current_inventory >= MAX_INVENTORY or capital < bid:
        return 0.0, round(float(ask), 2), "STOP_BUYING"
    label = "NARROW" if (sb + sa) / 2 < 0.12 else "WIDE" if (sb + sa) / 2 > 0.25 else "NORMAL"
    return round(float(bid), 2), round(float(ask), 2), label


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "train":
        train(int(sys.argv[2]) if len(sys.argv) > 2 else 300_000)
    elif cmd == "eval":
        evaluate()
    else:
        print(__doc__)
