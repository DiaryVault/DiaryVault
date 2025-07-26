from django.apps import AppConfig

class DiaryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'diary'

    def ready(self):
        import diary.signals  # Import signals when app is ready

class Web3authConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'web3auth'
    verbose_name = 'Web3 Authentication'
    
    def ready(self):
        # Import signals when app is ready
        import web3auth.signals
