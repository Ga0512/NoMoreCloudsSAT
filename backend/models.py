"""
Modelos Pydantic para requests e responses.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class ProviderEnum(str, Enum):
    GEE_SENTINEL = "gee_sentinel"
    GEE_LANDSAT = "gee_landsat"
    COPERNICUS = "copernicus"
    PLANETARY = "planetary"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BBoxInput(BaseModel):
    """Bounding box: [lon_min, lat_min, lon_max, lat_max]"""
    west: float = Field(..., ge=-180, le=180)
    south: float = Field(..., ge=-90, le=90)
    east: float = Field(..., ge=-180, le=180)
    north: float = Field(..., ge=-90, le=90)


class ProcessingRequest(BaseModel):
    """Requisição de processamento de imagem de satélite."""
    provider: ProviderEnum
    aoi_geojson: Dict[str, Any]  # GeoJSON (Polygon ou bbox convertido)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    bands: Optional[List[str]] = None  # None = usar padrão do provedor
    resolution: Optional[int] = None   # None = usar padrão do provedor
    max_cloud: int = Field(default=30, ge=0, le=100)
    cloud_prob_threshold: int = Field(default=50, ge=0, le=100)  # só GEE Sentinel


class JobInfo(BaseModel):
    """Informações sobre um job."""
    job_id: str
    provider: str
    status: JobStatus
    created_at: str
    message: str = ""
    progress: int = 0  # 0–100
    output_file: Optional[str] = None


class AuthStatus(BaseModel):
    """Status de autenticação de cada provedor."""
    gee: bool = False
    copernicus: bool = False
    planetary: bool = True  # sempre autenticado (público)
    gee_message: str = ""
    copernicus_message: str = ""
    planetary_message: str = "Acesso público, sem autenticação necessária."
