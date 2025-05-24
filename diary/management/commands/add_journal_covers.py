from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils.text import slugify
import random
import io
import requests
from PIL import Image, ImageDraw, ImageFont

from diary.models import Journal

class Command(BaseCommand):
    help = 'Add cover images to existing journals'

    def add_arguments(self, parser):
        parser.add_argument(
            '--method',
            type=str,
            choices=['generate', 'unsplash', 'placeholder'],
            default='generate',
            help='Method to create covers: generate (custom), unsplash (real photos), or placeholder (simple)'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing cover images'
        )

    def handle(self, *args, **options):
        method = options['method']
        overwrite = options['overwrite']

        # Get journals that need cover images
        if overwrite:
            journals = Journal.objects.filter(is_published=True)
            self.stdout.write(f'Processing all {journals.count()} published journals...')
        else:
            journals = Journal.objects.filter(is_published=True, cover_image__isnull=True)
            self.stdout.write(f'Processing {journals.count()} journals without cover images...')

        if not journals.exists():
            self.stdout.write(self.style.SUCCESS('No journals need cover images!'))
            return

        processed = 0
        errors = 0

        for journal in journals:
            try:
                if method == 'generate':
                    self.generate_custom_cover(journal)
                elif method == 'unsplash':
                    self.add_unsplash_cover(journal)
                elif method == 'placeholder':
                    self.create_placeholder_cover(journal)

                processed += 1

                if processed % 10 == 0:
                    self.stdout.write(f'Processed {processed}/{journals.count()} journals...')

            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.WARNING(f'Error processing journal "{journal.title}": {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {processed} journals! ({errors} errors)'
            )
        )

    def generate_custom_cover(self, journal):
        """Generate a custom gradient cover with journal title"""
        # Create image
        width, height = 400, 600
        image = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(image)

        # Choose colors based on journal category or randomly
        color_schemes = [
            [(76, 175, 80), (139, 195, 74)],    # Green
            [(33, 150, 243), (100, 181, 246)], # Blue
            [(156, 39, 176), (186, 104, 200)], # Purple
            [(255, 152, 0), (255, 193, 7)],    # Orange
            [(244, 67, 54), (229, 115, 115)],  # Red
            [(0, 150, 136), (77, 182, 172)],   # Teal
            [(96, 125, 139), (120, 144, 156)], # Blue Grey
            [(121, 85, 72), (141, 110, 99)],   # Brown
        ]

        # Get category-based colors if possible
        colors = random.choice(color_schemes)
        if hasattr(journal, 'marketplace_tags') and journal.marketplace_tags.exists():
            tag = journal.marketplace_tags.first()
            if 'travel' in tag.name.lower():
                colors = [(33, 150, 243), (100, 181, 246)]  # Blue
            elif 'health' in tag.name.lower():
                colors = [(76, 175, 80), (139, 195, 74)]    # Green
            elif 'creative' in tag.name.lower() or 'art' in tag.name.lower():
                colors = [(156, 39, 176), (186, 104, 200)]  # Purple

        # Create gradient background
        for y in range(height):
            # Calculate color interpolation
            ratio = y / height
            r = int(colors[0][0] * (1 - ratio) + colors[1][0] * ratio)
            g = int(colors[0][1] * (1 - ratio) + colors[1][1] * ratio)
            b = int(colors[0][2] * (1 - ratio) + colors[1][2] * ratio)

            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Add overlay pattern
        self.add_pattern_overlay(draw, width, height)

        # Add text
        self.add_title_to_cover(draw, journal.title, width, height)
        self.add_author_to_cover(draw, journal.author.get_full_name() or journal.author.username, width, height)

        # Save image
        self.save_cover_image(journal, image, 'generated')

    def add_pattern_overlay(self, draw, width, height):
        """Add subtle pattern overlay"""
        # Add some geometric shapes for visual interest
        overlay_color = (255, 255, 255, 30)  # Semi-transparent white

        # Add circles
        for _ in range(3):
            x = random.randint(-50, width + 50)
            y = random.randint(-50, height + 50)
            size = random.randint(100, 200)
            draw.ellipse([x-size//2, y-size//2, x+size//2, y+size//2],
                        outline=(255, 255, 255, 50), width=2)

    def add_title_to_cover(self, draw, title, width, height):
        """Add title text to cover"""
        # Try to load a font, fallback to default
        try:
            # Try common system fonts
            font_paths = [
                '/System/Library/Fonts/Helvetica.ttc',  # macOS
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Ubuntu
                '/Windows/Fonts/arial.ttf',  # Windows
            ]

            font = None
            for path in font_paths:
                try:
                    font = ImageFont.truetype(path, 32)
                    break
                except:
                    continue

            if not font:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        # Wrap title text
        words = title.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]

            if text_width < width - 60:  # 30px margin each side
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        # Draw title
        y_offset = height // 3
        line_height = 40

        for i, line in enumerate(lines[:3]):  # Max 3 lines
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = y_offset + i * line_height

            # Add text shadow
            draw.text((x+2, y+2), line, fill=(0, 0, 0, 100), font=font)
            # Add main text
            draw.text((x, y), line, fill=(255, 255, 255), font=font)

    def add_author_to_cover(self, draw, author, width, height):
        """Add author text to cover"""
        try:
            font = ImageFont.load_default()
        except:
            font = None

        author_text = f"by {author}"

        if font:
            bbox = draw.textbbox((0, 0), author_text, font=font)
            text_width = bbox[2] - bbox[0]
        else:
            text_width = len(author_text) * 6  # Rough estimate

        x = (width - text_width) // 2
        y = height - 80

        # Add author text
        if font:
            draw.text((x+1, y+1), author_text, fill=(0, 0, 0, 80), font=font)
            draw.text((x, y), author_text, fill=(255, 255, 255, 200), font=font)

    def add_unsplash_cover(self, journal):
        """Download a cover image from Unsplash"""
        # Categories for different journal types
        search_terms = ['journal', 'notebook', 'writing', 'diary', 'book', 'paper']

        # Add specific terms based on journal tags
        if hasattr(journal, 'marketplace_tags') and journal.marketplace_tags.exists():
            tag_names = [tag.name.lower() for tag in journal.marketplace_tags.all()]
            if any('travel' in name for name in tag_names):
                search_terms = ['travel', 'adventure', 'journey', 'explore']
            elif any('health' in name for name in tag_names):
                search_terms = ['wellness', 'mindfulness', 'meditation', 'nature']
            elif any('creative' in name for name in tag_names):
                search_terms = ['art', 'creativity', 'design', 'inspiration']

        search_term = random.choice(search_terms)

        # Unsplash API endpoint (you can use without API key for basic usage)
        url = f"https://source.unsplash.com/400x600/?{search_term}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                self.save_cover_image(journal, image, 'unsplash')
            else:
                # Fallback to generated cover
                self.generate_custom_cover(journal)
        except Exception as e:
            self.stdout.write(f"Unsplash failed for {journal.title}, using generated cover: {str(e)}")
            self.generate_custom_cover(journal)

    def create_placeholder_cover(self, journal):
        """Create a simple placeholder cover"""
        width, height = 400, 600

        # Choose a random solid color
        colors = [
            (52, 152, 219),   # Blue
            (46, 204, 113),   # Green
            (155, 89, 182),   # Purple
            (230, 126, 34),   # Orange
            (231, 76, 60),    # Red
            (26, 188, 156),   # Turquoise
        ]

        color = random.choice(colors)
        image = Image.new('RGB', (width, height), color)
        draw = ImageDraw.Draw(image)

        # Add simple title
        try:
            font = ImageFont.load_default()
        except:
            font = None

        title = journal.title[:30] + "..." if len(journal.title) > 30 else journal.title

        if font:
            bbox = draw.textbbox((0, 0), title, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = height // 2
            draw.text((x, y), title, fill=(255, 255, 255), font=font)

        self.save_cover_image(journal, image, 'placeholder')

    def save_cover_image(self, journal, image, method):
        """Save the image to the journal"""
        # Convert image to bytes
        img_io = io.BytesIO()
        image.save(img_io, format='JPEG', quality=85)
        img_content = ContentFile(img_io.getvalue())

        # Generate filename
        safe_title = slugify(journal.title)[:50]
        filename = f"journal_cover_{journal.id}_{safe_title}_{method}.jpg"

        # Save to journal
        journal.cover_image.save(filename, img_content, save=True)

        self.stdout.write(f'Added {method} cover to: {journal.title}')
