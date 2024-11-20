import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import requests
import json
import os
import csv

# File to cache the bulk data
bulk_cache_file = "scryfall_bulk_data.json"

# Global list to store decklist cards
decklist_cards = []
current_file_path = None  # Tracks the currently selected collection file


def download_bulk_data():
    """Download and cache Scryfall bulk data."""
    print("Downloading Scryfall bulk data...")
    bulk_url = "https://api.scryfall.com/bulk-data/default-cards"
    response = requests.get(bulk_url)
    bulk_data = response.json()
    download_url = bulk_data['download_uri']

    # Download and save the bulk card data
    bulk_response = requests.get(download_url)
    with open(bulk_cache_file, 'w') as f:
        json.dump(bulk_response.json(), f)


def get_image_url(card_data):
    """Retrieve the PNG image URL for the card."""
    if card_data.get("layout") in ["split", "modal_dfc", "transform", "adventure", "flip", "reversible_card"]:
        if "card_faces" in card_data and isinstance(card_data["card_faces"], list):
            front_face = card_data["card_faces"][0]
            if "image_uris" in front_face:
                return front_face["image_uris"].get("png")
    return card_data.get("image_uris", {}).get("png")


def calculate_pce_score(rank, price):
    """Calculate the PCE Score (Power-Cost Efficiency) based on EDHREC rank and price."""
    try:
        rank = float(rank) if rank is not None else None
        price = float(price) if price is not None else None
        if rank and price and rank > 0 and price > 0:
            return price / rank
        return None
    except ValueError:
        return None


def process_card(card_entry):
    """
    Process a single line of card entry to extract relevant details.
    """
    parts = card_entry.split()
    count = parts[0]  # First part is the count
    foil = "*F*" in card_entry  # Check if the entry has a foil marker
    collector_number = parts[-1].replace("*F*", "").strip()  # Last part is the collector number

    if not collector_number.replace("-", "").isalnum():
        collector_number = parts[-2]
        edition_with_name = " ".join(parts[1:-2])
    else:
        edition_with_name = " ".join(parts[1:-1])
    
    # Extract edition (text inside parentheses)
    edition_start = edition_with_name.rfind("(")
    edition_end = edition_with_name.rfind(")")
    edition = edition_with_name[edition_start + 1:edition_end].strip() if edition_start != -1 and edition_end != -1 else ""

    # Extract name (everything before the edition)
    name = edition_with_name[:edition_start].strip() if edition_start != -1 else edition_with_name.strip()
    return [count, name, edition, foil, collector_number]


def convert_txt_to_csv(input_path, output_path):
    """
    Convert the text file into a CSV file.
    """
    with open(input_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    processed_cards = [process_card(line.strip()) for line in lines if line.strip()]

    with open(output_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Count", "Name", "Edition", "Foil", "Collector Number"])  # Header
        writer.writerows(processed_cards)

    print(f"Conversion completed. CSV saved at {output_path}")


def import_decklist(file_path):
    """
    Import a decklist file (TXT or CSV) and convert it to a format for processing.
    """
    global decklist_cards

    if file_path.endswith(".txt"):
        temp_csv_path = file_path.replace(".txt", "_converted.csv")
        convert_txt_to_csv(file_path, temp_csv_path)
        file_path = temp_csv_path

    # Now read the CSV and process it
    deck_df = pd.read_csv(file_path)
    for _, row in deck_df.iterrows():
        card_id = f"{row['Edition'].upper()}-{row['Collector Number']}"
        is_foil = str(row['Foil']).strip().lower() == "true"  # Explicitly convert to string before checking
        decklist_cards.append((card_id, is_foil))
    print(f"Imported decklist from {file_path} with {len(decklist_cards)} cards.")


def process_file(file_path, exclude_decklist=False):
    """Process the collection file, with an optional exclusion for decklist cards."""
    if not os.path.exists(bulk_cache_file):
        download_bulk_data()

    with open(bulk_cache_file, 'r') as f:
        cards_data = json.load(f)
    cards = {card['set'].upper() + '-' + card['collector_number']: card for card in cards_data}

    output_path = "CLEAN_moxfield.csv"
    df = pd.read_csv(file_path)

    columns_to_drop = ['Tradelist Count', 'Condition', 'Tags', 'Last Modified', 'Alter', 'Proxy', 'Purchase Price']
    df.drop(columns=columns_to_drop, inplace=True, errors='ignore')

    # Ensure proper handling of foil status
    df['Foil'] = df['Foil'].apply(
        lambda x: True if str(x).strip().lower() in ["true", "foil", "yes", "*f*"] else False
    )
    df['Price'] = None
    df['Group'] = None
    df['Image URL'] = None
    df['EDHREC Rank'] = None
    df['PCE Score'] = None

    if exclude_decklist:
        df['Card ID'] = df['Edition'].str.upper() + '-' + df['Collector Number'].astype(str).str.strip()
        df = df[~df.apply(lambda row: (row['Card ID'], row['Foil']) in decklist_cards, axis=1)].drop(columns=['Card ID'], errors='ignore')

    for index, row in df.iterrows():
        card_id = f"{row['Edition'].upper()}-{str(row['Collector Number']).strip()}"
        if card_id in cards:
            card_data = cards[card_id]
            color_identity = card_data.get('color_identity', [])
            card_type = card_data.get('type_line', '').lower()

            if 'land' in card_type:
                group = 'Land'
            else:
                group = 'Multicolored' if len(color_identity) > 1 else ', '.join(color_identity) if color_identity else 'Colorless'

            prices = card_data.get("prices", {})
            price = prices.get("usd_foil") if row['Foil'] else prices.get("usd")
            image_url = get_image_url(card_data)
            edhrec_rank = card_data.get('edhrec_rank', None)
            pce_score = calculate_pce_score(edhrec_rank, price)

            df.at[index, 'Price'] = price
            df.at[index, 'Group'] = group
            df.at[index, 'Image URL'] = image_url
            df.at[index, 'EDHREC Rank'] = edhrec_rank
            df.at[index, 'PCE Score'] = pce_score

    df.sort_values(by=['Group', 'PCE Score'], ascending=[True, False], inplace=True)
    df.to_csv(output_path, index=False)
    print(f"Updated CSV saved to {output_path}")
    messagebox.showinfo("Success", f"Updated CSV saved to {output_path}")


def open_file_dialog(exclusion_var):
    """Open a file dialog to select the input CSV."""
    global current_file_path
    file_path = filedialog.askopenfilename(
        title="Select Moxfield CSV File",
        filetypes=[("CSV files", "*.csv")]
    )
    if file_path:
        current_file_path = file_path
        process_file(file_path, exclude_decklist=exclusion_var.get())


def open_decklist_dialog():
    """Open a file dialog to select a decklist TXT or CSV file."""
    try:
        file_path = filedialog.askopenfilename(
            title="Select Decklist File",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")]
        )
        if file_path:
            import_decklist(file_path)
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while importing the decklist:\n{e}")


def toggle_exclusion(exclusion_var):
    """Reprocess the file with the exclusion toggle."""
    if current_file_path:
        process_file(current_file_path, exclude_decklist=exclusion_var.get())


def create_gui():
    """Create the GUI for the application."""
    root = tk.Tk()
    root.title("MTG Collection Processor")
    root.geometry("400x300")

    exclusion_var = tk.BooleanVar()

    tk.Label(root, text="MTG Collection Processor", pady=20).pack()

    tk.Button(root, text="Select Collection File", command=lambda: open_file_dialog(exclusion_var)).pack(pady=10)
    tk.Button(root, text="Import Decklist", command=open_decklist_dialog).pack(pady=10)

    tk.Checkbutton(
        root,
        text="Exclude Decklist Cards",
        variable=exclusion_var,
        command=lambda: toggle_exclusion(exclusion_var)
    ).pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    create_gui()

#TODO

# make it so it takes in deck lists to remove from the collection for the binder (Potentially with other program)
    #Use the CARSINDECK.py to convert moxfield deck lists into .csv
# make it so it sorts by group and than by PCE (Potentially do that with different program)