import redis
import os
import json
from dotenv import load_dotenv

load_dotenv()

r = redis.Redis(
    host=os.getenv('REDIS_HOST'),
    port=int(os.getenv('REDIS_PORT')),
    username=os.getenv('REDIS_USERNAME'),
    password=os.getenv('REDIS_PASSWORD'),
    decode_responses=True
)

print("=" * 80)
print("REDIS DATABASE DUMP")
print("=" * 80)

try:
    # Get all keys
    keys = r.keys("*")

    if not keys:
        print("No keys found in Redis database")
    else:
        print(f"Total keys: {len(keys)}\n")

        for key in sorted(keys):
            key_type = r.type(key)

            print(f"Key: {key}")
            print(f"Type: {key_type}")

            if key_type == "string":
                value = r.get(key)
                try:
                    # Try to parse as JSON for better formatting
                    parsed = json.loads(value)
                    print(f"Value: {json.dumps(parsed, indent=2)}")
                except:
                    print(f"Value: {value}")

            elif key_type == "set":
                value = r.smembers(key)
                print(f"Value: {value}")

            elif key_type == "list":
                value = r.lrange(key, 0, -1)
                print(f"Value: {value}")

            elif key_type == "hash":
                value = r.hgetall(key)
                print(f"Value: {json.dumps(value, indent=2)}")

            elif key_type == "zset":
                value = r.zrange(key, 0, -1, withscores=True)
                print(f"Value: {value}")

            print("-" * 80)

    print("\nDatabase stats:")
    print(f"Database size: {r.dbsize()} keys")

except Exception as e:
    print(f"Error: {e}")
