"""
Provedor Copernicus Data Space via OpenEO.
Usa autenticação OIDC device flow.
Inclui retry robusto e polling manual com tolerância a erros 500.
"""
import openeo
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import OPENEO_BACKEND

logger = logging.getLogger(__name__)

# Estado global
_connection: Optional[openeo.Connection] = None
_authenticated = False


def _build_retry_adapter() -> HTTPAdapter:
    """Cria HTTPAdapter com retry agressivo para tolerar instabilidades do Copernicus."""
    retry_strategy = Retry(
        total=10,                # até 10 tentativas
        backoff_factor=3,        # espera 3s, 6s, 12s, 24s, 48s...
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PATCH", "DELETE", "HEAD"],
        raise_on_status=False,   # não levanta exceção, deixa o caller decidir
    )
    return HTTPAdapter(max_retries=retry_strategy)


def is_authenticated() -> bool:
    return _authenticated


def _check_token_valid() -> bool:
    """
    Verifica se o token OIDC do Copernicus ainda é válido.
    Se expirou, tenta refresh automático via refresh_token.
    """
    global _connection, _authenticated
    if not _authenticated or not _connection:
        return False
    try:
        # Chamada leve para testar token
        _connection.describe_account()
        return True
    except Exception as e:
        logger.warning(f"Token Copernicus pode ter expirado: {e}. Tentando refresh...")
        try:
            # Tenta refresh via OIDC refresh token (não precisa de interação do usuário)
            _connection.authenticate_oidc_refresh_token()
            _connection.describe_account()
            logger.info("Token Copernicus renovado com sucesso via refresh_token.")
            return True
        except Exception:
            pass
        try:
            # Fallback: tenta re-autenticar com credenciais salvas
            _connection.authenticate_oidc()
            _connection.describe_account()
            logger.info("Token Copernicus renovado via authenticate_oidc.")
            return True
        except Exception as e2:
            logger.error(f"Falha ao renovar token Copernicus: {e2}")
            _authenticated = False
            return False


def get_connection() -> Optional[openeo.Connection]:
    return _connection


def start_authentication() -> Dict[str, Any]:
    """
    Fase 1: Conecta ao backend e inicia device flow em background.
    Retorna a URL + código IMEDIATAMENTE para o frontend mostrar,
    enquanto o device flow fica aguardando em background.

    O frontend deve pollar /api/auth/status até copernicus=true.
    """
    global _connection, _authenticated, _auth_thread

    if _authenticated and _connection:
        return {"success": True, "message": "Copernicus já autenticado.", "phase": "complete"}

    # Se já tem uma auth em andamento, retorna a URL salva
    if _auth_thread and _auth_thread.is_alive() and _pending_device_info.get("verification_uri"):
        return {
            "success": False,
            "message": "Autenticação em andamento. Complete o login no link abaixo.",
            "phase": "device_code",
            "verification_uri": _pending_device_info.get("verification_uri"),
            "user_code": _pending_device_info.get("user_code"),
        }

    import io
    import sys
    import re
    import threading

    try:
        logger.info("Conectando ao backend Copernicus Data Space...")
        conn = openeo.connect(OPENEO_BACKEND)

        adapter = _build_retry_adapter()
        conn.session.mount("https://", adapter)

        # Captura stdout em background para pegar URL antes do bloqueio
        captured = io.StringIO()
        original_stdout = sys.stdout
        tee = _TeeWriter(original_stdout, captured)

        verification_uri = None
        user_code = None

        # Event que sinaliza quando a URL foi capturada
        url_captured_event = threading.Event()

        def do_auth():
            global _connection, _authenticated
            nonlocal verification_uri, user_code

            sys.stdout = tee
            try:
                conn.authenticate_oidc_device()

                _connection = conn
                _authenticated = True
                logger.info("Copernicus autenticado com sucesso (background).")
            except Exception as e:
                logger.error(f"Falha na autenticação Copernicus (background): {e}")
            finally:
                sys.stdout = original_stdout

        # Monitor thread: lê o captured output até achar a URL
        def monitor_output():
            nonlocal verification_uri, user_code
            import time as _time

            for _ in range(60):  # tenta por 30s
                text = captured.getvalue()
                if text:
                    url_match = re.search(r'(https?://\S+)', text)
                    code_match = re.search(r'\b([A-Z][A-Z0-9]{3,}-[A-Z0-9]{4,})\b', text)

                    if url_match:
                        verification_uri = url_match.group(1).rstrip('.,;:)')
                        _pending_device_info["verification_uri"] = verification_uri
                    if code_match:
                        user_code = code_match.group(1)
                        _pending_device_info["user_code"] = user_code

                    if verification_uri:
                        url_captured_event.set()
                        return
                _time.sleep(0.5)
            url_captured_event.set()  # timeout, sinaliza mesmo assim

        # Inicia auth em background
        _auth_thread = threading.Thread(target=do_auth, daemon=True)
        _auth_thread.start()

        # Inicia monitor em background
        monitor = threading.Thread(target=monitor_output, daemon=True)
        monitor.start()

        # Espera até 10s pela URL (geralmente aparece em 1-2s)
        url_captured_event.wait(timeout=10)

        if verification_uri:
            logger.info(f"Device flow URL capturada: {verification_uri} / code: {user_code}")
            return {
                "success": False,
                "message": "Abra o link e autorize o acesso. Aguardando confirmação...",
                "phase": "device_code",
                "verification_uri": verification_uri,
                "user_code": user_code,
            }
        else:
            # Não conseguiu capturar URL — talvez já tenha autenticado via cache
            if _authenticated:
                return {"success": True, "message": "Copernicus autenticado!", "phase": "complete"}

            return {
                "success": False,
                "message": (
                    "Device flow iniciado mas não foi possível capturar a URL. "
                    "Verifique o terminal do backend."
                ),
                "phase": "device_code",
            }

    except Exception as e:
        logger.error(f"Falha na autenticação Copernicus: {e}")
        return {
            "success": False,
            "message": f"Falha na autenticação Copernicus: {e}",
            "phase": "error",
        }


# Estado compartilhado entre threads
_auth_thread = None
_pending_device_info: Dict[str, Any] = {}


class _TeeWriter:
    """Escreve simultaneamente em dois streams (ex: stdout original + StringIO)."""

    def __init__(self, *writers):
        self._writers = writers

    def write(self, text):
        for w in self._writers:
            w.write(text)

    def flush(self):
        for w in self._writers:
            if hasattr(w, "flush"):
                w.flush()

    def __getattr__(self, name):
        return getattr(self._writers[0], name)


def _refresh_connection_retry():
    """Reaplica o adapter de retry na conexão (caso a sessão tenha sido resetada)."""
    global _connection
    if _connection:
        adapter = _build_retry_adapter()
        _connection.session.mount("https://", adapter)


def _poll_job_status(job, timeout=1800, interval=15, progress_callback=None):
    """
    Polling manual do job com tolerância a erros 500 transientes.

    O start_and_wait() do openeo não tolera bem 500s consecutivos,
    então fazemos polling manual com try/except por request.

    Args:
        job: openeo BatchJob
        timeout: timeout total em segundos (default 30 min)
        interval: intervalo entre polls em segundos
        progress_callback: função(pct, msg)
    """
    start_time = time.time()
    consecutive_errors = 0
    max_consecutive_errors = 20  # tolera até 20 erros 500 seguidos (~5 min com backoff)

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise RuntimeError(
                f"Job expirou após {timeout // 60} minutos. "
                "O backend Copernicus pode estar lento. Tente novamente mais tarde."
            )

        try:
            info = job.describe()
            consecutive_errors = 0  # reset no sucesso

            status = info.get("status", "unknown")
            logger.info(f"[Copernicus] Job status: {status} (elapsed: {elapsed:.0f}s)")

            if progress_callback:
                # Estima progresso baseado no status
                pct_map = {
                    "created": 60,
                    "queued": 65,
                    "running": 75,
                    "finished": 90,
                }
                pct = pct_map.get(status, 70)
                progress_callback(pct, f"Job status: {status} ({elapsed:.0f}s)")

            if status == "finished":
                return info
            elif status == "error":
                # Tenta pegar detalhes do erro
                error_msg = "Job falhou no backend Copernicus. Status: error."
                try:
                    logs = job.logs()
                    if logs:
                        error_details = [
                            entry.get("message", "")
                            for entry in logs
                            if isinstance(entry, dict)
                            and entry.get("level", "").lower() == "error"
                        ][-3:]
                        if error_details:
                            error_msg += " Detalhes: " + " | ".join(error_details)
                except Exception:
                    pass
                raise RuntimeError(error_msg)
            elif status == "canceled":
                raise RuntimeError("Job foi cancelado no backend Copernicus.")

        except RuntimeError:
            raise  # Re-raise nossos erros intencionais
        except Exception as e:
            consecutive_errors += 1
            logger.warning(
                f"[Copernicus] Erro ao consultar job (tentativa {consecutive_errors}/"
                f"{max_consecutive_errors}): {type(e).__name__}: {e}"
            )

            if consecutive_errors >= max_consecutive_errors:
                raise RuntimeError(
                    f"Backend Copernicus instável: {consecutive_errors} erros consecutivos ao "
                    f"consultar status do job. Último erro: {e}. "
                    "O servidor pode estar fora do ar. Tente novamente mais tarde."
                )

            if progress_callback:
                progress_callback(
                    70,
                    f"Backend Copernicus temporariamente instável, "
                    f"retentando ({consecutive_errors}/{max_consecutive_errors})..."
                )

            # Backoff crescente: 15s, 20s, 25s, ... até 60s
            wait = min(interval + (consecutive_errors * 5), 60)
            time.sleep(wait)
            continue

        time.sleep(interval)


def process_sentinel(
    aoi_geojson: Dict[str, Any],
    start_date: str,
    end_date: str,
    bands: List[str],
    max_cloud: int,
    output_path: str,
    progress_callback=None,
) -> str:
    """
    Processa composição mediana do Sentinel-2 via OpenEO/Copernicus.

    Args:
        aoi_geojson: GeoJSON Polygon da AOI
        start_date: data inicial
        end_date: data final
        bands: lista de bandas (ex: ['B02','B03','B04','B08'])
        max_cloud: % máximo de nuvens por cena
        output_path: caminho de saída para o GeoTIFF
        progress_callback: função(progress_int, message_str)

    Returns:
        Caminho do arquivo salvo.
    """
    if not _authenticated or not _connection:
        raise RuntimeError("Copernicus não autenticado. Chame start_authentication() primeiro.")

    # Verifica se o token ainda é válido (tenta refresh automático)
    if not _check_token_valid():
        raise RuntimeError(
            "Token Copernicus expirado e não foi possível renovar automaticamente. "
            "Clique em 'Login Copernicus' novamente na interface."
        )

    conn = _connection

    # Reaplica retry adapter (segurança extra)
    _refresh_connection_retry()

    def update(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)
        logger.info(f"[Copernicus] {pct}% - {msg}")

    # Extrai bbox do GeoJSON
    from ..utils import geojson_to_bbox
    west, south, east, north = geojson_to_bbox(aoi_geojson)

    spatial_extent = {
        "west": west,
        "south": south,
        "east": east,
        "north": north,
    }
    temporal_extent = [start_date, end_date]

    # Precisa da banda SCL para mascarar nuvens
    load_bands = list(bands) + ["SCL"] if "SCL" not in bands else list(bands)

    update(10, "Carregando coleção Sentinel-2 L2A...")
    cube = conn.load_collection(
        "SENTINEL2_L2A",
        spatial_extent=spatial_extent,
        temporal_extent=temporal_extent,
        bands=load_bands,
        max_cloud_cover=max_cloud,
    )

    update(25, "Aplicando máscara de nuvem (SCL)...")
    scl = cube.band("SCL")

    # Classes SCL inválidas: 1=saturado, 2=dark, 3=cloud shadow,
    # 8=cloud med, 9=cloud high, 10=cirrus, 11=snow
    cloud_mask = (
        (scl == 1) | (scl == 2) | (scl == 3) |
        (scl == 8) | (scl == 9) | (scl == 10) | (scl == 11)
    )
    cube = cube.mask(cloud_mask)

    # Remove SCL das bandas finais
    final_bands = [b for b in bands if b != "SCL"]
    cube = cube.filter_bands(final_bands)

    update(40, "Calculando mediana temporal...")
    cube = cube.reduce_dimension(dimension="t", reducer="median")

    update(50, "Preparando exportação...")
    cube = cube.save_result(format="GTiff")

    # Criação do job com retry
    update(55, "Criando job assíncrono no backend Copernicus...")
    job = None
    for attempt in range(3):
        try:
            job = cube.create_job(title="SatelliteWebApp_Sentinel2_Median")
            break
        except Exception as e:
            if attempt < 2:
                wait = (attempt + 1) * 10
                logger.warning(f"[Copernicus] Erro ao criar job (tentativa {attempt + 1}): {e}. Retry em {wait}s...")
                update(55, f"Erro ao criar job, retentando ({attempt + 1}/3)...")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Falha ao criar job no Copernicus após 3 tentativas: {e}")

    # Início do job com retry
    update(58, "Iniciando job no backend Copernicus...")
    for attempt in range(3):
        try:
            job.start()
            break
        except Exception as e:
            if attempt < 2:
                wait = (attempt + 1) * 10
                logger.warning(f"[Copernicus] Erro ao iniciar job (tentativa {attempt + 1}): {e}. Retry em {wait}s...")
                update(58, f"Erro ao iniciar job, retentando ({attempt + 1}/3)...")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Falha ao iniciar job no Copernicus após 3 tentativas: {e}")

    update(60, "Aguardando processamento no backend Copernicus...")

    # Polling manual com tolerância a erros 500
    _poll_job_status(
        job,
        timeout=1800,   # 30 minutos
        interval=15,    # verifica a cada 15s
        progress_callback=progress_callback,
    )

    # Download com retry
    update(90, "Baixando resultado...")
    max_download_retries = 5
    for attempt in range(max_download_retries):
        try:
            results = job.get_results()
            results.download_file(output_path)
            break
        except Exception as e:
            if attempt < max_download_retries - 1:
                wait = (attempt + 1) * 10
                logger.warning(
                    f"[Copernicus] Erro no download (tentativa {attempt + 1}/"
                    f"{max_download_retries}): {e}. Retry em {wait}s..."
                )
                update(92, f"Erro no download, retentando ({attempt + 1}/{max_download_retries})...")
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Falha no download após {max_download_retries} tentativas: {e}"
                )

    update(96, "Recortando para o polígono exato da AOI...")
    from ..utils import clip_raster_to_geojson
    clip_raster_to_geojson(output_path, aoi_geojson, output_path)

    update(100, "Concluído!")
    return output_path
