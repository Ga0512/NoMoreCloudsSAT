"""
Provedor Google Earth Engine (Sentinel-2 e Landsat 8/9).
Usa a API Python `ee` com autenticação do próprio usuário.
"""
import ee
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Estado de autenticação global
_gee_initialized = False


def is_authenticated() -> bool:
    """Verifica se o GEE está autenticado e inicializado."""
    return _gee_initialized


def _check_token_valid() -> bool:
    """
    Verifica se o token GEE ainda é válido fazendo uma chamada leve.
    Se expirou, tenta reinicializar com as credenciais em cache
    (a lib ee faz refresh automático do OAuth token).
    """
    global _gee_initialized
    if not _gee_initialized:
        return False
    try:
        # Chamada leve para validar token
        ee.Number(1).getInfo()
        return True
    except Exception as e:
        logger.warning(f"Token GEE pode ter expirado: {e}. Tentando reinicializar...")
        try:
            ee.Initialize()
            ee.Number(1).getInfo()
            logger.info("GEE reinicializado com sucesso (token refreshed).")
            return True
        except Exception as e2:
            logger.error(f"Falha ao reinicializar GEE: {e2}")
            _gee_initialized = False
            return False


def authenticate(project_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Tenta autenticar no GEE.

    Ordem de tentativas:
    1. Credenciais em cache (~/.config/earthengine/credentials)
    2. ee.Authenticate(auth_mode='localhost') — abre navegador, sem precisar de
       OAuth2 Client configurado no projeto (resolve o erro
       "incompatible OAuth2 Client configuration")
    3. Fallback para 'colab' mode se localhost falhar

    Retorna dict com status e mensagem.
    """
    global _gee_initialized

    # Se já inicializado, retorna sucesso
    if _gee_initialized:
        return {"success": True, "message": "GEE já autenticado."}

    init_kwargs = {}
    if project_id:
        init_kwargs["project"] = project_id

    # ── Tentativa 1: credenciais em cache ──
    try:
        ee.Initialize(**init_kwargs)
        _gee_initialized = True
        logger.info("GEE inicializado com credenciais em cache.")
        return {"success": True, "message": "GEE autenticado com credenciais em cache."}
    except Exception as e:
        logger.info(f"Credenciais em cache não disponíveis: {e}")

    # ── Tentativa 2: auth_mode='localhost' ──
    # Abre um servidor local temporário e redireciona o OAuth para localhost.
    # NÃO requer OAuth2 Client configurado no projeto GCloud.
    AUTH_MODES = ["localhost", "colab", "notebook"]

    for mode in AUTH_MODES:
        try:
            logger.info(f"Tentando autenticação GEE com auth_mode='{mode}'...")
            ee.Authenticate(auth_mode=mode)
            ee.Initialize(**init_kwargs)
            _gee_initialized = True
            logger.info(f"GEE autenticado via auth_mode='{mode}'.")
            return {"success": True, "message": f"GEE autenticado com sucesso (modo: {mode})."}
        except Exception as e:
            logger.warning(f"auth_mode='{mode}' falhou: {e}")
            continue

    # Nenhum modo funcionou
    return {
        "success": False,
        "message": (
            "Falha na autenticação GEE com todos os modos (localhost, colab, notebook).\n\n"
            "Solução recomendada:\n"
            "1. Abra um terminal\n"
            "2. Execute: earthengine authenticate\n"
            "3. Complete o fluxo no navegador\n"
            "4. Volte ao webapp e clique em 'Login GEE' novamente\n\n"
            "Se o erro persistir, verifique se o projeto GCloud tem a API Earth Engine habilitada "
            "em https://console.cloud.google.com/apis/library/earthengine.googleapis.com"
        ),
    }


def process_sentinel(
    aoi_geojson: Dict[str, Any],
    start_date: str,
    end_date: str,
    bands: List[str],
    scale: int,
    max_cloud: int,
    cloud_prob: int,
    output_path: str,
    progress_callback=None,
) -> str:
    """
    Processa composição mediana do Sentinel-2 via GEE.
    Exporta para arquivo local via getDownloadURL.

    Args:
        aoi_geojson: GeoJSON da área de interesse (Polygon)
        start_date: data inicial (YYYY-MM-DD)
        end_date: data final (YYYY-MM-DD)
        bands: lista de bandas (ex: ['B2','B3','B4','B8'])
        scale: resolução em metros
        max_cloud: % máximo de nuvens por cena
        cloud_prob: threshold s2cloudless
        output_path: caminho de saída para o GeoTIFF
        progress_callback: função(progress_int, message_str)

    Returns:
        Caminho do arquivo salvo.
    """
    if not _gee_initialized:
        raise RuntimeError("GEE não autenticado. Chame authenticate() primeiro.")

    # Verifica se o token ainda é válido (refresh automático se possível)
    if not _check_token_valid():
        raise RuntimeError(
            "Token GEE expirado e não foi possível renovar. "
            "Clique em 'Login GEE' novamente na interface."
        )

    def update(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)
        logger.info(f"[GEE Sentinel] {pct}% - {msg}")

    update(5, "Criando geometria da AOI...")
    aoi = ee.Geometry(aoi_geojson)

    update(10, "Carregando coleção Sentinel-2 SR Harmonized...")
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
    )

    s2_clouds = (
        ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
    )

    update(20, "Fazendo join com probabilidade de nuvem...")
    joined = ee.ImageCollection(
        ee.Join.saveFirst("cloud_prob").apply(
            primary=s2,
            secondary=s2_clouds,
            condition=ee.Filter.equals(
                leftField="system:index", rightField="system:index"
            ),
        )
    )

    update(30, "Aplicando máscara de nuvem por pixel...")

    def mask_clouds(image):
        prob = ee.Image(image.get("cloud_prob")).select("probability")
        return image.updateMask(prob.lt(cloud_prob))

    masked = joined.map(mask_clouds)

    update(40, "Calculando composição mediana...")
    composite = masked.select(bands).median().clip(aoi)

    update(50, "Gerando URL de download...")
    # Usa getDownloadURL para download direto (sem Google Drive)
    try:
        url = composite.getDownloadURL({
            "scale": scale,
            "crs": "EPSG:4326",
            "region": aoi,
            "format": "GEO_TIFF",
            "filePerBand": False,
        })
    except Exception as e:
        # Se a área for muito grande, usa Export.image.toDrive como fallback
        raise RuntimeError(
            f"Erro ao gerar download (área pode ser muito grande para download direto): {e}. "
            "Tente reduzir a área de interesse ou usar resolução menor."
        )

    update(70, "Baixando GeoTIFF...")
    import requests

    resp = requests.get(url, stream=True, timeout=600)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                dl_pct = int(70 + (downloaded / total_size) * 25)
                update(min(dl_pct, 95), f"Baixando... {downloaded // 1024} KB")

    update(96, "Recortando para o polígono exato da AOI...")
    from ..utils import clip_raster_to_geojson
    clip_raster_to_geojson(output_path, aoi_geojson, output_path)

    update(100, "Concluído!")
    return output_path


def process_landsat(
    aoi_geojson: Dict[str, Any],
    start_date: str,
    end_date: str,
    bands: List[str],
    scale: int,
    max_cloud: int,
    output_path: str,
    progress_callback=None,
) -> str:
    """
    Processa composição mediana do Landsat 8+9 via GEE.
    Exporta para arquivo local via getDownloadURL.

    Args:
        aoi_geojson: GeoJSON da área de interesse (Polygon)
        start_date: data inicial (YYYY-MM-DD)
        end_date: data final (YYYY-MM-DD)
        bands: lista de bandas Landsat (ex: ['SR_B2','SR_B3','SR_B4','SR_B5'])
        scale: resolução em metros (tipicamente 30)
        max_cloud: % máximo de nuvens por cena
        output_path: caminho de saída para o GeoTIFF
        progress_callback: função(progress_int, message_str)

    Returns:
        Caminho do arquivo salvo.
    """
    if not _gee_initialized:
        raise RuntimeError("GEE não autenticado. Chame authenticate() primeiro.")

    if not _check_token_valid():
        raise RuntimeError(
            "Token GEE expirado e não foi possível renovar. "
            "Clique em 'Login GEE' novamente na interface."
        )

    def update(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)
        logger.info(f"[GEE Landsat] {pct}% - {msg}")

    update(5, "Criando geometria da AOI...")
    aoi = ee.Geometry(aoi_geojson)

    update(10, "Carregando coleções Landsat 8 + 9...")
    l8 = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
    )
    l9 = (
        ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
    )
    landsat = l8.merge(l9)

    update(25, "Aplicando máscara de nuvem (QA_PIXEL)...")

    def mask_clouds(image):
        qa = image.select("QA_PIXEL")
        cloud = qa.bitwiseAnd(1 << 3).eq(0)
        cloud_shadow = qa.bitwiseAnd(1 << 4).eq(0)
        mask = cloud.And(cloud_shadow)
        return image.updateMask(mask)

    masked = landsat.map(mask_clouds)

    update(40, "Aplicando fator de escala (Collection 2)...")

    def apply_scale(image):
        optical = image.select(bands).multiply(0.0000275).add(-0.2)
        return optical.copyProperties(image, image.propertyNames())

    scaled = masked.map(apply_scale)

    update(50, "Calculando composição mediana...")
    composite = scaled.median().clip(aoi)

    update(60, "Gerando URL de download...")
    try:
        url = composite.getDownloadURL({
            "scale": scale,
            "crs": "EPSG:4326",
            "region": aoi,
            "format": "GEO_TIFF",
            "filePerBand": False,
        })
    except Exception as e:
        raise RuntimeError(
            f"Erro ao gerar download: {e}. "
            "Tente reduzir a área de interesse."
        )

    update(70, "Baixando GeoTIFF...")
    import requests

    resp = requests.get(url, stream=True, timeout=600)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                dl_pct = int(70 + (downloaded / total_size) * 25)
                update(min(dl_pct, 95), f"Baixando... {downloaded // 1024} KB")

    update(96, "Recortando para o polígono exato da AOI...")
    from ..utils import clip_raster_to_geojson
    clip_raster_to_geojson(output_path, aoi_geojson, output_path)

    update(100, "Concluído!")
    return output_path
