#!/usr/bin/env python3

from pathlib import Path
from urllib.request import urlretrieve
from urllib.error import HTTPError, URLError

# CMU MoCap uses ASF (skeleton) + AMC (motion) files. The public site exposes
# subject-based downloads, and CMU also notes on its FAQ that there is a zip of
# all ASF/AMC files if you want the whole archive instead of selected motions.
# This script is for downloading only the motions you care about.

BASE_URL = "https://mocap.cs.cmu.edu/subjects"

# Pick the subject and trial files you want.
# Format:
#   "SUBJECT": ["TRIAL", "TRIAL", ...]
#
# Example trial file path:
#   https://mocap.cs.cmu.edu/subjects/01/01_01.amc
# Example skeleton file path:
#   https://mocap.cs.cmu.edu/subjects/01/01.asf
#
# Replace these with the stair-climbing motions you choose from the CMU site.
SELECTION = {
    "01": ["01", "02"],
    # "13": ["15", "16"],
}

OUT_DIR = Path("cmu_mocap_selected")


def download_file(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"skip  {dest}")
        return True

    try:
        print(f"get   {url}")
        urlretrieve(url, dest)
        print(f"saved {dest}")
        return True
    except HTTPError as e:
        print(f"HTTP error for {url}: {e.code}")
    except URLError as e:
        print(f"URL error for {url}: {e.reason}")
    except Exception as e:
        print(f"Error for {url}: {e}")
    return False


def download_subject(subject: str, trials: list[str]) -> None:
    subject = subject.zfill(2)
    subject_dir = OUT_DIR / subject

    # Download skeleton once per subject
    asf_url = f"{BASE_URL}/{subject}/{subject}.asf"
    asf_dest = subject_dir / f"{subject}.asf"
    download_file(asf_url, asf_dest)

    # Download requested motion files
    for trial in trials:
        trial = trial.zfill(2)
        amc_url = f"{BASE_URL}/{subject}/{subject}_{trial}.amc"
        amc_dest = subject_dir / f"{subject}_{trial}.amc"
        download_file(amc_url, amc_dest)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for subject, trials in SELECTION.items():
        download_subject(subject, trials)

    print("\nDone.")
    print(f"Files saved under: {OUT_DIR.resolve()}")
    print("Next step: parse ASF/AMC and extract hip, knee, and ankle joint angles.")


if __name__ == "__main__":
    main()