"""
System service - real system status from database.
"""

from repositories import project_repo, task_repo


class SystemService:
    def get_status(self) -> dict:
        projects = project_repo.get_all_projects()
        active = sum(1 for p in projects if p["status"] == "in_progress")

        # Count pending tasks across all projects
        total_pending = 0
        for p in projects:
            if p["status"] == "in_progress":
                total_pending += len(task_repo.get_pending_tasks(p["project_id"]))

        # Check if LLM, image, and video providers are configured
        from integrations.llm import is_llm_configured
        from integrations.image import is_image_configured
        from repositories.settings_repo import get_setting

        llm_ok = is_llm_configured()
        image_ok = is_image_configured()
        video_ok = bool(get_setting("video_api_key"))

        return {
            "status": "operational",
            "active_projects": active,
            "queue_length": total_pending,
            "api_status": {
                "llm": "healthy" if llm_ok else "not_configured",
                "image_generation": "healthy" if image_ok else "not_configured",
                "video_generation": "healthy" if video_ok else "not_configured",
                "audio_generation": "not_configured",
            },
            "resources": {
                "cpu_usage": "N/A",
                "memory_usage": "N/A",
                "gpu_usage": "N/A",
            },
        }
