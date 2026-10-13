import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) 

import requests
import argparse
import time
from core.models import Signal
from core.scorer import score_pair
from core.socials import extract_socials
from storage.db import save_signals, known_tokens, upsert_tokens

BASE_URL = "https://api.dexscreener.com"
ENDPOINTS = {
    "profile": "/token-profiles/latest/v1",
    "boosted": "/token-boosts/latest/v1",
    "top_boosted": "/token-boosts/top/v1",
    "takeover": "/community-takeovers/latest/v1",
}


GT_BASE = "https://api.geckoterminal.com/api/v2"
GT_NETWORKS = {"solana": "solana", "ethereum": "eth", "base": "base", "bsc": "bsc"}  # dexscreener id -> geckoterminal id


def _gt_get(url, params=None, retries=3):
    """GET with backoff on 429. Returns parsed JSON or None."""
    delay = 5
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", delay))
                print(f"  geckoterminal 429, waiting {wait}s (try {attempt + 1}/{retries})")
                time.sleep(wait)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  geckoterminal error: {e}")
            return None
    return None


def get_geckoterminal_new(chain=None, pages=1):
    """Newest pools from GeckoTerminal, shaped like get_promoted_tokens."""
    found = {}
    for ds_chain, gt_chain in GT_NETWORKS.items():
        if chain and ds_chain != chain:
            continue
        for page in range(1, pages + 1):
            body = _gt_get(f"{GT_BASE}/networks/{gt_chain}/new_pools", params={"page": page})
            if body is None:
                break
            for pool in body.get("data", []):
                base_id = pool["relationships"]["base_token"]["data"]["id"]
                address = base_id.split("_", 1)[1]
                key = (ds_chain, address.lower())
                entry = found.setdefault(
                    key, {"chainId": ds_chain, "tokenAddress": address, "tags": set()}
                )
                entry["tags"].add("new_pool")
            time.sleep(6)   # ~10 calls/min, well under the limit
    return list(found.values())

def get_all_tokens(chain=None):
    by_key = {}
    sources = [get_promoted_tokens, get_geckoterminal_new]
    for fetch in sources:
        for t in fetch(chain=chain):
            key = (t["chainId"], t["tokenAddress"].lower())
            if key in by_key:
                by_key[key]["tags"] |= t["tags"]   # same token in both: merge tags
            else:
                by_key[key] = t
    return list(by_key.values())



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


def filter_by_age(pairs, min_hours=None, max_hours=None):
    """Keep pairs whose age in hours is within [min_hours, max_hours]"""
    now_ms = time.time() * 1000
    kept = []
    for p in pairs:
        created = p.get("pairCreatedAt")
        if not created: continue

        age = (now_ms - created) / 3_600_000
        if min_hours is not None and age < min_hours: continue
        if max_hours is not None and age > max_hours: continue  

        kept.append(p)
    return kept



def pairs_to_signals(pairs):
    signals = []
    for p in pairs:
        score, reason = score_pair(p)
        signals.append(Signal(
            source="dexscreener",
            token=p["baseToken"]["symbol"],
            chain=p["chainId"],
            score=score,
            reason=reason,
            details={**p, "socials": extract_socials(p)}
        ))
    return sorted(signals, key=lambda s: s.score, reverse=True)


def get_promoted_tokens(chain=None):
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


def sig_key(s):
    return (s.chain, s.details["baseToken"]["address"].lower())


def scan_round(args, tag_lookup):
    """One full discovery pass. Returns one signal per token (best pool)."""
    tokens = get_all_tokens(chain=args.chain)
    for t in tokens:
        tag_lookup[(t["chainId"], t["tokenAddress"].lower())] = t["tags"]

    pairs = get_pairs_for_tokens(tokens)
    if args.min_age is not None or args.max_age is not None:
        pairs = filter_by_age(pairs, min_hours=args.min_age, max_hours=args.max_age)
    pairs = filter_pairs(pairs, min_liquidity=args.min_liq, min_volume=args.min_vol)

    best = {}
    for s in pairs_to_signals(pairs):   # already sorted best-first
        best.setdefault(sig_key(s), s)
    return list(best.values())


def rating(score):
    if score >= 75: return "STRONG"
    if score >= 55: return "DECENT"
    if score >= 35: return "WEAK"
    return "AVOID"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=15, help="how many results to show")
    parser.add_argument("--count", type=int, default=0, help="keep scanning until N NEW tokens are found (0 = single pass)")
    parser.add_argument("--wait", type=int, default=180, help="seconds to wait between rounds")
    parser.add_argument("--max-rounds", type=int, default=30, help="safety cap on number of rounds")
    parser.add_argument("--chain", default=None, help="e.g. solana, ethereum, base, bsc")
    parser.add_argument("--min-liq", type=float, default=2_000)
    parser.add_argument("--min-vol", type=float, default=2_000)
    parser.add_argument("--max-age", type=float, default=None, help="only pairs younger than N hours")
    parser.add_argument("--min-age", type=float, default=None, help="only pairs older than N hours")
    args = parser.parse_args()

    tag_lookup = {}
    new_found = []
    signals = []
    stale_rounds = 0
    rounds = args.max_rounds if args.count else 1

    try:
        for rnd in range(1, rounds + 1):
            signals = scan_round(args, tag_lookup)

            known = known_tokens()
            new_sigs = [s for s in signals if sig_key(s) not in known]
            updated = len(signals) - len(new_sigs)

            upsert_tokens(signals)     # inserts new, updates existing
            save_signals(signals)      # history row for this scan
            new_found.extend(new_sigs)

            print(f"Round {rnd}: {len(signals)} passed filters | "
                  f"{len(new_sigs)} new, {updated} updated | "
                  f"total new: {len(new_found)}/{args.count or '-'}")

            if not args.count or len(new_found) >= args.count:
                break

            stale_rounds = stale_rounds + 1 if not new_sigs else 0
            if stale_rounds >= 3:
                print("No new tokens in 3 rounds in a row, stopping.")
                break

            print(f"Waiting {args.wait}s for the lists to refresh...")
            time.sleep(args.wait)
    except KeyboardInterrupt:
        print("\nStopped by user. Showing what was collected so far.")

    # show new tokens if we were collecting, otherwise everything from the pass
    to_show = new_found if args.count else signals
    to_show = sorted(to_show, key=lambda s: s.score, reverse=True)

    print("\n" + "=" * 70)
    for s in to_show[:args.limit]:
        tags = ",".join(sorted(tag_lookup.get(sig_key(s), []))) or "?"
        filled = int(s.score // 10)
        bar = "█" * filled + "░" * (10 - filled)

        print(f"SCORE: {s.score:>5.1f} {bar} {rating(s.score)}")
        print(f"  {s.token} ({s.chain}) [{tags}]")
        print(f"  {s.reason}")
        for kind, url in s.details.get("socials", {}).items():
            print(f"      {kind}: {url}")
        print("-" * 70)