"""
Provedor Microsoft Planetary Computer (Landsat 8/9 via STAC).
Sem autenticação necessária (acesso público com URLs assinadas).
"""
import os
import logging
import numpy as np
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Força acesso sem credenciais AWS (dados públicos)
os.environ["AWS_NO_SIGN_REQUEST"] = "YES"


def is_authenticated() -> bool:
    """Planetary Computer é público, sempre 'autenticado'."""
    return True


def process_landsat(
    aoi_geojson: Dict[str, Any],
    start_date: str,
    end_date: str,
    bands: List[str],
    resolution: int,
    max_cloud: int,
    output_path: str,
    progress_callback=None,
) -> str:
    """
    Processa composição mediana do Landsat 8+9 via Planetary Computer STAC.

    Args:
        aoi_geojson: GeoJSON Polygon da AOI
        start_date: data inicial (YYYY-MM-DD)
        end_date: data final (YYYY-MM-DD)
        bands: lista de bandas (ex: ['blue','green','red','nir08'])
        resolution: resolução em metros (tipicamente 30)
        max_cloud: % máximo de nuvens
        output_path: caminho de saída para o GeoTIFF
        progress_callback: função(progress_int, message_str)

    Returns:
        Caminho do arquivo salvo.
    """
    import stackstac
    import pystac_client
    import planetary_computer
    import rioxarray

    def update(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)
        logger.info(f"[Planetary] {pct}% - {msg}")

    # Extrai bbox
    from ..utils import geojson_to_bbox
    bbox = list(geojson_to_bbox(aoi_geojson))

    update(5, "Buscando cenas no catálogo Planetary Computer...")
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    temporal_str = f"{start_date}/{end_date}"
    search = catalog.search(
        collections=["landsat-c2-l2"],
        bbox=bbox,
        datetime=temporal_str,
        query={
            "eo:cloud_cover": {"lt": max_cloud},
            "platform": {"in": ["landsat-8", "landsat-9"]},
        },
    )

    items = list(search.items())
    if not items:
        raise RuntimeError(
            "Nenhuma cena Landsat encontrada para os parâmetros fornecidos. "
            "Tente ampliar o período ou aumentar o limite de nuvens."
        )

    logger.info(f"{len(items)} cenas encontradas.")
    update(15, f"{len(items)} cenas encontradas. Assinando URLs...")

    # Assina URLs (necessário para acesso aos dados)
    items = [planetary_computer.sign(i) for i in items]

    update(25, "Montando datacube com stackstac...")

    # Determina EPSG baseado na localização (heurística simples)
    center_lat = (bbox[1] + bbox[3]) / 2
    center_lon = (bbox[0] + bbox[2]) / 2
    # UTM zone
    utm_zone = int((center_lon + 180) / 6) + 1
    hemisphere = "6" if center_lat >= 0 else "7"
    epsg = int(f"32{hemisphere}{utm_zone:02d}")
    logger.info(f"EPSG detectado: {epsg}")

    stack_kwargs = dict(
        bounds_latlon=bbox,
        resolution=resolution,
        epsg=epsg,
        rescale=False,
        dtype="float64",
        fill_value=np.nan,
    )

    optical = stackstac.stack(items, assets=bands, **stack_kwargs)
    qa_stack = stackstac.stack(items, assets=["qa_pixel"], **stack_kwargs)
    qa = qa_stack.sel(band="qa_pixel")

    update(40, "Aplicando máscara de nuvem (QA_PIXEL)...")
    qa_int = qa.fillna(0).astype("uint32")

    # Bits: 1=dilated cloud, 3=cloud, 4=cloud shadow, 5=snow
    cloud_mask = (
        ((qa_int & 2) != 0) |   # bit 1
        ((qa_int & 8) != 0) |   # bit 3
        ((qa_int & 16) != 0) |  # bit 4
        ((qa_int & 32) != 0)    # bit 5
    )

    optical = optical.where(~cloud_mask)

    update(55, "Aplicando fator de escala (Collection 2)...")
    optical = optical * 0.0000275 + (-0.2)
    optical = optical.clip(0, 1)

    update(65, "Calculando mediana temporal (isso pode levar alguns minutos)...")
    mediana = optical.median(dim="time", skipna=True).compute()

    nan_pct = float(np.isnan(mediana).mean()) * 100
    logger.info(
        f"Range final: min={float(mediana.min()):.4f}  "
        f"max={float(mediana.max()):.4f}  nan%={nan_pct:.1f}%"
    )

    update(90, "Exportando GeoTIFF...")
    mediana.astype("float32").rio.to_raster(output_path, dtype="float32")

    update(96, "Recortando para o polígono exato da AOI...")
    from ..utils import clip_raster_to_geojson
    clip_raster_to_geojson(output_path, aoi_geojson, output_path)

    update(100, "Concluído!")
    return output_path
