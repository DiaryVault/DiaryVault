from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from .models import Entry, Tag, LifeChapter, Biography, Journal, JournalTag, JournalReview, EntryPhoto
from django.db import models

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

class EntryForm(forms.ModelForm):
    tags = forms.CharField(required=False, help_text="Comma-separated tags")
    entry_photo = forms.ImageField(required=False, help_text="Upload a photo for this entry")

    class Meta:
        model = Entry
        fields = ['title', 'content', 'mood', 'chapter']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'diary-font'}),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
                'placeholder': 'Entry title'
            }),
            'mood': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            }),
            'chapter': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none'
            })
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter chapters to only show user's chapters
        if self.user:
            self.fields['chapter'].queryset = LifeChapter.objects.filter(user=self.user)

        # If this is an existing entry, populate the tags field
        if self.instance and self.instance.pk:
            self.initial['tags'] = ', '.join([tag.name for tag in self.instance.tags.all()])

    def save(self, commit=True, user=None):
        user = user or self.user
        if not user:
            raise ValueError("User must be provided to save the form")

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

# Marketplace Forms
class PublishJournalForm(forms.ModelForm):
    """Form for publishing a journal to the marketplace"""

    tags = forms.CharField(
        max_length=200,
        required=False,
        help_text="Enter tags separated by commas (e.g., travel, adventure, photography)",
        widget=forms.TextInput(attrs={
            'placeholder': 'travel, adventure, photography',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    entries = forms.ModelMultipleChoiceField(
        queryset=Entry.objects.none(),  # Will be set in __init__
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text="Select the entries you want to include in this journal"
    )

    cover_image = forms.ImageField(
        required=False,
        help_text="Upload a cover image for your journal (optional)",
        widget=forms.FileInput(attrs={
            'accept': 'image/*',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    class Meta:
        model = Journal
        fields = ['title', 'description', 'price', 'cover_image']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Give your journal a compelling title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-indigo-500 focus:border-indigo-500',
                'rows': 4,
                'placeholder': 'Describe what readers can expect from your journal...'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-indigo-500 focus:border-indigo-500',
                'min': '0',
                'step': '0.01',
                'placeholder': '0.00'
            })
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # Only show entries that can be published
            publishable_entries = Entry.objects.filter(
                user=user
            ).exclude(content='').order_by('-created_at')

            # Try to filter by published_in_journal field if it exists
            try:
                publishable_entries = publishable_entries.filter(published_in_journal__isnull=True)
            except:
                pass  # Field might not exist yet

            self.fields['entries'].queryset = publishable_entries

    def clean_price(self):
        price = self.cleaned_data.get('price')

        if price and price < 0:
            raise forms.ValidationError("Price cannot be negative")

        return price or 0.00

    def clean_entries(self):
        entries = self.cleaned_data.get('entries')

        if not entries:
            raise forms.ValidationError("Please select at least one entry")

        # Check if entries meet quality criteria
        for entry in entries:
            if len(entry.content.strip()) < 100:
                raise forms.ValidationError(
                    f"Entry '{entry.title}' is too short. Entries must be at least 100 characters."
                )

        return entries

class JournalReviewForm(forms.ModelForm):
    """Form for reviewing published journals"""

    class Meta:
        model = JournalReview
        fields = ['rating', 'review_text']
        widgets = {
            'rating': forms.Select(
                choices=[(i, f"{i} Star{'s' if i != 1 else ''}") for i in range(1, 6)],
                attrs={
                    'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500'
                }
            ),
            'review_text': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500',
                'rows': 4,
                'placeholder': 'Share your thoughts about this journal...'
            })
        }

class TipForm(forms.Form):
    """Form for sending tips to authors"""

    AMOUNT_CHOICES = [
        ('1.00', '$1.00'),
        ('3.00', '$3.00'),
        ('5.00', '$5.00'),
        ('10.00', '$10.00'),
        ('custom', 'Custom amount'),
    ]

    amount_preset = forms.ChoiceField(
        choices=AMOUNT_CHOICES,
        required=False,
        widget=forms.RadioSelect(attrs={
            'class': 'mr-2'
        })
    )

    custom_amount = forms.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        validators=[MinValueValidator(0.50)],
        widget=forms.NumberInput(attrs={
            'min': '0.50',
            'step': '0.01',
            'placeholder': '0.00',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    message = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Optional message to the author...',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        amount_preset = cleaned_data.get('amount_preset')
        custom_amount = cleaned_data.get('custom_amount')

        if amount_preset == 'custom':
            if not custom_amount or custom_amount < 0.50:
                raise forms.ValidationError("Custom amount must be at least $0.50")
        elif not amount_preset:
            raise forms.ValidationError("Please select a tip amount")

        return cleaned_data

    def get_amount(self):
        """Get the actual tip amount"""
        if self.cleaned_data.get('amount_preset') == 'custom':
            return self.cleaned_data.get('custom_amount')
        else:
            return float(self.cleaned_data.get('amount_preset', 0))

class JournalSearchForm(forms.Form):
    """Form for searching and filtering journals"""

    SORT_CHOICES = [
        ('trending', 'Trending'),
        ('newest', 'Newest'),
        ('mostLiked', 'Most Liked'),
        ('mostTipped', 'Highest Earning'),
        ('staffPicks', 'Staff Picks'),
    ]

    PRICE_CHOICES = [
        ('all', 'All Journals'),
        ('free', 'Free Only'),
        ('premium', 'Premium Only'),
    ]

    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search journals...',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    category = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    sort = forms.ChoiceField(
        choices=SORT_CHOICES,
        required=False,
        initial='trending',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    price = forms.ChoiceField(
        choices=PRICE_CHOICES,
        required=False,
        initial='all',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dynamically populate category choices
        try:
            categories = JournalTag.objects.annotate(
                count=models.Count('journal')
            ).filter(count__gt=0).order_by('name')

            category_choices = [('all', 'All Categories')] + [
                (tag.slug, f"{tag.name} ({tag.count})") for tag in categories
            ]

            self.fields['category'].widget.choices = category_choices
        except:
            # Fallback if JournalTag doesn't exist yet
            self.fields['category'].widget.choices = [('all', 'All Categories')]
