from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Entry, Tag, LifeChapter, Biography

class EntryForm(forms.ModelForm):
    tags = forms.CharField(required=False, help_text="Comma-separated tags")

    class Meta:
        model = Entry
        fields = ['title', 'content', 'mood', 'chapter']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'diary-font'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.initial['tags'] = ', '.join([tag.name for tag in self.instance.tags.all()])

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

def save(self, commit=True, user=None):
    user = user or self.user
    if not user:
        raise ValueError("User must be provided to save the form")

    entry = super().save(commit=False)
    entry.user = user

    if commit:
        entry.save()

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

class LifeChapterForm(forms.ModelForm):
    class Meta:
        model = LifeChapter
        fields = ['title', 'description', 'color']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
                'placeholder': 'Chapter title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-sky-400 focus:outline-none',
                'placeholder': 'Describe this chapter of your life...',
                'rows': 3
            }),
            'color': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }, choices=[
                ('sky-600', 'Blue'),
                ('indigo-600', 'Indigo'),
                ('emerald-600', 'Green'),
                ('amber-600', 'Amber'),
                ('rose-600', 'Red'),
                ('purple-700', 'Purple'),
                ('pink-600', 'Pink')
            ])
        }
