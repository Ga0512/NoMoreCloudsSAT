"""
FastAPI backend para o Satellite Image Compositor.
Endpoints para autenticação, upload de AOI, processamento e download.
"""
import os
import json
import shutil
import logging
import threading
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import OUTPUTS_DIR, UPLOADS_DIR, DEFAULT_BANDS, DEFAULT_RESOLUTION
from .models import (
    ProcessingRequest,
    JobInfo,
    JobStatus,
    AuthStatus,
    ProviderEnum,
    BBoxInput,
)
from pydantic import BaseModel as PydanticBaseModel
from .jobs import job_manager
from .utils import (
    bbox_to_geojson,
    read_shapefile_to_geojson,
    read_geojson_file,
    validate_geojson,
    normalize_geojson,
)

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ──────────────────────────────────────────────────
app = FastAPI(
    title="Satellite Image Compositor",
    description="Download e composição de imagens de satélite (GEE, Copernicus, Planetary Computer)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════════

@app.get("/api/auth/status", response_model=AuthStatus)
async def auth_status():
    """Retorna o status de autenticação de cada provedor."""
    from .services import gee, copernicus, planetary

    return AuthStatus(
        gee=gee.is_authenticated(),
        copernicus=copernicus.is_authenticated(),
        planetary=planetary.is_authenticated(),
        gee_message="Autenticado" if gee.is_authenticated() else "Não autenticado",
        copernicus_message="Autenticado" if copernicus.is_authenticated() else "Não autenticado",
        planetary_message="Acesso público (sempre disponível)",
    )


class GeeAuthRequest(PydanticBaseModel):
    project_id: Optional[str] = None


@app.post("/api/auth/gee")
async def auth_gee(body: GeeAuthRequest = GeeAuthRequest()):
    """
    Autentica no Google Earth Engine.
    Se as credenciais já estiverem em cache, inicializa direto.
    Caso contrário, inicia fluxo de autenticação (verifique o terminal).
    """
    from .services import gee

    pid = body.project_id.strip() if body.project_id else None
    result = gee.authenticate(project_id=pid or None)
    if result["success"]:
        return {"status": "ok", "message": result["message"]}
    raise HTTPException(status_code=401, detail=result["message"])


@app.post("/api/auth/copernicus")
async def auth_copernicus():
    """
    Inicia autenticação OIDC device flow com o Copernicus Data Space.
    Retorna URL + código imediatamente para o frontend mostrar.
    O device flow roda em background — frontend polla /api/auth/status.
    """
    from .services import copernicus

    result = copernicus.start_authentication()

    if result.get("success"):
        return {
            "status": "ok",
            "message": result["message"],
            "verification_uri": result.get("verification_uri"),
            "user_code": result.get("user_code"),
        }

    # Device code obtido — retorna 202 com URL para o frontend mostrar
    if result.get("phase") == "device_code":
        return JSONResponse(
            status_code=202,
            content={
                "status": "pending",
                "message": result.get("message", "Complete o login no link abaixo."),
                "verification_uri": result.get("verification_uri"),
                "user_code": result.get("user_code"),
            },
        )

    # Erro real
    raise HTTPException(status_code=401, detail=result.get("message", "Erro desconhecido"))


# ═══════════════════════════════════════════════════════════
# AOI (Área de Interesse)
# ═══════════════════════════════════════════════════════════

@app.post("/api/aoi/bbox")
async def aoi_from_bbox(bbox: BBoxInput):
    """Converte bounding box em GeoJSON."""
    geojson = bbox_to_geojson(bbox.west, bbox.south, bbox.east, bbox.north)
    return {"geojson": geojson}


@app.post("/api/aoi/upload")
async def aoi_from_upload(file: UploadFile = File(...)):
    """
    Upload de Shapefile (.zip) ou GeoJSON (.geojson/.json).
    Retorna GeoJSON normalizado.
    """
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()

    # Salva arquivo temporariamente
    tmp_path = UPLOADS_DIR / filename
    with open(tmp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        if suffix == ".zip":
            geojson = read_shapefile_to_geojson(str(tmp_path))
        elif suffix in (".geojson", ".json"):
            geojson = read_geojson_file(str(tmp_path))
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Formato não suportado: {suffix}. Use .zip (shapefile) ou .geojson/.json.",
            )

        if not validate_geojson(geojson):
            raise HTTPException(status_code=400, detail="GeoJSON inválido.")

        # Normaliza para geometria simples
        geometry = normalize_geojson(geojson)
        return {"geojson": geometry}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao processar upload: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo: {e}")
    finally:
        # Limpa arquivo temporário
        if tmp_path.exists():
            tmp_path.unlink()


@app.post("/api/aoi/geojson")
async def aoi_from_geojson(geojson: dict):
    """Recebe GeoJSON diretamente (ex: do Leaflet Draw) e normaliza."""
    if not validate_geojson(geojson):
        raise HTTPException(status_code=400, detail="GeoJSON inválido.")
    geometry = normalize_geojson(geojson)
    return {"geojson": geometry}


# ═══════════════════════════════════════════════════════════
# PROCESSAMENTO
# ═══════════════════════════════════════════════════════════

@app.post("/api/process", response_model=JobInfo)
async def start_processing(req: ProcessingRequest):
    """
    Inicia um job de processamento em background.
    Retorna imediatamente com o job_id para acompanhamento.
    """
    # Validações
    provider = req.provider

    # Verifica autenticação
    from .services import gee, copernicus

    if provider in (ProviderEnum.GEE_SENTINEL, ProviderEnum.GEE_LANDSAT):
        if not gee.is_authenticated():
            raise HTTPException(status_code=401, detail="GEE não autenticado.")
    elif provider == ProviderEnum.COPERNICUS:
        if not copernicus.is_authenticated():
            raise HTTPException(status_code=401, detail="Copernicus não autenticado.")

    # Define bandas e resolução padrão se não especificados
    bands = req.bands
    resolution = req.resolution

    if provider == ProviderEnum.GEE_SENTINEL:
        bands = bands or DEFAULT_BANDS["gee"]
        resolution = resolution or DEFAULT_RESOLUTION["gee_sentinel"]
    elif provider == ProviderEnum.GEE_LANDSAT:
        bands = bands or ["SR_B2", "SR_B3", "SR_B4", "SR_B5"]
        resolution = resolution or DEFAULT_RESOLUTION["gee_landsat"]
    elif provider == ProviderEnum.COPERNICUS:
        bands = bands or DEFAULT_BANDS["copernicus"]
        resolution = resolution or DEFAULT_RESOLUTION["copernicus"]
    elif provider == ProviderEnum.PLANETARY:
        bands = bands or DEFAULT_BANDS["planetary"]
        resolution = resolution or DEFAULT_RESOLUTION["planetary"]

    # Normaliza GeoJSON
    try:
        geometry = normalize_geojson(req.aoi_geojson)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"GeoJSON inválido: {e}")

    # Cria job
    job_id = job_manager.create_job(provider.value)

    # Monta nome do arquivo de saída
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{provider.value}_{timestamp}_{job_id}.tif"
    output_path = str(OUTPUTS_DIR / output_filename)

    # Inicia processamento em thread separada
    def run_job():
        def progress_callback(pct, msg):
            job_manager.update_job(job_id, progress=pct, message=msg)

        try:
            job_manager.update_job(job_id, status=JobStatus.RUNNING, message="Iniciando processamento...")

            if provider == ProviderEnum.GEE_SENTINEL:
                gee.process_sentinel(
                    aoi_geojson=geometry,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    bands=bands,
                    scale=resolution,
                    max_cloud=req.max_cloud,
                    cloud_prob=req.cloud_prob_threshold,
                    output_path=output_path,
                    progress_callback=progress_callback,
                )

            elif provider == ProviderEnum.GEE_LANDSAT:
                gee.process_landsat(
                    aoi_geojson=geometry,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    bands=bands,
                    scale=resolution,
                    max_cloud=req.max_cloud,
                    output_path=output_path,
                    progress_callback=progress_callback,
                )

            elif provider == ProviderEnum.COPERNICUS:
                copernicus.process_sentinel(
                    aoi_geojson=geometry,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    bands=bands,
                    max_cloud=req.max_cloud,
                    output_path=output_path,
                    progress_callback=progress_callback,
                )

            elif provider == ProviderEnum.PLANETARY:
                from .services import planetary
                planetary.process_landsat(
                    aoi_geojson=geometry,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    bands=bands,
                    resolution=resolution,
                    max_cloud=req.max_cloud,
                    output_path=output_path,
                    progress_callback=progress_callback,
                )

            job_manager.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                message="Processamento concluído!",
                progress=100,
                output_file=output_filename,
            )

        except Exception as e:
            logger.error(f"Job {job_id} falhou: {e}", exc_info=True)
            job_manager.update_job(
                job_id,
                status=JobStatus.FAILED,
                message=f"Erro: {str(e)}",
            )

    thread = threading.Thread(target=run_job, daemon=True)
    thread.start()

    return job_manager.get_job(job_id)


# ═══════════════════════════════════════════════════════════
# JOBS
# ═══════════════════════════════════════════════════════════

@app.get("/api/jobs", response_model=List[JobInfo])
async def list_jobs():
    """Lista todos os jobs (mais recente primeiro)."""
    return job_manager.list_jobs()


@app.get("/api/jobs/{job_id}", response_model=JobInfo)
async def get_job(job_id: str):
    """Retorna status de um job específico."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return job


# ═══════════════════════════════════════════════════════════
# DOWNLOAD
# ═══════════════════════════════════════════════════════════

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download de arquivo GeoTIFF gerado."""
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="image/tiff",
    )


@app.get("/api/outputs")
async def list_outputs():
    """Lista todos os arquivos disponíveis para download."""
    files = []
    for f in sorted(OUTPUTS_DIR.iterdir(), reverse=True):
        if f.is_file() and f.suffix in (".tif", ".tiff"):
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat(),
            })
    return files


# ═══════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
