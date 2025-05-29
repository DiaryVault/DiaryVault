from django.conf import settings

def stripe_keys(request):
    return {
        'STRIPE_PUBLISHABLE_KEY': getattr(settings, 'STRIPE_PUBLISHABLE_KEY', ''),
    }
