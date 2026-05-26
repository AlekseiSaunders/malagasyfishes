from django.apps import AppConfig


class SubmissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "submissions"
    verbose_name = "Curated Submissions"

    def ready(self) -> None:
        # Wire the post_delete signal that reopens a submission when its
        # promoted population is deleted (Gate 15 AC-15.16).
        from submissions import signals  # noqa: F401
