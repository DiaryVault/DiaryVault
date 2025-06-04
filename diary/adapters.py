# Create this file: diary/adapters.py

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_email, user_field
from allauth.socialaccount.models import SocialLogin
from django.contrib.auth.models import User
import re


class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter to handle username generation"""

    def generate_unique_username(self, txts, regex=None):
        """Generate a unique username from the given text fragments"""
        # Clean and join the text fragments
        username = self.clean_username_base(txts)

        # If username is taken, add numbers
        if User.objects.filter(username=username).exists():
            counter = 1
            base_username = username
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

        return username

    def clean_username_base(self, txts):
        """Clean username components and create base username"""
        # Join all text fragments
        username = ''.join(txts)

        # Remove invalid characters (keep only letters, numbers, underscores)
        username = re.sub(r'[^a-zA-Z0-9_]', '', username)

        # Ensure it starts with a letter
        if username and not username[0].isalpha():
            username = 'user' + username

        # Limit length
        username = username[:20]

        # Fallback if empty
        if not username:
            username = 'user'

        return username.lower()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter to auto-generate usernames"""

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social login. In case of auto-signup,
        this method is responsible for creating the user.
        """
        user = sociallogin.user

        # Auto-generate username if not provided
        if not user.username:
            user.username = self.generate_username_from_social_login(sociallogin)

        # Set email if available
        if sociallogin.account.extra_data.get('email'):
            user_email(user, sociallogin.account.extra_data['email'])

        # Set first/last name if available
        if sociallogin.account.extra_data.get('given_name'):
            user_field(user, 'first_name', sociallogin.account.extra_data['given_name'])

        if sociallogin.account.extra_data.get('family_name'):
            user_field(user, 'last_name', sociallogin.account.extra_data['family_name'])

        # Save the user
        user.save()
        return user

    def generate_username_from_social_login(self, sociallogin):
        """Generate username from social login data"""
        extra_data = sociallogin.account.extra_data

        # Try different sources for username generation
        username_parts = []

        # Option 1: Use name components
        if extra_data.get('given_name'):
            username_parts.append(extra_data['given_name'])
        if extra_data.get('family_name'):
            username_parts.append(extra_data['family_name'])

        # Option 2: Use email prefix
        if not username_parts and extra_data.get('email'):
            email_prefix = extra_data['email'].split('@')[0]
            username_parts.append(email_prefix)

        # Option 3: Use display name
        if not username_parts and extra_data.get('name'):
            username_parts.append(extra_data['name'])

        # Option 4: Fallback
        if not username_parts:
            username_parts.append('user')

        # Generate base username
        base_username = self.clean_username(''.join(username_parts))

        # Ensure uniqueness
        return self.generate_unique_username(base_username)

    def clean_username(self, username):
        """Clean username to be valid"""
        # Remove invalid characters
        username = re.sub(r'[^a-zA-Z0-9_]', '', username)

        # Ensure it starts with a letter
        if username and not username[0].isalpha():
            username = 'user' + username

        # Limit length
        username = username[:20]

        # Fallback if empty
        if not username:
            username = 'user'

        return username.lower()

    def generate_unique_username(self, base_username):
        """Generate unique username by appending numbers if needed"""
        username = base_username
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        return username

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Allow auto-signup for social accounts
        This skips the signup form entirely
        """
        return True


# Alternative simpler approach - just for username generation
class SimpleAutoUsernameAdapter(DefaultSocialAccountAdapter):
    """Simplified version that just auto-generates usernames"""

    def save_user(self, request, sociallogin, form=None):
        user = sociallogin.user

        # Auto-generate username if not set
        if not user.username:
            # Use email prefix as base
            email = sociallogin.account.extra_data.get('email', '')
            if email:
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

        user.save()
        return user
