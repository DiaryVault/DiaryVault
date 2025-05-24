from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random

from diary.models import Entry, Journal, JournalEntry, JournalTag

class Command(BaseCommand):
    help = 'Create marketplace journals from existing entries'

    def handle(self, *args, **options):
        self.stdout.write('Creating marketplace journals from entries...')

        # Get sample users
        sample_users = User.objects.filter(username__startswith='sample_user')

        if not sample_users.exists():
            self.stdout.write(self.style.ERROR('No sample users found. Run create_sample_data first.'))
            return

        # Create journal tags
        tag_names = ['Personal Growth', 'Daily Life', 'Reflections', 'Work Life', 'Family', 'Travel']
        journal_tags = []

        for tag_name in tag_names:
            tag, created = JournalTag.objects.get_or_create(
                name=tag_name,
                defaults={
                    'slug': tag_name.lower().replace(' ', '-'),
                    'description': f'Journals about {tag_name.lower()}',
                    'color': random.choice(['blue', 'green', 'purple', 'red', 'amber'])
                }
            )
            journal_tags.append(tag)
            if created:
                self.stdout.write(f'Created journal tag: {tag.name}')

        journals_created = 0

        for user in sample_users:
            user_entries = Entry.objects.filter(user=user)

            if user_entries.count() < 5:
                continue

            # Create 2 journals per user
            journal_configs = [
                {
                    'title': f'{user.first_name}\'s Personal Journey',
                    'description': 'A collection of personal reflections and daily experiences, capturing moments of growth, challenges, and insights from everyday life.',
                    'price': 0.00,
                    'tags': ['Personal Growth', 'Daily Life']
                },
                {
                    'title': f'Life Reflections by {user.first_name}',
                    'description': 'Thoughtful entries exploring life\'s ups and downs, work experiences, and family moments. An authentic look into one person\'s journey.',
                    'price': random.choice([0.00, 4.99, 7.99, 9.99]),
                    'tags': ['Reflections', 'Work Life', 'Family']
                }
            ]

            for config in journal_configs:
                # Create journal
                journal = Journal.objects.create(
                    title=config['title'],
                    description=config['description'],
                    author=user,
                    is_published=True,
                    privacy_setting='public'
                )

                # Set price if field exists
                if hasattr(journal, 'price'):
                    journal.price = config['price']

                # Set publication date if field exists
                if hasattr(journal, 'date_published'):
                    journal.date_published = timezone.now() - timedelta(days=random.randint(1, 30))

                # Set view count if field exists
                if hasattr(journal, 'view_count'):
                    journal.view_count = random.randint(10, 500)

                # Set total tips if field exists
                if hasattr(journal, 'total_tips'):
                    journal.total_tips = random.randint(0, 50) if config['price'] == 0 else random.randint(0, 100)

                journal.save()

                # Add tags if field exists
                if hasattr(journal, 'marketplace_tags'):
                    for tag_name in config['tags']:
                        tag = next((t for t in journal_tags if t.name == tag_name), None)
                        if tag:
                            journal.marketplace_tags.add(tag)

                # Add some entries to the journal
                sample_entries = random.sample(list(user_entries), min(random.randint(3, 8), user_entries.count()))

                for entry in sample_entries:
                    try:
                        JournalEntry.objects.create(
                            journal=journal,
                            title=entry.title,
                            content=entry.content,
                            entry_date=entry.created_at.date(),
                            is_included=True
                        )
                    except Exception as e:
                        # If JournalEntry model doesn't exist, skip
                        pass

                # Add to likes if field exists
                if hasattr(journal, 'likes'):
                    # Add some random likes from other sample users
                    other_users = sample_users.exclude(id=user.id)
                    likers = random.sample(list(other_users), min(random.randint(0, 3), len(other_users)))
                    for liker in likers:
                        journal.likes.add(liker)

                journals_created += 1
                self.stdout.write(f'Created journal: {journal.title}')

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {journals_created} marketplace journals!')
        )
