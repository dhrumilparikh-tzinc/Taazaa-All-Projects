import subprocess
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

DATASET = "pythonafroz/medquad-medical-question-answer-for-ai-research"  # MedQuAD slug

def main():
    cmd = [
        "kaggle", "datasets", "download",
        "-d", DATASET,
        "-p", str(DATA_DIR),
        "--unzip",
    ]
    subprocess.run(cmd, check=True)
    print("Download complete. Check the data/ folder.")

if __name__ == "__main__":
    main()