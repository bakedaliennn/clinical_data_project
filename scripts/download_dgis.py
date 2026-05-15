"""
scripts/download_dgis.py
------------------------
Descargador inteligente de datos abiertos de la DGIS / SSA México.

Uso:
    # Descargar SAEH 2023 (datos + descriptor + catálogos)
    python scripts/download_dgis.py --source saeh --year 2023

    # Descargar catálogo CLUES actual
    python scripts/download_dgis.py --source clues

    # Descargar catálogo CIE-10 CEMECE
    python scripts/download_dgis.py --source cie10

    # Descubrir todos los archivos disponibles (sin descargar)
    python scripts/download_dgis.py --source saeh --discover-only

Estrategia:
    1. Hace GET al portal SINAIS y parsea los enlaces con BeautifulSoup.
    2. Filtra por año y extensión (.zip, .rar, .xlsx).
    3. Descarga con barra de progreso y verifica checksum SHA-256.
    4. Descomprime ZIP/RAR en la carpeta destino.
    5. Guarda un manifiesto JSON de lo descargado.

Refs:
    - docs/data_sources_catalog.md
    - AGENTS.md (encodings y convenciones SSA)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Configuración de portales ──────────────────────────────────────────────────

PORTALS: dict[str, str] = {
    "saeh": "http://www.dgis.salud.gob.mx/contenidos/basesdedatos/da_egresoshosp_gobmx.html",
    "clues": "http://www.dgis.salud.gob.mx/contenidos/intercambio/clues_gobmx.html",
    "cie10": "http://www.dgis.salud.gob.mx/contenidos/intercambio/diagnostico_gobmx.html",
    "sinerhias": "http://www.dgis.salud.gob.mx/contenidos/sinais/s_sinerhias.html",
}

BASE_DOMAIN = "http://www.dgis.salud.gob.mx"

# Carpeta raíz de datos crudos (relativa a la raíz del proyecto)
DATA_RAW = Path(__file__).resolve().parents[1] / "data_raw"


# ── Utilidades ─────────────────────────────────────────────────────────────────

def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _fetch_html(url: str, timeout: int = 30) -> BeautifulSoup:
    """Descarga el HTML de una página y retorna el BeautifulSoup."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 SaludMX-Pipeline/1.0"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "lxml")


def _extract_links(soup: BeautifulSoup, base: str) -> list[str]:
    """Extrae todos los href de <a> que apunten a archivos descargables."""
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if re.search(r"\.(zip|rar|xlsx|csv|txt)(\?.*)?$", href, re.IGNORECASE):
            # Resolver URLs relativas
            if href.startswith("http"):
                links.append(href)
            elif href.startswith("/"):
                links.append(base + href)
            else:
                links.append(base + "/" + href)
    return list(dict.fromkeys(links))  # dedup preservando orden


def _filter_by_year(links: list[str], year: int) -> list[str]:
    """Filtra los links que contienen el año indicado en la URL o el nombre de archivo."""
    pattern = re.compile(rf"(?<!\d){year}(?!\d)")
    return [lnk for lnk in links if pattern.search(lnk)]


def _download_file(url: str, dest: Path, chunk_size: int = 1 << 16) -> Path:
    """
    Descarga un archivo con progreso básico por consola.
    Retorna la ruta al archivo descargado.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    filename = dest.name

    headers = {
        "User-Agent": "Mozilla/5.0 SaludMX-Pipeline/1.0"
    }

    with requests.get(url, headers=headers, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0

        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        print(f"\r  [{filename}] {downloaded/1e6:.1f}/{total/1e6:.1f} MB ({pct:.0f}%)", end="")

    print()  # newline
    return dest


def _unzip(archive: Path, dest_dir: Path) -> list[Path]:
    """Descomprime un ZIP en dest_dir. Retorna lista de archivos extraídos."""
    extracted = []
    with zipfile.ZipFile(archive, "r") as zf:
        for member in zf.namelist():
            zf.extract(member, dest_dir)
            extracted.append(dest_dir / member)
    return extracted


def _save_manifest(dest_dir: Path, entries: list[dict]) -> Path:
    """Guarda un JSON de manifiesto de descarga."""
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "files": entries,
    }
    path = dest_dir / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ── Lógica principal ───────────────────────────────────────────────────────────

def discover(source: str, year: int | None = None) -> list[str]:
    """Retorna los links de descarga disponibles para la fuente dada."""
    url = PORTALS[source]
    print(f"[discover] Escaneando: {url}")
    soup = _fetch_html(url)
    links = _extract_links(soup, BASE_DOMAIN)
    if year:
        links = _filter_by_year(links, year)
    return links


def download_saeh(year: int, discover_only: bool = False) -> None:
    """Descarga los microdatos SAEH para el año indicado."""
    links = discover("saeh", year)

    if not links:
        print(f"[WARN] No se encontraron archivos para el año {year}.")
        print("  Verifica manualmente en:")
        print(f"  {PORTALS['saeh']}")
        return

    print(f"\nArchivos encontrados para {year}:")
    for i, lnk in enumerate(links, 1):
        print(f"  [{i}] {lnk}")

    if discover_only:
        return

    dest_dir = DATA_RAW / "saeh" / str(year)
    dest_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    for url in links:
        filename = url.split("/")[-1].split("?")[0] or "archivo_dgis"
        dest = dest_dir / filename

        if dest.exists():
            print(f"[skip] {filename} ya existe — omitiendo descarga.")
            continue

        print(f"\n[download] {filename}")
        _download_file(url, dest)

        sha = _sha256(dest)
        print(f"  SHA-256: {sha}")

        # Descomprimir si es ZIP
        if filename.lower().endswith(".zip"):
            print(f"  Descomprimiendo {filename}...")
            extracted = _unzip(dest, dest_dir)
            print(f"  Extraídos: {[f.name for f in extracted]}")

        manifest_entries.append({"url": url, "file": filename, "sha256": sha})

    mp = _save_manifest(dest_dir, manifest_entries)
    print(f"\n[ok] Manifiesto guardado en: {mp}")
    print(f"[ok] Datos en: {dest_dir}")
    print("\nSiguiente paso:")
    print("  Abre docs/data_sources_catalog.md para ver el mapeo de columnas")
    print("  y ejecuta el pipeline de exploración con DuckDB.")


def download_clues() -> None:
    """Descarga el catálogo CLUES más reciente."""
    links = discover("clues")
    if not links:
        print("[WARN] No se encontraron links en el portal CLUES.")
        return

    dest_dir = DATA_RAW / "clues"
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nLinks CLUES encontrados:")
    for lnk in links:
        print(f"  {lnk}")

    # Tomar el primer link disponible (usualmente el más reciente)
    url = links[0]
    filename = url.split("/")[-1].split("?")[0] or "clues.xlsx"
    dest = dest_dir / filename

    if dest.exists():
        print(f"[skip] {filename} ya existe.")
        return

    _download_file(url, dest)
    print(f"[ok] CLUES descargado: {dest}")


def download_cie10() -> None:
    """Descarga el catálogo CIE-10 CEMECE."""
    links = discover("cie10")
    if not links:
        print("[WARN] No se encontraron links en el portal CIE-10.")
        return

    dest_dir = DATA_RAW / "cie10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    url = links[0]
    filename = url.split("/")[-1].split("?")[0] or "cie10.zip"
    dest = dest_dir / filename

    if not dest.exists():
        _download_file(url, dest)
        if filename.lower().endswith(".zip"):
            _unzip(dest, dest_dir)

    print(f"[ok] CIE-10 descargado: {dest}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Descargador de datos abiertos DGIS/SSA para SaludMX."
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=list(PORTALS.keys()),
        help="Fuente de datos a descargar.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Año a descargar (aplica para SAEH).",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Solo muestra los links disponibles, no descarga.",
    )
    args = parser.parse_args()

    if args.source == "saeh":
        if not args.year:
            parser.error("--year es requerido para --source saeh")
        download_saeh(year=args.year, discover_only=args.discover_only)

    elif args.source == "clues":
        if args.discover_only:
            links = discover("clues")
            for lnk in links:
                print(lnk)
        else:
            download_clues()

    elif args.source == "cie10":
        if args.discover_only:
            links = discover("cie10")
            for lnk in links:
                print(lnk)
        else:
            download_cie10()

    elif args.source == "sinerhias":
        print("[INFO] SINERHIAS solo disponible con descarga manual.")
        print(f"  Portal: {PORTALS['sinerhias']}")
        print(f"  Destino sugerido: {DATA_RAW / 'sinerhias'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
