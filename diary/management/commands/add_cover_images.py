# diary/management/commands/add_cover_images.py
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
import requests
import random
from diary.models import Journal

class Command(BaseCommand):
    help = 'Add real cover images to existing journals'

    def handle(self, *args, **options):
        # Free high-quality images from Unsplash (no API key needed for basic use)
        journal_images = [
            'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=400&h=600&fit=crop',  # Journal on wooden desk
            'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400&h=600&fit=crop',  # Open notebook
            'https://images.unsplash.com/photo-1517842645767-c639042777db?w=400&h=600&fit=crop',  # Stack of journals
            'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=400&h=600&fit=crop',  # Notebook with coffee
            'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=600&fit=crop',  # Writing desk setup
            'https://images.unsplash.com/photo-1471107340929-a87cd0f5b5f3?w=400&h=600&fit=crop',  # Vintage journal
            'https://images.unsplash.com/photo-1519904981063-b0cf448d479e?w=400&h=600&fit=crop',  # Journal with pen
            'https://images.unsplash.com/photo-1515378791036-0648a814c963?w=400&h=600&fit=crop',  # Clean notebook
            'https://images.unsplash.com/photo-1517842645767-c639042777db?w=400&h=600&fit=crop',  # Books and journal
            'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=400&h=600&fit=crop',  # Writing materials
        ]

        journals = Journal.objects.all()
        if not journals.exists():
            self.stdout.write(self.style.ERROR('No journals found. Create some journals first.'))
            return

        self.stdout.write(f'Adding cover images to {journals.count()} journals...')

        for journal in journals:
            try:
                # Skip if already has cover
                if hasattr(journal, 'cover_image') and journal.cover_image:
                    continue

                # Get random image
                image_url = random.choice(journal_images)

                # Download image
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200:
                    # Save to journal
                    journal.cover_image.save(
                        f'journal_cover_{journal.id}.jpg',
                        ContentFile(response.content),
                        save=True
                    )
                    self.stdout.write(f'Added cover to: {journal.title[:50]}...')
                else:
                    self.stdout.write(f'Failed to download image for: {journal.title[:50]}...')

            except Exception as e:
                self.stdout.write(f'Error adding cover to {journal.title[:30]}: {e}')

        self.stdout.write(self.style.SUCCESS('Finished adding cover images!'))
