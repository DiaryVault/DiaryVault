# Generated by Django 5.1.8 on 2025-04-03 04:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diary', '0002_diaryentry_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='diaryentry',
            name='summary',
            field=models.TextField(blank=True, null=True),
        ),
    ]
