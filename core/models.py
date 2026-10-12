from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Signal:
    source: str  # "dexscreener", "whales", "politicians", "twitter"
    token: str   # symbol, e.g: "PEPE" 
    chain: str  # "solana", "ethereum", etc
    score: float  # 0-100, how strong the signal is 
    reason: str  # short human readable explanation
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict = field(default_factory=dict)  # raw extra data