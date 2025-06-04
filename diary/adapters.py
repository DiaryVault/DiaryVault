# diary/adapters.py

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
import uuid

class CustomAccountAdapter(DefaultAccountAdapter):
    def generate_unique_username(self, txts):
        """Generate a unique username for the user"""
        # Use first part of email or generate random username
        base_username = None

        for txt in txts:
            if txt and '@' in txt:
                base_username = txt.split('@')[0]
                break

        if not base_username:
            base_username = f"user_{uuid.uuid4().hex[:8]}"

        # Ensure username is unique
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        return username

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a
        social provider, but before the login is actually processed.
        """
        # If user exists with this email, connect the accounts
        email = sociallogin.account.extra_data.get('email')
        if email:
            try:
                user = User.objects.get(email=email)
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social login. In case of auto-signup,
        this method is responsible for creating the user instance.
        """
        user = sociallogin.user

        # Generate username if not provided
        if not user.username:
            email = user.email or sociallogin.account.extra_data.get('email', '')
            if email:
                user.username = self.generate_unique_username([email])
            else:
                user.username = f"user_{uuid.uuid4().hex[:8]}"

        # Set email from social account if not present
        if not user.email and sociallogin.account.extra_data.get('email'):
            user.email = sociallogin.account.extra_data.get('email')

        # Set first/last name from social account
        if sociallogin.account.provider == 'microsoft':
            # Microsoft specific data extraction
            if not user.first_name and sociallogin.account.extra_data.get('given_name'):
                user.first_name = sociallogin.account.extra_data.get('given_name')
            if not user.last_name and sociallogin.account.extra_data.get('family_name'):
                user.last_name = sociallogin.account.extra_data.get('family_name')
            if not user.first_name and sociallogin.account.extra_data.get('givenName'):
                user.first_name = sociallogin.account.extra_data.get('givenName')
            if not user.last_name and sociallogin.account.extra_data.get('surname'):
                user.last_name = sociallogin.account.extra_data.get('surname')

        # Google and other providers
        if not user.first_name and sociallogin.account.extra_data.get('given_name'):
            user.first_name = sociallogin.account.extra_data.get('given_name')
        if not user.last_name and sociallogin.account.extra_data.get('family_name'):
            user.last_name = sociallogin.account.extra_data.get('family_name')

        # If no separate first/last name, try to split the name
        if not user.first_name and sociallogin.account.extra_data.get('name'):
            name_parts = sociallogin.account.extra_data.get('name', '').split(' ', 1)
            user.first_name = name_parts[0] if name_parts else ''
            user.last_name = name_parts[1] if len(name_parts) > 1 else ''

        user.save()
        return user

    def generate_unique_username(self, txts):
        """Generate a unique username for the user"""
        base_username = None

        for txt in txts:
            if txt and '@' in txt:
                base_username = txt.split('@')[0]
                break

        if not base_username:
            base_username = f"user_{uuid.uuid4().hex[:8]}"

        # Ensure username is unique
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        return username

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Checks whether or not the site allows for signup via the
        passed SocialLogin instance.
        """
        # ALWAYS allow auto signup for social logins
        return True

    def new_user(self, request, sociallogin):
        """
        Instantiates a new User instance.
        """
        user = super().new_user(request, sociallogin)

        # Ensure we have a username
        if not user.username:
            email = sociallogin.account.extra_data.get('email', '')
            if email:
                user.username = self.generate_unique_username([email])
            else:
                user.username = f"user_{uuid.uuid4().hex[:8]}"

        return user
