import json
import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.serializers import serialize

from diary.models import Entry, Tag, LifeChapter, Journal

class Command(BaseCommand):
    help = 'Backup user data to JSON files'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='Username to backup')
        parser.add_argument('--output-dir', default='./backups', help='Output directory')

    def handle(self, *args, **options):
        username = options['username']
        output_dir = options['output_dir']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {username} not found'))
            return

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        backup_data = {
            'user': {
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'date_joined': user.date_joined.isoformat(),
            },
            'entries': [],
            'tags': [],
            'chapters': [],
            'journals': []
        }

        # Backup entries
        for entry in Entry.objects.filter(user=user):
            entry_data = {
                'title': entry.title,
                'content': entry.content,
                'created_at': entry.created_at.isoformat(),
                'mood': entry.mood,
                'tags': [tag.name for tag in entry.tags.all()],
                'chapter': entry.chapter.title if entry.chapter else None
            }
            backup_data['entries'].append(entry_data)

        # Backup tags
        for tag in Tag.objects.filter(user=user):
            backup_data['tags'].append({
                'name': tag.name
            })

        # Backup chapters
        for chapter in LifeChapter.objects.filter(user=user):
            backup_data['chapters'].append({
                'title': chapter.title,
                'description': chapter.description,
                'start_date': chapter.start_date.isoformat() if chapter.start_date else None,
                'end_date': chapter.end_date.isoformat() if chapter.end_date else None,
                'is_active': chapter.is_active
            })

        # Backup journals
        for journal in Journal.objects.filter(author=user):
            backup_data['journals'].append({
                'title': journal.title,
                'description': journal.description,
                'is_published': journal.is_published,
                'created_at': journal.created_at.isoformat()
            })

        # Save to file
        filename = f'{username}_backup_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)

        self.stdout.write(
            self.style.SUCCESS(f'Backup saved to {filepath}')
        )
        self.stdout.write(f'Backed up {len(backup_data["entries"])} entries')
