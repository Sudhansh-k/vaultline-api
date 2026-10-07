import sqlite3, pandas as pd

conn = sqlite3.connect('market.db')

print('=== TABLES ===')
for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(r[0])

print('\n=== LISTINGS SAMPLE (5 rows) ===')
df = pd.read_sql_query('SELECT * FROM listings LIMIT 5', conn)
print(df.to_string())

print('\n=== AGGREGATE STATS ===')
stats = pd.read_sql_query('''
  SELECT
    COUNT(*) as total_listings,
    COUNT(DISTINCT item_id) as unique_items,
    COUNT(DISTINCT category) as categories,
    ROUND(AVG(days_to_sell),1) as avg_days,
    ROUND(AVG(sale_price),0) as avg_price,
    MIN(sale_date) as earliest,
    MAX(sale_date) as latest
  FROM listings WHERE sold=1
''', conn)
print(stats.to_string())

print('\n=== CATEGORIES ===')
cats = pd.read_sql_query('SELECT category, COUNT(*) as n FROM listings GROUP BY category', conn)
print(cats.to_string())

print('\n=== PER-ITEM SUMMARY (first 15) ===')
items = pd.read_sql_query('''
  SELECT item_id, category, COUNT(*) as n,
    ROUND(AVG(sale_price),0) as avg_price,
    ROUND(AVG(days_to_sell),1) as avg_days,
    image_path
  FROM listings
  GROUP BY item_id
  LIMIT 15
''', conn)
print(items.to_string())

print('\n=== ITEMS WITHOUT IMAGES ===')
no_img = pd.read_sql_query('''
  SELECT item_id FROM listings
  WHERE (image_path IS NULL OR image_path = '')
  GROUP BY item_id
''', conn)
print(no_img)

print('\n=== MARKET_TRENDS SAMPLE ===')
tr = pd.read_sql_query('SELECT * FROM market_trends LIMIT 5', conn)
print(tr.to_string())

conn.close()
