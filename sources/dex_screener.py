import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) 

import requests
import argparse
from core.models import Signal
from storage.db import save_signals

BASE_URL = "https://api.dexscreener.com"
ENDPOINTS = {
    "profile": "/token-profiles/latest/v1",
    "boosted": "/token-boosts/latest/v1",
    "top_boosted": "/token-boosts/top/v1",
    "takeover": "/community-takeovers/latest/v1",
}


def search_pairs(query: str):
    r = requests.get(f"{BASE_URL}/latest/dex/search", params={"q": query}, timeout=10)
    r.raise_for_status()
    return r.json().get("pairs", [])


def filter_pairs(pairs, min_liquidity=50_000, min_volume=100_000):
    good = []
    for p in pairs:
        liquidity = (p.get("liquidity") or {}).get("usd") or 0
        volume = (p.get("volume") or {}).get("h24") or 0
        if liquidity >= min_liquidity and volume >= min_volume:
            good.append(p)
    return sorted(good, key=lambda p: p["volume"]["h24"], reverse=True)


def pairs_to_signals(pairs):
    signals = []
    for p in pairs:
        volume = p["volume"]["h24"]
        liquidity = p["liquidity"]["usd"]
        change = (p.get("priceChange") or {}).get("h24") or 0

        txns = (p.get("txns") or {}).get("h24") or {}
        buys = txns.get("buys", 0)
        sells = txns.get("sells", 0)

        # simple starter score: volume relative to the liquidity, capped at 100
        score = min(100, (volume / liquidity) * 20)
        signals.append(Signal(
            source="dexscreener",
            token=p["baseToken"]["symbol"],
            chain=p["chainId"],
            score=round(score, 1),
            reason=f"vol/liq {volume/liquidity:.1f}x, 24h change {change}%, buys {buys} / sells {sells}",
            details=p
        ))
    return sorted(signals, key=lambda s: s.score, reverse=True) 


def get_new_tokens(chain=None):
    """Tokens from several DEX Screener lists, tagged by origin."""
    found = {}
    for label, path in ENDPOINTS.items():
        try:
            r = requests.get(BASE_URL + path, timeout=10)
            r.raise_for_status()
            items = r.json()
        except Exception as e:
            print(f"skipped {label}: {e}")
            continue
        for t in items:
            if "chainId" not in t or "tokenAddress" not in t:
                continue
            if chain and t["chainId"] != chain:
                continue
            key = (t["chainId"], t["tokenAddress"].lower())
            entry = found.setdefault(key, {**t, "tags": set()})
            entry["tags"].add(label)
    return list(found.values())


def get_pairs_for_tokens(tokens):
    addresses = [t["tokenAddress"] for t in tokens]
    pairs = []
    for i in range(0, len(addresses), 30):
        chunk = ",".join(addresses[i:i + 30])
        r = requests.get(f"{BASE_URL}/latest/dex/tokens/{chunk}", timeout=10)
        r.raise_for_status()
        pairs.extend(r.json().get("pairs") or [])
    return pairs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=15, help="how many results to show")
    parser.add_argument("--chain", default=None, help="e.g. solana, ethereum, base")
    parser.add_argument("--min-liq", type=float, default=5_000)
    parser.add_argument("--min-vol", type=float, default=10_000)
    args = parser.parse_args()

    tokens = get_new_tokens(chain=args.chain)
    tag_lookup = {(t["chainId"], t["tokenAddress"].lower()): t["tags"] for t in tokens}
    print(f"Found {len(tokens)} tokens")

    pairs = get_pairs_for_tokens(tokens)
    pairs = filter_pairs(pairs, min_liquidity=args.min_liq, min_volume=args.min_vol)
    signals = pairs_to_signals(pairs)
    saved = save_signals(signals)
    print(f"Saved {saved} signals to database")

    for s in signals[:args.limit]:
        addr = s.details["baseToken"]["address"].lower()
        tags = ",".join(sorted(tag_lookup.get((s.chain, addr), []))) or "?"
        print(f"[{tags}]", s.token, s.chain, s.score, s.reason)