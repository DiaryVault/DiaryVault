from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.validators import MinValueValidator, MaxValueValidator
from .models import Entry, Tag, Journal, JournalTag, JournalReview, EntryPhoto, UserProfile
from django.db import models

User = get_user_model()

def auto_generate_tags(content, mood=None):
    """Generate tags based on entry content and mood"""
    tags = set()

    # Common topics to check for
    topic_keywords = {
        'work': ['work', 'job', 'career', 'office', 'meeting', 'project', 'boss', 'colleague'],
        'family': ['family', 'parents', 'mom', 'dad', 'children', 'kids', 'brother', 'sister'],
        'health': ['health', 'workout', 'exercise', 'doctor', 'fitness', 'gym', 'running'],
        'food': ['food', 'dinner', 'lunch', 'breakfast', 'meal', 'cooking', 'restaurant'],
        'travel': ['travel', 'trip', 'vacation', 'journey', 'flight', 'hotel'],
        'learning': ['learning', 'study', 'read', 'book', 'class', 'course'],
        'friends': ['friend', 'social', 'party', 'hangout', 'gathering'],
        'goals': ['goal', 'plan', 'future', 'aspiration', 'dream', 'objective'],
        'reflection': ['reflection', 'thinking', 'contemplation', 'introspection', 'mindfulness']
    }

    # Convert content to lowercase for case-insensitive matching
    content_lower = content.lower()

    # Check for topic keywords in content
    for topic, keywords in topic_keywords.items():
        for keyword in keywords:
            if keyword in content_lower:
                tags.add(topic)
                break

    # Add mood as a tag if provided
    if mood:
        tags.add(mood.lower())

    return list(tags)

# ============================================================================
# User Authentication Forms (Standard Django fields only)
# ============================================================================

class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form - using only standard User fields"""
    
    email = forms.EmailField(
        max_length=254, 
        required=False, 
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'Email address (optional)'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
                'placeholder': 'Username'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        
        # Add CSS classes to password fields
        self.fields['password1'].widget.attrs.update({
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'Confirm password'
        })


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form - using only standard User fields"""
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove password field from change form
        if 'password' in self.fields:
            del self.fields['password']


class UserProfileForm(forms.ModelForm):
    """Form for users to update their profile - standard fields only"""
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already in use.")
        return email


# Legacy SignUpForm (keeping for backwards compatibility)
class SignUpForm(UserCreationForm):
    email = forms.EmailField(max_length=254, required=True, widget=forms.EmailInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
        'placeholder': 'Email address'
    }))

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
                'placeholder': 'Username'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'Confirm password'
        })

# ============================================================================
# Journal Entry Forms
# ============================================================================

class EntryForm(forms.ModelForm):
    tags = forms.CharField(required=False, help_text="Comma-separated tags")
    entry_photo = forms.ImageField(required=False, help_text="Upload a photo for this entry")

    class Meta:
        model = Entry
        fields = ['title', 'content', 'mood']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'diary-font'}),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
                'placeholder': 'Entry title'
            }),
            'mood': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            })
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # If this is an existing entry, populate the tags field
        if self.instance and self.instance.pk:
            self.initial['tags'] = ', '.join([tag.name for tag in self.instance.tags.all()])

    def clean(self):
        """Override clean to allow validation without requiring a user"""
        cleaned_data = super().clean()
        return cleaned_data

    def save(self, commit=True, user=None):
        """
        Save method that supports both authenticated and anonymous usage.
        For anonymous users, this returns the form data without saving to database.
        """
        user = user or self.user
        
        # For anonymous users, return the entry data without saving
        if not user:
            # Create a non-persisted entry object with the form data
            entry = super().save(commit=False)
            
            # Return a dictionary with the entry data for session storage
            entry_data = {
                'title': entry.title,
                'content': entry.content,
                'mood': entry.mood,
                'tags': self.cleaned_data.get('tags', ''),
                'has_photo': bool(self.files.get('entry_photo'))
            }
            
            # Process tags for the session data
            manual_tags = []
            if self.cleaned_data.get('tags'):
                manual_tags = [t.strip() for t in self.cleaned_data['tags'].split(',') if t.strip()]
            
            # Generate automatic tags
            auto_tags = auto_generate_tags(entry.content, entry.mood)
            
            # Combine tags
            all_tags = list(set(manual_tags + auto_tags))
            entry_data['tags'] = all_tags
            
            return entry_data
        
        # For authenticated users, proceed with normal save
        entry = super().save(commit=False)
        entry.user = user

        if commit:
            entry.save()

            # Handle photo upload if present
            if 'entry_photo' in self.files:
                photo = EntryPhoto(
                    entry=entry,
                    photo=self.files['entry_photo']
                )
                photo.save()

            # Get manually entered tags if any
            manual_tags = []
            if 'tags' in self.cleaned_data and self.cleaned_data['tags']:
                manual_tags = [t.strip() for t in self.cleaned_data['tags'].split(',') if t.strip()]

            # Generate automatic tags based on content
            auto_tags = auto_generate_tags(entry.content, entry.mood)

            # Combine manual and auto tags (manual tags take priority)
            all_tags = set(manual_tags + auto_tags)

            # Clear existing tags
            entry.tags.clear()

            # Add each tag, creating new ones as needed
            for tag_name in all_tags:
                if tag_name:  # Skip empty tags
                    tag, created = Tag.objects.get_or_create(
                        name=tag_name.lower(),  # Normalize to lowercase
                        user=user
                    )
                    entry.tags.add(tag)

        return entry

    def save_anonymous(self):
        """
        Convenience method specifically for anonymous users.
        Returns a dictionary of entry data suitable for session storage.
        """
        return self.save(commit=False, user=None)
    
# ============================================================================
# Enhanced Profile Forms (using UserProfile model)
# ============================================================================

class Web3ProfileForm(forms.ModelForm):
    """Enhanced profile form with UserProfile integration"""
    
    # UserProfile fields
    bio = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'Tell us about yourself...'
        })
    )
    
    location = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'Your location'
        })
    )
    
    website = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
            'placeholder': 'https://yourwebsite.com'
        })
    )
    
    birth_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate UserProfile fields if they exist
        if self.instance and hasattr(self.instance, 'userprofile'):
            profile = self.instance.userprofile
            self.fields['bio'].initial = profile.bio
            self.fields['location'].initial = profile.location
            self.fields['website'].initial = profile.website
            self.fields['birth_date'].initial = profile.birth_date

    def save(self, commit=True):
        user = super().save(commit=commit)
        
        if commit:
            # Update or create UserProfile
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.bio = self.cleaned_data.get('bio', '')
            profile.location = self.cleaned_data.get('location', '')
            profile.website = self.cleaned_data.get('website', '')
            profile.birth_date = self.cleaned_data.get('birth_date')
            profile.save()
        
        return user