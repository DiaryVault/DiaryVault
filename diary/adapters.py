from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.urls import reverse
import re

class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter"""
    pass

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter to auto-generate usernames and FORCE auto-signup"""

    def is_auto_signup_allowed(self, request, sociallogin):
        """ALWAYS allow auto-signup"""
        return True

    def is_open_for_signup(self, request, sociallogin):
        """ALWAYS allow signup"""
        return True

    def save_user(self, request, sociallogin, form=None):
        """FORCE save user without any forms"""
        print("🔍 CustomSocialAccountAdapter.save_user called!")
        print(f"sociallogin.is_existing: {sociallogin.is_existing}")

        user = sociallogin.user

        # Auto-generate username if not set
        if not user.username:
            email = sociallogin.account.extra_data.get('email', '')
            if email and '@' in email:
                base = email.split('@')[0]
            else:
                base = 'user'

            # Clean username
            base = re.sub(r'[^a-zA-Z0-9_]', '', base)[:15]
            if not base or not base[0].isalpha():
                base = 'user'

            # Make unique
            username = base
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}{counter}"
                counter += 1

            user.username = username

        # Set email
        if sociallogin.account.extra_data.get('email'):
            user.email = sociallogin.account.extra_data['email']

        # Set first/last name if available
        if sociallogin.account.extra_data.get('given_name'):
            user.first_name = sociallogin.account.extra_data['given_name']
        if sociallogin.account.extra_data.get('family_name'):
            user.last_name = sociallogin.account.extra_data['family_name']

        user.save()
        print(f"✅ User created: {user.username} ({user.email})")
        return user

    def get_signup_form_initial_data(self, sociallogin):
        """Don't show any signup form"""
        return {}

    def pre_social_login(self, request, sociallogin):
        """Hook before social login processing"""
        print(f"🔍 pre_social_login: existing={sociallogin.is_existing}")
