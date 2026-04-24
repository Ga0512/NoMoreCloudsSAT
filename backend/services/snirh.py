"""
Provedor ANADEM (ANA/SNIRH) via Google Earth Engine.
Asset público: projects/et-brasil/assets/anadem/v1
ANADEM é um Modelo Digital de Terreno (DTM) para a América do Sul, 30 m.
Dataset estático (sem dimensão temporal) — start_date/end_date são ignorados.
Requer GEE autenticado — compartilha estado com services/gee.py.
"""
import logging
import requests
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_ASSET_ID = "projects/et-brasil/assets/anadem/v1"


def is_authenticated() -> bool:
    from .gee import is_authenticated as _gee_auth
    return _gee_auth()


def process_anadem(
    aoi_geojson: Dict[str, Any],
    start_date: str,           # ignorado — dataset estático
    end_date: str,             # ignorado — dataset estático
    bands: Optional[List[str]],
    scale: int,
    output_path: str,
    progress_callback=None,
) -> str:
    """
    Baixa o ANADEM (DTM 30 m) clipeado na AOI via GEE.

    Args:
        aoi_geojson: GeoJSON Polygon da AOI
        start_date: ignorado (dataset sem dimensão temporal)
        end_date: ignorado
        bands: ignorado (única banda renomeada para 'elevation')
        scale: resolução em metros (nativo 30 m)
        output_path: caminho de saída para o GeoTIFF
        progress_callback: função(pct: int, msg: str)

    Returns:
        Caminho do arquivo salvo.
    """
    import ee
    from .gee import _gee_initialized, _check_token_valid

    if not _gee_initialized:
        raise RuntimeError("GEE não autenticado. Faça login no GEE primeiro.")
    if not _check_token_valid():
        raise RuntimeError("Token GEE expirado. Clique em 'Login GEE' novamente.")

    def update(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)
        logger.info(f"[ANADEM] {pct}% - {msg}")

    update(5, "Criando geometria da AOI...")
    aoi = ee.Geometry(aoi_geojson)

    update(15, f"Carregando asset ANADEM ({_ASSET_ID})...")
    try:
        image = ee.Image(_ASSET_ID)
        # Seleciona a primeira banda e renomeia para 'elevation'
        # (o nome interno do asset pode variar; .select([0]) é seguro)
        image = image.select([0]).rename("elevation")
    except Exception as e:
        raise RuntimeError(
            f"Não foi possível carregar o asset ANADEM: {e}. "
            "Verifique se o seu usuário GEE tem acesso ao asset "
            f"'{_ASSET_ID}' (deve ser público em CC BY 4.0)."
        )

    update(30, "Clipeando na AOI...")
    image = image.clip(aoi)

    update(50, "Gerando URL de download...")
    try:
        url = image.getDownloadURL({
            "scale": scale,
            "crs": "EPSG:4326",
            "region": aoi,
            "format": "GEO_TIFF",
            "filePerBand": False,
            "maxPixels": 1e13,
        })
    except Exception as e:
        raise RuntimeError(
            f"Erro ao gerar URL de download (AOI muito grande?): {e}. "
            "Tente reduzir a área ou usar escala maior (ex: 60 m)."
        )

    update(70, "Baixando GeoTIFF...")
    resp = requests.get(url, stream=True, timeout=600)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                dl_pct = int(70 + (downloaded / total_size) * 22)
                update(min(dl_pct, 92), f"Baixando... {downloaded // 1024} KB")

    update(94, "Recortando para o polígono exato da AOI...")
    from ..utils import clip_raster_to_geojson
    clip_raster_to_geojson(output_path, aoi_geojson, output_path)

    update(100, "Concluído!")
    return output_path
