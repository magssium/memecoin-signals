def extract_socials(p):
    """Pull website/twitter/telegram/etc. out of a DEX Screener pair."""
    info = p.get("info") or {}
    socials = {}

    websites = info.get("websites") or []
    if websites and websites[0].get("url"):
        socials["website"] = websites[0]["url"]

    for s in info.get("socials") or []:
        kind = (s.get("type") or "").lower()
        if kind and s.get("url"):
            socials.setdefault(kind, s["url"])

    return socials