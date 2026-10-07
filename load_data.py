import pandas as pd
import sqlite3
import glob
from datetime import datetime

# Automatically find your scraped BrickLink CSV
csv_files = glob.glob("dataset_bricklink-scraper*.csv")
if not csv_files:
    raise FileNotFoundError("Could not find the BrickLink CSV in collectible_models folder!")

csv_path = csv_files[0]
df = pd.read_csv(csv_path)

conn = sqlite3.connect("market.db")
cursor = conn.cursor()

today = datetime.now().strftime("%Y-%m-%d")
records_added = 0

for idx, row in df.iterrows():
    # Clean the set ID and price
    raw_id = str(row.get('itemNo', '')).strip()
    if not raw_id or raw_id == 'nan':
        continue
        
    item_id = f"lego_{raw_id.replace('-', '_')}"
    
    # Extract price (fallback to usedAvgPrice if newAvgPrice is missing)
    price = pd.to_numeric(row.get('newAvgPrice'), errors='coerce')
    if pd.isna(price) or price <= 0:
        price = pd.to_numeric(row.get('usedAvgPrice'), errors='coerce')
    if pd.isna(price) or price <= 0:
        continue

    listing_id = f"{item_id}_{idx:04d}"
    image_url = str(row.get('imageUrl', ''))
    
    # Insert row matching the exact listings table schema
    cursor.execute("""
        INSERT INTO listings (
            listing_id, item_id, category, sale_price, 
            sale_date, days_to_sell, sold, image_path, condition_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (listing_id, item_id, 'lego', float(price), today, 15.0, 1, image_url, 9.0))
    
    records_added += 1

conn.commit()
conn.close()
print(f"Successfully ingested {records_added} sets from the dataset into market.db!")
