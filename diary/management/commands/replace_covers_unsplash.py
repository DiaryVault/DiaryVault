from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils.text import slugify
import random
import requests
import time

from diary.models import Journal

class Command(BaseCommand):
    help = 'Replace all journal covers with real Unsplash photos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of journals to process (for testing)'
        )

    def handle(self, *args, **options):
        limit = options['limit']

        # Get all published journals
        journals = Journal.objects.filter(is_published=True)

        if limit:
            journals = journals[:limit]
            self.stdout.write(f'Processing first {limit} journals...')
        else:
            self.stdout.write(f'Processing ALL {journals.count()} published journals...')

        if not journals.exists():
            self.stdout.write(self.style.ERROR('No published journals found!'))
            return

        processed = 0
        errors = 0

        for journal in journals:
            try:
                # Get themed search term based on journal
                search_term = self.get_search_term_for_journal(journal)

                # Download and save Unsplash image
                success = self.download_unsplash_image(journal, search_term)

                if success:
                    processed += 1
                    self.stdout.write(f'✅ Updated: {journal.title[:60]}... (theme: {search_term})')
                else:
                    errors += 1
                    self.stdout.write(f'❌ Failed: {journal.title[:60]}...')

                # Small delay to be nice to Unsplash
                time.sleep(0.5)

                if processed % 10 == 0:
                    self.stdout.write(f'--- Progress: {processed}/{journals.count()} ---')

            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.WARNING(f'Error with "{journal.title}": {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 Complete! {processed} successful, {errors} errors'
            )
        )

    def get_search_term_for_journal(self, journal):
        """Get appropriate search term based on journal content"""

        # Default themes for journals
        default_themes = [
            'journal', 'notebook', 'writing', 'diary', 'book', 'paper',
            'minimalist', 'aesthetic', 'peaceful', 'calm'
        ]

        # Check journal tags first
        if hasattr(journal, 'marketplace_tags') and journal.marketplace_tags.exists():
            tag_names = [tag.name.lower() for tag in journal.marketplace_tags.all()]

            # Travel themes
            if any(word in ' '.join(tag_names) for word in ['travel', 'adventure', 'journey']):
                return random.choice([
                    'travel', 'adventure', 'wanderlust', 'journey', 'explore',
                    'mountains', 'ocean', 'landscape', 'destination', 'backpack'
                ])

            # Health & wellness themes
            elif any(word in ' '.join(tag_names) for word in ['health', 'mental', 'wellness', 'fitness']):
                return random.choice([
                    'wellness', 'meditation', 'mindfulness', 'yoga', 'nature',
                    'peaceful', 'zen', 'balance', 'harmony', 'healing'
                ])

            # Creative themes
            elif any(word in ' '.join(tag_names) for word in ['creative', 'art', 'design']):
                return random.choice([
                    'art', 'creativity', 'inspiration', 'design', 'artistic',
                    'colors', 'paint', 'canvas', 'studio', 'create'
                ])

            # Parenting themes
            elif any(word in ' '.join(tag_names) for word in ['parent', 'family', 'child']):
                return random.choice([
                    'family', 'love', 'together', 'home', 'warmth',
                    'happiness', 'joy', 'connection', 'care', 'gentle'
                ])

            # Career themes
            elif any(word in ' '.join(tag_names) for word in ['career', 'work', 'business', 'entrepreneur']):
                return random.choice([
                    'success', 'growth', 'business', 'professional', 'achievement',
                    'goals', 'focus', 'determination', 'progress', 'vision'
                ])

            # Personal growth themes
            elif any(word in ' '.join(tag_names) for word in ['growth', 'personal', 'self']):
                return random.choice([
                    'growth', 'transformation', 'reflection', 'wisdom', 'insight',
                    'journey', 'progress', 'development', 'mindful', 'clarity'
                ])

        # Check journal title for themes
        title_lower = journal.title.lower()

        if any(word in title_lower for word in ['travel', 'journey']):
            return random.choice(['travel', 'adventure', 'journey', 'wanderlust'])
        elif any(word in title_lower for word in ['health', 'wellness', 'mind']):
            return random.choice(['wellness', 'meditation', 'peaceful', 'nature'])
        elif any(word in title_lower for word in ['creative', 'art']):
            return random.choice(['art', 'creativity', 'inspiration'])
        elif any(word in title_lower for word in ['family', 'parent', 'mom', 'dad']):
            return random.choice(['family', 'love', 'home', 'warmth'])
        elif any(word in title_lower for word in ['work', 'career', 'business']):
            return random.choice(['success', 'business', 'professional'])

        # Random default theme
        return random.choice(default_themes)

    def download_unsplash_image(self, journal, search_term):
        """Download image from Unsplash and save to journal"""
        try:
            # Unsplash source URL - this redirects to a random image
            url = f"https://source.unsplash.com/400x600/?{search_term}"

            # Make request with headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)

            if response.status_code == 200 and len(response.content) > 5000:  # Ensure we got a real image
                # Create filename
                safe_title = slugify(journal.title)[:40]
                filename = f"cover_{journal.id}_{safe_title}_{search_term}.jpg"

                # Delete old cover if exists
                if journal.cover_image:
                    try:
                        journal.cover_image.delete(save=False)
                    except:
                        pass

                # Save new cover
                journal.cover_image.save(
                    filename,
                    ContentFile(response.content),
                    save=True
                )

                return True
            else:
                self.stdout.write(f'Bad response for {journal.title}: {response.status_code}, size: {len(response.content)}')
                return False

        except requests.exceptions.RequestException as e:
            self.stdout.write(f'Request error for {journal.title}: {str(e)}')
            return False
        except Exception as e:
            self.stdout.write(f'General error for {journal.title}: {str(e)}')
            return False

    def get_journal_summary(self, journals):
        """Print summary of journals by category"""
        self.stdout.write('\n📊 Journal Summary by Category:')

        category_counts = {}
        for journal in journals:
            if hasattr(journal, 'marketplace_tags') and journal.marketplace_tags.exists():
                for tag in journal.marketplace_tags.all():
                    category_counts[tag.name] = category_counts.get(tag.name, 0) + 1
            else:
                category_counts['Uncategorized'] = category_counts.get('Uncategorized', 0) + 1

        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            self.stdout.write(f'  {category}: {count} journals')
