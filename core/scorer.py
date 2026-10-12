import os
from goplus.token import Token
from core.socials import extract_socials


def score_pair(p):
    """Return (score 0-100, short reason) for a DEX Screener pair"""
    volume = (p.get("volume") or {}).get("h24") or 0
    liquidity = (p.get("liquidity") or {}).get("usd") or 0
    change = (p.get("priceChange") or {}).get("h24") or 0
    txns = (p.get("txns") or {}).get("h24") or {}
    buys = txns.get("buys", 0)
    sells = txns.get("sells", 0)

    if liquidity <= 0: return 0.0, "no liquidity"

    ratio = volume / liquidity
    score = 0.0
    notes = []

    # turnover is good up to ~10x, then it looks fake
    if ratio <= 10:
        score += min(35, ratio * 3.5)
    else:
        score += 35
        notes.append("suspicious turnover")

    # buy pressure (0-30): share of transactions that are buys
    total = buys + sells
    if total > 0:
        buy_share = buys / total
        score += max(0, ((buy_share - 0.4) / 0.3) * 30 if buy_share > 0.4 else 0)
        notes.append(f"{buy_share:.0%} buys")

    # price direction (0-25): rising is good, crashing is bad
    if change > 0:
        score += min(25, change / 4)
    elif change < -30:
        score -= 25
        notes.append("crashing")
    elif change < 0:
        score -= abs(change) / 3

    # liquidity safety (0-10): deeper pools are harder to rug
    score += min(10, liquidity / 10_000)

    # pump and dump penalities
    if ratio > 50:
        score -= 30
        notes.append("extreme ratio")
    if change > 500:
        score -= 20
        notes.append("parabolic")

    # general purpose security sdk check (using goplus.token)
    token_address = (p.get("baseToken") or {}).get("address", "")
    chain_id_raw = str(p.get("chainId", "")).lower()

    # dynamic mapping to turn DEX Screener text names into GoPlus SDK expected IDs
    chain_mapping = {
        "solana": "solana",
        "base": "8453",
        "ethereum": "1",
        "bsc": "56",
        "arbitrum": "42161",
        "optimism": "10",
        "avalanche": "43114",
        "polygon": "137"
    }

    goplus_chain = chain_mapping.get(chain_id_raw)

    if token_address and goplus_chain:
        try: 
            # querying via the official SDK 
            api_response = Token(access_token=None).token_security(
                chain_id=goplus_chain,
                addresses=[token_address],
                **{"_request_timeout": 10}
            )

            all_results = getattr(api_response, "result", {}) or {}
            result_data = all_results.get(token_address) or all_results.get(token_address.lower()) or {}

            if result_data:
                # cast metrics to strings to protect against mixed  int/str responses
                is_honeypot = str(result_data.get("is_honeypot")) == "1" or str(result_data.get("honeypot_with_same_creator")) == "1"
                cannot_buy = str(result_data.get("cannot_buy")) == "1"

                # check for active code minting/authority backdoors
                is_mintable = str(result_data.get("is_mintable")) == "1" or result_data.get("mint_authority") is not None

                if is_honeypot or cannot_buy:
                    score = 0.0
                    notes.append("HONEYPOT/CAN'T BUY")
                elif is_mintable:
                    score -= 45
                    notes.append("mint authority active")
        except Exception as e:
            notes.append(f"goplus-sdk error: {e}")

    # extract the token's socials
    socials = extract_socials(p)
    if not socials:
        score -= 10
        notes.append("no socials")
    else:
        score += min(10, len(socials) * 3)
        notes.append("socials: " + ",".join(sorted(socials)))

    score = max(0, min(100, score))
    return round(score, 1), f"vol/liq {ratio:.1f}x, change {change}%, " + ", ".join(notes)