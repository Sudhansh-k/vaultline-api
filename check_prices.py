import sqlite3, pandas as pd, glob
c = sqlite3.connect("market.db")
print("rows:", c.execute("SELECT COUNT(*) FROM listings").fetchone()[0])
print("items:", c.execute("SELECT COUNT(DISTINCT item_id) FROM listings").fetchone()[0])
print(c.execute("SELECT item_id, COUNT(*) FROM listings GROUP BY item_id ORDER BY 2 DESC LIMIT 5").fetchall())

f = glob.glob("dataset_bricklink-scraper_*.csv")[0]
df = pd.read_csv(f)
print(df.loc[df["itemNo"] == "10188-1", ["itemName", "newAvgPrice", "usedAvgPrice", "newLots", "usedLots"]])
