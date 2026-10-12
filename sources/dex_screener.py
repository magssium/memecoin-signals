import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) 

import requests
from core.models import Signal

BASE_URL = "https://api.dexscreener.com"


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

        # simple starter score: volume relative to the liquidity, capped at 100
        score = min(100, (volume / liquidity) * 20)
        signals.append(Signal(
            source="dexscreener",
            token=p["baseToken"]["symbol"],
            chain=p["chainId"],
            score=round(score, 1),
            reason=f"vol/liq {volume / liquidity:.1f}x, 24h change {change}%",
            details=p
        ))
    return sorted(signals, key=lambda s: s.score, reverse=True) 


if __name__ == "__main__":
    pairs = filter_pairs(search_pairs("PEPE"))
    for s in pairs_to_signals(pairs)[:10]:
        print(s.token, s.chain, s.score, s.reason)