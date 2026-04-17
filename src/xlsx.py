from dataclasses import dataclass
from pathlib import Path

import openpyxl
from loguru import logger


@dataclass
class Row:
    number: str  # e.g. "1.1"
    prompt: str


def read_rows(path: Path) -> list[Row]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows: list[Row] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # header
        number, prompt, *_ = (*row, None, None)
        if not number or not prompt:
            continue
        rows.append(Row(number=str(number).strip(), prompt=str(prompt).strip()))
    wb.close()
    logger.debug("Read {} rows from {}", len(rows), path.name)
    return rows
