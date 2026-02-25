"""
Utilitários: conversão de AOI, leitura de shapefile, validações.
"""
import json
import zipfile
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


def bbox_to_geojson(west: float, south: float, east: float, north: float) -> Dict[str, Any]:
    """Converte bounding box para GeoJSON Polygon."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]]
    }


def geojson_to_bbox(geojson: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Extrai bounding box [west, south, east, north] de qualquer GeoJSON."""
    coords = _extract_all_coords(geojson)
    if not coords:
        raise ValueError("GeoJSON sem coordenadas válidas.")
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (min(lons), min(lats), max(lons), max(lats))


def _extract_all_coords(geojson: Dict[str, Any]) -> List[List[float]]:
    """Extrai todas as coordenadas de um GeoJSON (Polygon, MultiPolygon, Feature, FeatureCollection)."""
    gtype = geojson.get("type", "")

    if gtype == "FeatureCollection":
        coords = []
        for feat in geojson.get("features", []):
            coords.extend(_extract_all_coords(feat))
        return coords

    if gtype == "Feature":
        return _extract_all_coords(geojson.get("geometry", {}))

    if gtype == "Polygon":
        return [pt for ring in geojson.get("coordinates", []) for pt in ring]

    if gtype == "MultiPolygon":
        return [
            pt
            for poly in geojson.get("coordinates", [])
            for ring in poly
            for pt in ring
        ]

    return []


def read_shapefile_to_geojson(zip_path: str) -> Dict[str, Any]:
    """
    Lê um zip contendo .shp/.shx/.dbf e retorna GeoJSON.
    Usa fiona para a leitura.
    """
    import fiona
    from fiona.io import ZipMemoryFile

    with open(zip_path, "rb") as f:
        zip_bytes = f.read()

    # Tenta abrir como zip com fiona
    with ZipMemoryFile(zip_bytes) as z:
        # Pega a primeira layer
        with z.open() as collection:
            features = []
            for feature in collection:
                features.append(dict(feature))
            crs = collection.crs

    # Monta FeatureCollection
    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    logger.info(f"Shapefile lido: {len(features)} features, CRS={crs}")
    return geojson


def read_geojson_file(file_path: str) -> Dict[str, Any]:
    """Lê um arquivo .geojson e retorna o dict."""
    with open(file_path, "r") as f:
        return json.load(f)


def validate_geojson(geojson: Dict[str, Any]) -> bool:
    """Validação básica de GeoJSON."""
    gtype = geojson.get("type", "")
    if gtype in ("Polygon", "MultiPolygon"):
        return "coordinates" in geojson
    if gtype == "Feature":
        return "geometry" in geojson
    if gtype == "FeatureCollection":
        return "features" in geojson
    return False


def normalize_geojson(geojson: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza GeoJSON para Polygon simples.
    Se for FeatureCollection, pega a geometria do primeiro feature.
    Se for Feature, extrai a geometria.
    """
    gtype = geojson.get("type", "")

    if gtype == "FeatureCollection":
        features = geojson.get("features", [])
        if not features:
            raise ValueError("FeatureCollection vazio.")
        return normalize_geojson(features[0])

    if gtype == "Feature":
        geom = geojson.get("geometry")
        if not geom:
            raise ValueError("Feature sem geometria.")
        return geom

    if gtype in ("Polygon", "MultiPolygon"):
        return geojson

    raise ValueError(f"Tipo GeoJSON não suportado: {gtype}")


def clip_raster_to_geojson(raster_path: str, geojson: Dict[str, Any], output_path: str = None) -> str:
    """
    Recorta um GeoTIFF usando um polígono GeoJSON.
    Pixels fora do polígono ficam como NoData (transparentes).

    Lida automaticamente com diferenças de CRS:
    o GeoJSON é sempre EPSG:4326, mas o raster pode estar em UTM ou outro CRS.

    Args:
        raster_path: caminho do GeoTIFF de entrada
        geojson: GeoJSON geometry (Polygon/MultiPolygon) em EPSG:4326
        output_path: caminho de saída (None = sobrescreve o original)

    Returns:
        Caminho do arquivo recortado.
    """
    import rasterio
    from rasterio.mask import mask as rio_mask
    from shapely.geometry import shape, mapping
    from shapely.ops import transform as shp_transform
    from pyproj import Transformer
    import numpy as np

    if output_path is None:
        output_path = raster_path

    # Abre o raster para descobrir o CRS
    with rasterio.open(raster_path) as src:
        raster_crs = src.crs
        logger.info(f"Raster CRS: {raster_crs}, bounds: {src.bounds}")

    # Cria geometria shapely a partir do GeoJSON (assume EPSG:4326)
    geom_4326 = shape(geojson)

    # Se o raster NÃO está em EPSG:4326, reprojeta o polígono para o CRS do raster
    if raster_crs and not raster_crs.to_epsg() == 4326:
        logger.info(f"Reprojetando polígono de EPSG:4326 para {raster_crs}...")
        transformer = Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)
        geom = shp_transform(transformer.transform, geom_4326)
    else:
        geom = geom_4326

    geometries = [mapping(geom)]
    logger.info(f"Geometria para clip bounds: {geom.bounds}")

    # Lê, recorta e salva
    with rasterio.open(raster_path) as src:
        try:
            out_image, out_transform = rio_mask(
                src,
                geometries,
                crop=True,
                nodata=0,
                all_touched=True,
            )
        except ValueError as e:
            # Se ainda não sobrepõe, loga detalhes e pula o clip
            logger.warning(
                f"Clip falhou ({e}). Raster bounds={src.bounds}, "
                f"Polygon bounds={geom.bounds}, Raster CRS={raster_crs}. "
                "Retornando raster original sem recorte."
            )
            return raster_path

        out_meta = src.meta.copy()

    out_meta.update({
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
    })

    # Define nodata adequado ao dtype
    dtype_str = str(out_meta.get("dtype", ""))
    if "float" in dtype_str:
        out_meta["nodata"] = float("nan")
        out_image = np.where(out_image == 0, np.nan, out_image)
    else:
        out_meta["nodata"] = 0

    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(out_image)

    logger.info(f"Raster recortado para polígono: {output_path} ({out_image.shape})")
    return output_path
