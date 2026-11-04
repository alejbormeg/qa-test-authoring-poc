"""Lectura del DFF: .docx (párrafos y tablas en orden), .md o .txt."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


@dataclass
class Block:
    kind: str                       # "p" (párrafo) | "table"
    text: str = ""
    style: str = ""
    rows: list[list[str]] = field(default_factory=list)


def read_blocks(path: Path) -> list[Block]:
    if path.suffix.lower() in (".md", ".txt"):
        return [Block("p", line.rstrip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Formato no soportado: {path.suffix} (usa .docx, .md o .txt)")
    doc = Document(str(path))
    blocks: list[Block] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            if p.text.strip():
                blocks.append(Block("p", p.text.strip(), p.style.name if p.style is not None else ""))
        elif tag == "tbl":
            t = Table(child, doc)
            blocks.append(Block("table", rows=[[c.text.strip() for c in row.cells] for row in t.rows]))
    return blocks


def to_text(blocks: list[Block]) -> str:
    """Representación de texto fiel del documento para el modelo (tablas en Markdown)."""
    out: list[str] = []
    list_n = 0
    for b in blocks:
        if b.kind == "table":
            list_n = 0
            if not b.rows:
                continue
            width = max(len(r) for r in b.rows)
            rows = [r + [""] * (width - len(r)) for r in b.rows]
            fmt = lambda r: "| " + " | ".join(c.replace("\n", "<br>") for c in r) + " |"  # noqa: E731
            out += [fmt(rows[0]), "|" + "---|" * width, *[fmt(r) for r in rows[1:]], ""]
            continue
        style = b.style.lower()
        if style.startswith("heading") or style == "title":
            level = "".join(ch for ch in style if ch.isdigit()) or "1"
            out.append("#" * (int(level) + 1) + " " + b.text)
            list_n = 0
        elif "list number" in style:
            list_n += 1
            out.append(f"{list_n}. {b.text}")
        elif "list" in style:
            out.append(f"- {b.text}")
        else:
            list_n = 0
            out.append(b.text)
    return "\n".join(out)
