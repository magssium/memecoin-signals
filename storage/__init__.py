import time
import requests

# Base configuration
BASE_URL = "https://api.geckoterminal.com/api/v2/networks/new_pools"
HEADERS = {"Accept": "application/json;version=20230203"}
# 'include=base_token' loads full token info (symbol, address, etc.) along with the pool
PARAMS = {"include": "base_token"} 

# Set to keep track of already processed pools so we don't duplicate logs
seen_pools = set()

def check_new_tokens():
    print("📡 Fetching latest token pools from GeckoTerminal...")
    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=PARAMS)
        
        if response.status_code == 429:
            print("⚠️ Rate limit hit. Waiting a bit longer...")
            return

        if response.status_code != 200:
            print(f"❌ Error fetching data: {response.status_code}")
            return
            
        json_data = response.json()
        pools = json_data.get("data", [])
        
        # Build a lookup dictionary for included token metadata strings
        included_data = json_data.get("included", [])
        tokens_meta = {
            item["id"]: item["attributes"] 
            for item in included_data if item["type"] == "token"
        }

        new_discoveries = 0

        for pool in pools:
            pool_id = pool.get("id")
            
            # Skip if we already saw this pool in a previous iteration
            if pool_id in seen_pools:
                continue
                
            seen_pools.add(pool_id)
            new_discoveries += 1
            
            pool_attrs = pool.get("attributes", {})
            pool_name = pool_attrs.get("name", "Unknown Pair")
            pool_address = pool_attrs.get("address")
            created_at = pool_attrs.get("pool_created_at", "N/A")
            reserve_usd = pool_attrs.get("reserve_in_usd", "0")

            # Extract specific base token details
            base_token_relationship = pool.get("relationships", {}).get("base_token", {}).get("data", {})
            base_token_id = base_token_relationship.get("id")
            
            token_name = "Unknown"
            token_symbol = "Unknown"
            token_address = "Unknown"
            
            if base_token_id in tokens_meta:
                meta = tokens_meta[base_token_id]
                token_name = meta.get("name")
                token_symbol = meta.get("symbol")
                token_address = meta.get("address")

            # Print the token check breakdown
            print("-" * 50)
            print(f"🔥 NEW TOKEN POOL DETECTED!")
            print(f"🪙 Token Name: {token_name} ({token_symbol})")
            print(f"🔗 Token Address: {token_address}")
            print(f"📊 Pair: {pool_name}")
            print(f"📍 Pool Contract: {pool_address}")
            print(f"💰 Initial Liquidity: ${float(reserve_usd):,.2f} USD" if reserve_usd else "💰 Initial Liquidity: $0.00")
            print(f"⏰ Deployed At: {created_at}")

        if new_discoveries == 0:
            print("💤 No new tokens found in this check.")
            
    except Exception as e:
        print(f"⚠️ An anomaly occurred: {e}")

if __name__ == "__main__":
    print("🚀 Starting GeckoTerminal Token Live Monitor...")
    print("Press Ctrl+C to stop the script.\n")
    
    # GeckoTerminal updates public data roughly every 60 seconds.
    # Polling faster than 60 seconds will result in 429 rate limit exceptions.
    CHECK_INTERVAL = 65 

    while True:
        check_new_tokens()
        print(f"⏱️ Sleeping for {CHECK_INTERVAL} seconds before next check...\n")
        time.sleep(CHECK_INTERVAL)
