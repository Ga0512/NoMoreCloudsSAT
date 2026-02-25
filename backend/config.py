"""
Configurações globais do backend.
"""
import os
from pathlib import Path

# Diretório raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent

# Pasta de saída para GeoTIFFs
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Pasta temporária para uploads (shapefiles etc.)
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# GEE
GEE_PROJECT = os.getenv("GEE_PROJECT", "")  # opcional, pode ficar vazio

# Copernicus OpenEO
OPENEO_BACKEND = "https://openeo.dataspace.copernicus.eu"

# Planetary Computer
PLANETARY_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# Bandas padrão por provedor
DEFAULT_BANDS = {
    "gee": ["B2", "B3", "B4", "B8"],
    "copernicus": ["B02", "B03", "B04", "B08"],
    "planetary": ["blue", "green", "red", "nir08"],
}

# Resoluções padrão
DEFAULT_RESOLUTION = {
    "gee_sentinel": 10,
    "gee_landsat": 30,
    "copernicus": 10,
    "planetary": 30,
}
