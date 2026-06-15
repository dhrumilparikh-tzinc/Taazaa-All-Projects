import pandas as pd
from pathlib import Path

def main():
    data_dir = Path("data")

    # Print all files in data/ so we see actual names
    print("Files in data/:")
    for p in data_dir.iterdir():
        print(" -", p)

    # TODO: Update this after you see the real filename
    csv_path = data_dir / "medquad.csv"  # placeholder, will adjust
    if not csv_path.exists():
        print("Update csv_path to match the actual file name from above.")
        return

    df = pd.read_csv(csv_path)
    print("Columns:", df.columns.tolist())
    print(df.head(3))

if __name__ == "__main__":
    main()