from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
import re

class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter to handle username generation"""

    def generate_unique_username(self, txts, regex=None):
        """Generate a unique username from the given text fragments"""
        if isinstance(txts, list):
            username = ''.join(txts)
        else:
            username = str(txts)

        # Clean username
        username = re.sub(r'[^a-zA-Z0-9_]', '', username)[:15]
        if not username or not username[0].isalpha():
            username = 'user'

        # Make unique
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        return username

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter to auto-generate usernames"""

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social login. Auto-generates username.
        """
        user = sociallogin.user

        # Auto-generate username if not set
        if not user.username:
            email = sociallogin.account.extra_data.get('email', '')
            if email and '@' in email:
                base = email.split('@')[0]
            else:
                # Use name from Google if available
                name = sociallogin.account.extra_data.get('given_name', '') or \
                       sociallogin.account.extra_data.get('name', '') or 'user'
                base = name

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
        return user

    def is_auto_signup_allowed(self, request, sociallogin):
        """Allow auto-signup for social accounts"""
        return True

    def is_open_for_signup(self, request, sociallogin):
        """Always allow signup for social accounts"""
        return True
