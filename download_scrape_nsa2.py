#!/usr/bin/env python3
"""
Download PDFs from the ACLU FOIA DB using aria2c quietly,
while showing a Rich progress bar for total progress.
"""

import os
import sys
import sqlite3
import argparse
import hashlib
from urllib.parse import urlparse, unquote
import subprocess
from rich.progress import Progress, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.console import Console

console = Console()


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------

def check_aria2_installed():
    try:
        subprocess.run(
            ["aria2c", "--version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
    except Exception:
        console.print("[bold red]ERROR:[/bold red] aria2c not found. Install aria2 first.")
        sys.exit(1)


def sanitize_filename(name: str, max_len=200):
    name = name.strip().replace("/", "_").replace("\\", "_")
    name = name.split("?")[0].split("#")[0]
    if len(name) > max_len:
        name = name[:max_len]
    return name


def basename_from_url(url: str):
    parsed = urlparse(url)
    name = os.path.basename(unquote(parsed.path or ""))
    return sanitize_filename(name if name else "file.pdf")


def unique_fname(rowid: int, url: str):
    base = basename_from_url(url)
    h = hashlib.sha1(url.encode()).hexdigest()[:8]
    return f"{rowid}_{h}_{base}"


# ---------------------------------------------------------------------
# Database Loading
# ---------------------------------------------------------------------

def load_rows(conn, include_duplicates=False):
    c = conn.cursor()
    if include_duplicates:
        q = """
            SELECT rowid, DirectPDF_Link, Year_From_URL
            FROM ACLU WHERE DirectPDF_Link IS NOT NULL AND DirectPDF_Link != ''
        """
    else:
        q = """
            SELECT rowid, DirectPDF_Link, Year_From_URL
            FROM ACLU WHERE DirectPDF_Link IS NOT NULL AND DirectPDF_Link != ''
            AND (Duplicate IS NULL OR Duplicate='No')
        """
    c.execute(q)
    return c.fetchall()


# ---------------------------------------------------------------------
# Download Logic
# ---------------------------------------------------------------------

def download_one(pdf_url, dest_path):
    """
    Download 1 file using aria2 silently.
    """
    cmd = [
        "aria2c",
        "--quiet=true",
        "--continue=true",
        "--file-allocation=none",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--dir", os.path.dirname(dest_path),
        "--out", os.path.basename(dest_path),
        pdf_url
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="ACLU_NSA_Snowden-D.db")
    parser.add_argument("--out", default="downloads")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--include-duplicates", action="store_true")
    args = parser.parse_args()

    check_aria2_installed()

    if not os.path.exists(args.db):
        console.print(f"[red]DB not found:[/red] {args.db}")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    rows = load_rows(conn, include_duplicates=args.include_duplicates)

    if not rows:
        console.print("[yellow]No records with DirectPDF_Link found.[/yellow]")
        return

    rows.sort(key=lambda x: (x[2] if x[2] else 9999, x[0]))
    total = len(rows)

    console.print(f"[green]Preparing to download {total} PDFs...[/green]\n")

    # Rich Progress Bar with live counters
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True
    ) as progress:

        task = progress.add_task(f"[0/{total}] Downloading PDFs...", total=total)
        completed = 0

        for rowid, pdf_url, year in rows:
            year_str = str(year if year is not None else "unknown")
            year_dir = os.path.join(args.out, year_str)
            os.makedirs(year_dir, exist_ok=True)

            fname = unique_fname(rowid, pdf_url)
            dest_path = os.path.join(year_dir, fname)

            # Skip if file exists
            if os.path.exists(dest_path) and not args.force:
                completed += 1
                progress.update(
                    task,
                    advance=1,
                    description=f"[{completed}/{total}] Downloading PDFs..."
                )
                continue

            # Download file
            try:
                download_one(pdf_url, dest_path)
            except Exception as e:
                console.print(f"[red]Failed:[/red] {pdf_url} ({e})")

            completed += 1
            progress.update(
                task,
                advance=1,
                description=f"[{completed}/{total}] Downloading PDFs..."
            )

    console.print("\n[bold green]All downloads completed.[/bold green]")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    main()
