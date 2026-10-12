import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from storage.db import recent_counts


for token, chain, n, avg in recent_counts():
    print(f"{token:12} {chain:10} seen {n}x avg score {avg}")