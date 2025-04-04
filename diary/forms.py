from django import forms
from .models import DiaryEntry, Tag

class DiaryEntryForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = DiaryEntry
        fields = ['title', 'content', 'tags']
