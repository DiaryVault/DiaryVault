from django.db import models
from django.contrib.auth.models import User

class Tag(models.Model):
    name = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.name

class DiaryEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    content = models.TextField()
    summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True)  

    def __str__(self):
        return self.title

class SummaryVersion(models.Model):
    entry = models.ForeignKey(DiaryEntry, on_delete=models.CASCADE, related_name="versions")
    summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Version for {self.entry.title} @ {self.created_at.strftime('%Y-%m-%d %H:%M')}"
