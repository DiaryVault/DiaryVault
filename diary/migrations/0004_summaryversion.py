# Generated by Django 5.1.8 on 2025-04-03 04:17

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diary', '0003_diaryentry_summary'),
    ]

    operations = [
        migrations.CreateModel(
            name='SummaryVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('summary', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='diary.diaryentry')),
            ],
        ),
    ]
