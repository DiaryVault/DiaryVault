from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils.text import slugify
import random
import requests
import time
import json

from diary.models import Journal

class Command(BaseCommand):
    help = 'Replace journal covers with images from multiple sources'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of journals to process'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay between requests (seconds)'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        delay = options['delay']

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
        skipped = 0

        for journal in journals:
            try:
                # Get theme for the journal
                theme = self.get_journal_theme(journal)

                # Try multiple image sources
                success = (
                    self.try_picsum_image(journal, theme) or
                    self.try_lorem_flickr(journal, theme) or
                    self.try_placeholder_image(journal, theme) or
                    self.create_gradient_placeholder(journal, theme)
                )

                if success:
                    processed += 1
                    self.stdout.write(f'✅ Updated: {journal.title[:50]}... (theme: {theme})')
                else:
                    errors += 1
                    self.stdout.write(f'❌ Failed: {journal.title[:50]}...')

                # Respectful delay
                time.sleep(delay)

                if (processed + errors) % 10 == 0:
                    self.stdout.write(f'--- Progress: {processed + errors}/{journals.count()} (✅{processed} ❌{errors}) ---')

            except KeyboardInterrupt:
                self.stdout.write('\n🛑 Interrupted by user')
                break
            except Exception as e:
                errors += 1
                self.stdout.write(f'⚠️  Error with "{journal.title[:30]}...": {str(e)}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 Complete! ✅{processed} successful, ❌{errors} errors, ⏭️{skipped} skipped'
            )
        )

    def get_journal_theme(self, journal):
        """Get theme for journal based on tags and title"""

        # Check tags first
        if hasattr(journal, 'marketplace_tags') and journal.marketplace_tags.exists():
            tag_names = ' '.join([tag.name.lower() for tag in journal.marketplace_tags.all()])

            if any(word in tag_names for word in ['travel', 'adventure']):
                return random.choice(['nature', 'landscape', 'mountains', 'ocean', 'forest'])
            elif any(word in tag_names for word in ['health', 'mental', 'wellness']):
                return random.choice(['nature', 'peaceful', 'zen', 'meditation', 'calm'])
            elif any(word in tag_names for word in ['creative', 'art']):
                return random.choice(['abstract', 'colorful', 'artistic', 'creative'])
            elif any(word in tag_names for word in ['parent', 'family']):
                return random.choice(['warm', 'cozy', 'home', 'family'])
            elif any(word in tag_names for word in ['career', 'business']):
                return random.choice(['professional', 'modern', 'clean', 'minimal'])

        # Check title
        title_lower = journal.title.lower()
        if any(word in title_lower for word in ['travel', 'journey']):
            return random.choice(['nature', 'landscape', 'adventure'])
        elif any(word in title_lower for word in ['health', 'mind']):
            return random.choice(['peaceful', 'nature', 'calm'])
        elif any(word in title_lower for word in ['creative', 'art']):
            return random.choice(['abstract', 'colorful'])

        # Default themes
        return random.choice(['minimal', 'abstract', 'nature', 'peaceful', 'modern'])

    def try_picsum_image(self, journal, theme):
        """Try to get image from Lorem Picsum (usually reliable)"""
        try:
            # Lorem Picsum with random seed
            seed = random.randint(1, 1000)
            url = f"https://picsum.photos/400/600?random={seed}"

            response = requests.get(url, timeout=10, stream=True)

            if response.status_code == 200 and len(response.content) > 5000:
                filename = f"cover_{journal.id}_{slugify(journal.title)[:30]}_picsum.jpg"

                # Delete old cover
                if journal.cover_image:
                    journal.cover_image.delete(save=False)

                # Save new cover
                journal.cover_image.save(filename, ContentFile(response.content), save=True)
                return True

        except Exception as e:
            self.stdout.write(f'Picsum failed: {str(e)}')

        return False

    def try_lorem_flickr(self, journal, theme):
        """Try LoremFlickr (themed images)"""
        try:
            # LoremFlickr with theme
            theme_map = {
                'nature': 'nature,landscape',
                'landscape': 'landscape,mountains',
                'mountains': 'mountains,nature',
                'ocean': 'ocean,water',
                'forest': 'forest,trees',
                'peaceful': 'peaceful,calm',
                'zen': 'zen,meditation',
                'meditation': 'meditation,peaceful',
                'calm': 'calm,serene',
                'abstract': 'abstract,art',
                'colorful': 'colorful,vibrant',
                'artistic': 'art,creative',
                'creative': 'creative,art',
                'warm': 'warm,cozy',
                'cozy': 'cozy,home',
                'home': 'home,interior',
                'family': 'family,together',
                'professional': 'business,office',
                'modern': 'modern,clean',
                'clean': 'minimal,simple',
                'minimal': 'minimal,simple'
            }

            search_terms = theme_map.get(theme, 'abstract,minimal')
            url = f"https://loremflickr.com/400/600/{search_terms}"

            response = requests.get(url, timeout=15)

            if response.status_code == 200 and len(response.content) > 5000:
                filename = f"cover_{journal.id}_{slugify(journal.title)[:30]}_flickr.jpg"

                if journal.cover_image:
                    journal.cover_image.delete(save=False)

                journal.cover_image.save(filename, ContentFile(response.content), save=True)
                return True

        except Exception as e:
            self.stdout.write(f'LoremFlickr failed: {str(e)}')

        return False

    def try_placeholder_image(self, journal, theme):
        """Try placeholder.com with colors"""
        try:
            # Color schemes based on theme
            color_schemes = {
                'nature': ('4CAF50', 'FFFFFF'),      # Green
                'peaceful': ('2196F3', 'FFFFFF'),    # Blue
                'abstract': ('9C27B0', 'FFFFFF'),    # Purple
                'warm': ('FF9800', 'FFFFFF'),        # Orange
                'professional': ('607D8B', 'FFFFFF'), # Blue Grey
                'creative': ('E91E63', 'FFFFFF'),    # Pink
                'minimal': ('9E9E9E', 'FFFFFF'),     # Grey
            }

            bg_color, text_color = color_schemes.get(theme, ('2196F3', 'FFFFFF'))

            # Create title for placeholder
            title_text = journal.title.replace(' ', '+')[:40]
            url = f"https://via.placeholder.com/400x600/{bg_color}/{text_color}?text={title_text}"

            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                filename = f"cover_{journal.id}_{slugify(journal.title)[:30]}_placeholder.png"

                if journal.cover_image:
                    journal.cover_image.delete(save=False)

                journal.cover_image.save(filename, ContentFile(response.content), save=True)
                return True

        except Exception as e:
            self.stdout.write(f'Placeholder failed: {str(e)}')

        return False

    def create_gradient_placeholder(self, journal, theme):
        """Last resort: create a simple colored rectangle (requires PIL)"""
        try:
            from PIL import Image, ImageDraw, ImageFont

            # Color schemes
            colors = {
                'nature': [(76, 175, 80), (139, 195, 74)],     # Green gradient
                'peaceful': [(33, 150, 243), (100, 181, 246)], # Blue gradient
                'abstract': [(156, 39, 176), (186, 104, 200)], # Purple gradient
                'warm': [(255, 152, 0), (255, 193, 7)],        # Orange gradient
                'professional': [(96, 125, 139), (120, 144, 156)], # Blue grey
                'creative': [(233, 30, 99), (240, 98, 146)],   # Pink gradient
                'minimal': [(158, 158, 158), (189, 189, 189)], # Grey gradient
            }

            theme_colors = colors.get(theme, colors['minimal'])

            # Create gradient image
            width, height = 400, 600
            image = Image.new('RGB', (width, height))
            draw = ImageDraw.Draw(image)

            # Create vertical gradient
            for y in range(height):
                ratio = y / height
                r = int(theme_colors[0][0] * (1 - ratio) + theme_colors[1][0] * ratio)
                g = int(theme_colors[0][1] * (1 - ratio) + theme_colors[1][1] * ratio)
                b = int(theme_colors[0][2] * (1 - ratio) + theme_colors[1][2] * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            # Add title text
            try:
                font = ImageFont.load_default()
                title = journal.title[:50]

                # Calculate text position
                bbox = draw.textbbox((0, 0), title, font=font)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                y = height // 2

                # Draw text with shadow
                draw.text((x+2, y+2), title, fill=(0, 0, 0, 100), font=font)
                draw.text((x, y), title, fill=(255, 255, 255), font=font)
            except:
                pass  # Skip text if font fails

            # Save image
            import io
            img_io = io.BytesIO()
            image.save(img_io, format='JPEG', quality=85)
            img_content = ContentFile(img_io.getvalue())

            filename = f"cover_{journal.id}_{slugify(journal.title)[:30]}_gradient.jpg"

            if journal.cover_image:
                journal.cover_image.delete(save=False)

            journal.cover_image.save(filename, img_content, save=True)
            return True

        except ImportError:
            self.stdout.write('PIL not available for gradient creation')
            return False
        except Exception as e:
            self.stdout.write(f'Gradient creation failed: {str(e)}')
            return False
