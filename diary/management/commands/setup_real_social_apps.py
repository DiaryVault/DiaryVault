import os
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp

class Command(BaseCommand):
    help = 'Setup real social authentication apps with environment credentials'

    def handle(self, *args, **options):
        # Get or update the current site
        site = Site.objects.get(pk=1)  # Assumes site ID 1 exists
        site.domain = 'diaryvault.com'
        site.name = 'DiaryVault'
        site.save()
        self.stdout.write(f'✓ Updated site: {site.domain}')

        # Google OAuth Setup
        google_client_id = os.getenv('GOOGLE_CLIENT_ID')
        google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

        if google_client_id and google_client_secret:
            # Remove existing Google app if it exists
            SocialApp.objects.filter(provider='google').delete()

            # Create Google app with real credentials
            google_app = SocialApp.objects.create(
                provider='google',
                name='Google OAuth',
                client_id=google_client_id,
                secret=google_client_secret,
            )
            google_app.sites.add(site)
            self.stdout.write(self.style.SUCCESS('✓ Created Google OAuth with real credentials'))
        else:
            self.stdout.write(self.style.ERROR('✗ Missing Google OAuth credentials in environment'))

        # Microsoft OAuth Setup
        microsoft_client_id = os.getenv('MICROSOFT_CLIENT_ID')
        microsoft_client_secret = os.getenv('MICROSOFT_CLIENT_SECRET')

        if microsoft_client_id and microsoft_client_secret:
            # Remove existing Microsoft app if it exists
            SocialApp.objects.filter(provider='microsoft').delete()

            # Create Microsoft app with real credentials
            microsoft_app = SocialApp.objects.create(
                provider='microsoft',
                name='Microsoft OAuth',
                client_id=microsoft_client_id,
                secret=microsoft_client_secret,
            )
            microsoft_app.sites.add(site)
            self.stdout.write(self.style.SUCCESS('✓ Created Microsoft OAuth with real credentials'))
        else:
            self.stdout.write(self.style.ERROR('✗ Missing Microsoft OAuth credentials in environment'))

        # Apple OAuth Setup (skip if not available)
        apple_client_id = os.getenv('APPLE_CLIENT_ID')
        apple_secret = os.getenv('APPLE_SECRET')

        if apple_client_id and apple_secret and apple_client_id != 'your_apple_client_id_here':
            # Remove existing Apple app if it exists
            SocialApp.objects.filter(provider='apple').delete()

            # Create Apple app with real credentials
            apple_app = SocialApp.objects.create(
                provider='apple',
                name='Apple OAuth',
                client_id=apple_client_id,
                secret=apple_secret,
            )
            apple_app.sites.add(site)
            self.stdout.write(self.style.SUCCESS('✓ Created Apple OAuth with real credentials'))
        else:
            self.stdout.write(self.style.WARNING('⚠ Skipping Apple OAuth (credentials not configured)'))

        self.stdout.write(
            self.style.SUCCESS(
                '\n🎉 Social authentication setup complete!'
                '\nYour login page should now show working social login buttons.'
            )
        )

        # Important reminders
        self.stdout.write(
            self.style.HTTP_INFO(
                '\n📋 Important reminders:'
                '\n1. Ensure your OAuth redirect URIs are configured correctly:'
                '\n   - Google: https://diaryvault.com/accounts/google/login/callback/'
                '\n   - Microsoft: https://diaryvault.com/accounts/microsoft/login/callback/'
                '\n   - For testing: also add http://localhost:8000/accounts/[provider]/login/callback/'
                '\n2. Test each social login to ensure they work'
                '\n3. Check Django admin to verify the applications were created'
            )
        )
