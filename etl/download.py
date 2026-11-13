"""Download MovieLens 25M and unzip the 6 CSVs into data/raw/.

Usage:  python etl/download.py
Safe to re-run: skips the download if the zip is already present.
"""
import shutil
import urllib.request
import zipfile
from pathlib import Path

URL = "https://files.grouplens.org/datasets/movielens/ml-25m.zip"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ZIP_PATH = RAW / "ml-25m.zip"
FILES = ["movies.csv", "ratings.csv", "tags.csv", "links.csv",
         "genome-tags.csv", "genome-scores.csv"]


def download():
    if ZIP_PATH.exists():
        print(f"Zip already present: {ZIP_PATH}")
        return
    print(f"Downloading {URL} ...")
    tmp = ZIP_PATH.with_suffix(".part")
    with urllib.request.urlopen(URL) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 1024)
    tmp.rename(ZIP_PATH)
    print(f"Saved {ZIP_PATH.stat().st_size / 1e6:.1f} MB")


def extract():
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for member in zf.namelist():
            name = Path(member).name
            if name in FILES:
                target = RAW / name
                if not target.exists():
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    print(f"Extracted {name}")


def count_rows(path: Path) -> int:
    """Count data rows (lines minus header), reading in binary blocks."""
    n = 0
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            n += block.count(b"\n")
    return n - 1


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    download()
    extract()
    print(f"\n{'file':<20}{'rows':>14}{'MB':>10}")
    missing = []
    for name in FILES:
        p = RAW / name
        if not p.exists():
            missing.append(name)
            continue
        print(f"{name:<20}{count_rows(p):>14,}{p.stat().st_size / 1e6:>10.1f}")
    if missing:
        raise SystemExit(f"Missing files: {missing}")
    print("\nAll 6 files present.")


if __name__ == "__main__":
    main()
