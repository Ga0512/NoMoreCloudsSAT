"""
Gerenciador de jobs em memória.
Armazena status, progresso e resultado de cada job de processamento.
"""
import uuid
from datetime import datetime
from typing import Dict, Optional
from .models import JobInfo, JobStatus


class JobManager:
    """Gerenciador de jobs em memória (para uso local)."""

    def __init__(self):
        self._jobs: Dict[str, JobInfo] = {}

    def create_job(self, provider: str) -> str:
        """Cria um novo job e retorna o job_id."""
        job_id = str(uuid.uuid4())[:8]
        self._jobs[job_id] = JobInfo(
            job_id=job_id,
            provider=provider,
            status=JobStatus.PENDING,
            created_at=datetime.now().isoformat(),
            message="Job criado, aguardando início...",
            progress=0,
        )
        return job_id

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        """Retorna informações do job ou None."""
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        message: Optional[str] = None,
        progress: Optional[int] = None,
        output_file: Optional[str] = None,
    ):
        """Atualiza campos do job."""
        job = self._jobs.get(job_id)
        if not job:
            return
        if status is not None:
            job.status = status
        if message is not None:
            job.message = message
        if progress is not None:
            job.progress = progress
        if output_file is not None:
            job.output_file = output_file

    def list_jobs(self) -> list:
        """Retorna todos os jobs ordenados por data de criação (mais recente primeiro)."""
        return sorted(
            self._jobs.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )


# Instância global (singleton)
job_manager = JobManager()
