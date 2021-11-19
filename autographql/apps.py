from django.apps import AppConfig


class AutographqlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'autographql'

    def ready(self):
        import autographql.converters
        import autographql.filters.converters
        import autographql.monkeypatch
