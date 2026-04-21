from django.apps import AppConfig


class ThemesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'themes'

    def ready(self):
        # Connect post_migrate signal to seed default themes after migrations run
        from django.db.models.signals import post_migrate
        from . import signals
        post_migrate.connect(signals.seed_default_themes, sender=self)
