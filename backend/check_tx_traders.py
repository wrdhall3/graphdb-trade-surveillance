#!/usr/bin/env python3

# Simple query to check TX004 and TX005 trader associations

query = """
MATCH (t:Transaction)-[:PLACED_BY]->(trader:Trader)
WHERE t.transaction_id IN ['TX004', 'TX005']
RETURN t.transaction_id as transaction_id, 
       trader.trader_id as trader_id,
       t.status as status,
       t.timestamp as timestamp
ORDER BY t.transaction_id
"""

print("🔍 CHECKING TX004 AND TX005 TRADER ASSOCIATIONS")
print("=" * 50)
print("\nQuery to run in Neo4j browser:")
print(query)
print("\nExpected if same trader:")
print("  TX004 -> TR002")
print("  TX005 -> TR002")
print("\nIf different traders:")
print("  TX004 -> TR002 (explains why only TX004 shows in TR002's spoofing pattern)")
print("  TX005 -> TR001 (would show in TR001's spoofing pattern)")
print("\nThis would explain why only TX004 appears - they're separate patterns!") 