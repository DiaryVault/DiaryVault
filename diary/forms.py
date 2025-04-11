from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Entry, Tag, LifeChapter, Biography

class EntryForm(forms.ModelForm):
    tags = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
        'placeholder': 'Add tags separated by commas'
    }))

    class Meta:
        model = Entry
        fields = ['title', 'content']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-sky-400 focus:outline-none',
                'placeholder': 'Title your entry...'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-sky-400 focus:outline-none diary-font',
                'placeholder': 'Write your thoughts here...',
                'rows': 8
            })
        }

    def save(self, commit=True, user=None):
        entry = super().save(commit=False)
        if user:
            entry.user = user

        if commit:
            entry.save()

            # Handle tags
            if self.cleaned_data['tags']:
                tag_names = [tag.strip() for tag in self.cleaned_data['tags'].split(',')]
                for tag_name in tag_names:
                    if tag_name:
                        tag, created = Tag.objects.get_or_create(name=tag_name, user=user)
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
