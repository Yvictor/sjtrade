from typing import Union, Dict
from pathlib import Path


def read_position(filepath: Union[Path, str]) -> Dict[str, int]:
    p = Path(filepath)
    if p.exists() and p.is_file():
        content = p.read_text()
        return {
            r[0]: int(float(r[1]))
            for r in [l.split("\t") for l in content.split("\n") if l]
        }
    else:
        raise FileNotFoundError(f"filepath: '{filepath}' not exist.")


def read_csv_position(
    filepath: Union[Path, str], with_header: bool = True
) -> Dict[str, int]:
    p = Path(filepath)
    if p.exists() and p.is_file():
        content = p.read_text()
        return {
            r[0]: {
                "pos": int(float(r[1])),
                "stop_loss_tick": int(r[2]),
                "cover_pct": float(r[3]),
            }
            for r in [
                l.split(",") for l in content.split("\n")[int(with_header) :] if l
            ]
        }
    else:
        raise FileNotFoundError(f"filepath: '{filepath}' not exist.")
