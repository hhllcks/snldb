import pandas as pd
import numpy as np
import os

DATA_ROOT = 'output'

def create_csv(json_filename, csv_filename):
    print(f"Reading JSON file: {json_filename}")
    df = pd.read_json(json_filename, lines=True)
    print(f"Writing CSV file: {csv_filename}")
    df.to_csv(csv_filename, encoding="utf-8", index=False)

def create_csv_files(path):
    for file in os.listdir(path):
        if file.endswith(".json"):
            json_filename = DATA_ROOT + '/' + file
            csv_filename = os.path.splitext(json_filename)[0] + '.csv'
            create_csv(json_filename, csv_filename)

create_csv_files(DATA_ROOT)