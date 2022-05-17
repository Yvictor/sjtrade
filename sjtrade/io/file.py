from typing import Union
from pathlib import Path


def read_position(filepath: Union[Path, str]):
    p = Path(filepath)
    if p.exists() and p.is_file():
        content = p.read_text()
        return {
            r[0]: int(float(r[1]))
            for r in [l.split("\t") for l in content.split("\n") if l]
        }
    else:
        raise FileNotFoundError(f"filepath: '{filepath}' not exist.")
