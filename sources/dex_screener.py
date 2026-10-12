import requests

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


if __name__ == "__main__":
    pairs = filter_pairs(search_pairs("PEPE"))
    for p in pairs[:10]:
        print(
            p["baseToken"]["symbol"],
            p["chainId"],
            p.get("priceUsd"),
            f"vol24h=${p['volume']['h24']:,.0f}",
            f"liq=${p['liquidity']['usd']:,.0f}",
            f"chg24h={p.get('priceChange', {}).get('h24')}%",
        )