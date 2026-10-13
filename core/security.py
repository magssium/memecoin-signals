from goplus.token import Token
from storage.db import get_cached_security, save_security

CHAIN_MAP = {"solana": "solana", "base": "8453", "ethereum": "1", "bsc": "56",
             "arbitrum": "42161", "optimism": "10", "avalanche": "43114", "polygon": "137"}


def fetch_security(pairs):
    """Returns {(chain, address_lower): result_dict}. Uses the cache, then batches the rest."""
    out, missing = {}, {}
    for p in pairs:
        chain = p.get("chainId")
        addr = (p.get("baseToken") or {}).get("address")
        if not addr or chain not in CHAIN_MAP:
            continue
        key = (chain, addr.lower())
        cached = get_cached_security(chain, addr)
        if cached is not None:
            out[key] = cached
        else:
            missing.setdefault(chain, set()).add(addr)

    for chain, addrs in missing.items():
        addrs = list(addrs)
        for i in range(0, len(addrs), 20):
            chunk = addrs[i:i + 20]
            try:
                resp = Token(access_token=None).token_security(
                    chain_id=CHAIN_MAP[chain], addresses=chunk, **{"_request_timeout": 10}
                )
                results = getattr(resp, "result", {}) or {}
                for addr in chunk:
                    data = results.get(addr) or results.get(addr.lower())
                    if data:
                        out[(chain, addr.lower())] = data
                        save_security(chain, addr, data)
            except Exception as e:
                print(f"goplus error on {chain}: {e}")
    return out