import pandas as pd
import requests
import json
import os

# File to cache the bulk data
bulk_cache_file = "scryfall_bulk_data.json"

# Check if bulk data needs to be downloaded
if not os.path.exists(bulk_cache_file):
    print("Downloading Scryfall bulk data...")
    bulk_url = "https://api.scryfall.com/bulk-data/default-cards"
    response = requests.get(bulk_url)
    bulk_data = response.json()
    download_url = bulk_data['download_uri']

    # Download and save the bulk card data
    bulk_response = requests.get(download_url)
    with open(bulk_cache_file, 'w') as f:
        json.dump(bulk_response.json(), f)

# Load the cached bulk data
with open(bulk_cache_file, 'r') as f:
    cards_data = json.load(f)
cards = {card['set'] + '-' + card['collector_number']: card for card in cards_data}

# Load the CSV
file_path = "moxfield_haves_2024-11-12-2021Z.csv"
output_path = "bulk_moxfield_haves_cleaned_updated.csv"
df = pd.read_csv(file_path)

# Remove unnecessary columns
columns_to_drop = ['Tradelist Count', 'Condition', 'Tags', 'Last Modified', 'Alter', 'Proxy', 'Purchase Price']
df.drop(columns=columns_to_drop, inplace=True, errors='ignore')  # Ignore if columns are missing

# Standardize the Foil column
df['Foil'] = df['Foil'].apply(lambda x: True if str(x).strip().lower() == 'foil' else False)

# Add new columns for Price and Group
df['Price'] = None
df['Group'] = None

# Update the DataFrame using bulk data
for index, row in df.iterrows():
    card_id = f"{row['Edition']}-{row['Collector Number']}"
    if card_id in cards:
        card_data = cards[card_id]
        color_identity = card_data.get('color_identity', [])
        card_type = card_data.get('type_line', '').lower()

        # Determine Group
        if "//" in card_type:
            if 'land' in card_type and 'land' in card_type.split(' // '):
                group = 'Land'
            else:
                group = 'Multicolored' if len(color_identity) > 1 else ', '.join(color_identity) if color_identity else 'Colorless'
        elif 'land' in card_type:
            group = 'Land'
        else:
            group = 'Multicolored' if len(color_identity) > 1 else ', '.join(color_identity) if color_identity else 'Colorless'

        # Get Pricing
        prices = card_data.get("prices", {})
        price = prices.get("usd_foil") if row['Foil'] else prices.get("usd")

        # Update DataFrame
        df.at[index, 'Price'] = price
        df.at[index, 'Group'] = group
    else:
        print(f"Card not found in bulk data: {row['Name']} ({row['Edition']} - {row['Collector Number']})")

# Save the updated DataFrame
df.to_csv(output_path, index=False)
print(f"Updated CSV saved to {output_path}")
