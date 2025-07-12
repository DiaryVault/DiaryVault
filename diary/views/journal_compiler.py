# views/journal_compiler.py
import json
import logging
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
import io
import os

from ..models import Entry, Tag, Journal, JournalEntry
from ..services.ai_service import AIService
from ..utils.analytics import get_mood_emoji, get_tag_color
from ..views.marketplace_service import MarketplaceService

logger = logging.getLogger(__name__)

@login_required
def smart_journal_compiler(request):
    """Main view for the Smart Journal Compiler with image upload support"""

    # Handle POST request for publishing journals with images
    if request.method == 'POST':
        try:
            # Get form data
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            price = request.POST.get('price', '0')
            method = request.POST.get('method', 'ai')
            entry_ids = request.POST.get('entry_ids', '[]')

            # Handle image upload
            cover_image = request.FILES.get('cover_image')
            image_filter = request.POST.get('image_filter', 'none')

            # Validate required fields
            if not title or not description:
                return JsonResponse({
                    'success': False,
                    'error': 'Title and description are required'
                }, status=400)

            # Parse entry IDs
            try:
                entry_ids_list = json.loads(entry_ids) if isinstance(entry_ids, str) else entry_ids
            except (json.JSONDecodeError, TypeError):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid entry selection'
                }, status=400)

            if not entry_ids_list:
                return JsonResponse({
                    'success': False,
                    'error': 'Please select at least one entry'
                }, status=400)

            # Validate entries belong to user
            user_entries = Entry.objects.filter(
                id__in=entry_ids_list,
                user=request.user
            )

            if user_entries.count() != len(entry_ids_list):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid entry selection'
                }, status=400)

            # Create journal structure using your existing AI service
            try:
                structure = JournalCompilerAI.generate_journal_structure(
                    user=request.user,
                    entries=user_entries,
                    compilation_method=method,
                    journal_type='growth',  # Default, could be made configurable
                    ai_enhancements=[]
                )
            except Exception as e:
                logger.error(f"Failed to generate journal structure: {e}")
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to generate journal structure'
                }, status=500)

            # Create the journal using your existing service
            try:
                journal = JournalCompilerAI.create_compiled_journal(
                    user=request.user,
                    title=title,
                    description=description,
                    price=float(price) if price else 0.00,
                    structure=structure,
                    entry_ids=entry_ids_list,
                    cover_image_data=None  # We'll handle image separately
                )

                # Handle cover image upload
                if cover_image:
                    # Validate image
                    if cover_image.size > 5 * 1024 * 1024:  # 5MB limit
                        return JsonResponse({
                            'success': False,
                            'error': 'Image size must be less than 5MB'
                        }, status=400)

                    if not cover_image.content_type.startswith('image/'):
                        return JsonResponse({
                            'success': False,
                            'error': 'Please upload a valid image file'
                        }, status=400)

                    # Save image to journal
                    journal.cover_image = cover_image

                    # Save image filter preference if you have this field
                    if hasattr(journal, 'image_filter'):
                        journal.image_filter = image_filter

                    journal.save()

                # Return success response
                return JsonResponse({
                    'success': True,
                    'journal_id': journal.id,
                    'redirect_url': f'/marketplace/journal/{journal.id}/',
                    'message': f'Journal "{title}" published successfully!'
                })

            except Exception as e:
                logger.error(f"Failed to create compiled journal: {e}")
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to create journal'
                }, status=500)

        except Exception as e:
            logger.error(f"Error in smart_journal_compiler POST: {e}")
            return JsonResponse({
                'success': False,
                'error': 'An unexpected error occurred'
            }, status=500)

    # Handle GET request - show the compiler interface
    # Get user's entries and analyze them
    entries = Entry.objects.filter(user=request.user).order_by('-created_at')

    if not entries.exists():
        messages.info(request, "You need at least 5 journal entries to use the Smart Journal Compiler.")
        return redirect('new_entry')

    # Generate comprehensive analysis
    analysis = JournalAnalysisService.analyze_user_entries(request.user, entries)

    # Get AI recommendations for compilation methods
    recommendations = JournalCompilerAI.get_compilation_recommendations(
        user=request.user,
        entries=entries,
        analysis=analysis
    )

    # Get available templates
    templates = JournalTemplateService.get_available_templates()

    # Get recent compiled journals
    compiled_journals = Journal.objects.filter(
        author=request.user
    ).order_by('-created_at')[:6]

    # Add entry count to each journal for template use
    for journal in compiled_journals:
        try:
            journal.entry_count = journal.entries.count()
        except Exception:
            journal.entry_count = 0

    context = {
        'analysis': analysis,
        'recommendations': recommendations,
        'templates': templates,
        'entries': entries,
        'compiled_journals': compiled_journals,
        'total_entries': entries.count(),
        'has_enough_entries': entries.count() >= 5,
    }

    return render(request, 'diary/publish_journal.html', context)

@login_required
@require_POST
def analyze_entries_ajax(request):
    """AJAX endpoint to analyze entries for compilation"""
    try:
        data = json.loads(request.body)
        compilation_method = data.get('method', 'ai')
        entry_ids = data.get('entry_ids', [])

        # Get selected entries or all entries if none selected
        if entry_ids:
            entries = Entry.objects.filter(
                id__in=entry_ids,
                user=request.user
            )
        else:
            entries = Entry.objects.filter(user=request.user)

        # Perform analysis based on compilation method
        if compilation_method == 'ai':
            analysis = JournalCompilerAI.smart_analyze_entries(request.user, entries)
        elif compilation_method == 'thematic':
            analysis = JournalCompilerAI.thematic_analyze_entries(request.user, entries)
        elif compilation_method == 'chronological':
            analysis = JournalCompilerAI.chronological_analyze_entries(request.user, entries)
        else:
            analysis = JournalAnalysisService.analyze_user_entries(request.user, entries)

        return JsonResponse({
            'success': True,
            'analysis': analysis,
            'entry_count': entries.count()
        })

    except Exception as e:
        logger.error(f"Error analyzing entries: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to analyze entries'
        }, status=500)

@login_required
@require_POST
def generate_journal_structure(request):
    """Generate journal structure with AI-powered chapters and organization"""
    try:
        data = json.loads(request.body)

        compilation_method = data.get('method', 'ai')
        journal_type = data.get('journal_type', 'growth')
        entry_ids = data.get('entry_ids', [])
        ai_enhancements = data.get('ai_enhancements', [])

        # Get entries
        entries = Entry.objects.filter(
            id__in=entry_ids,
            user=request.user
        ) if entry_ids else Entry.objects.filter(user=request.user)

        if not entries.exists():
            return JsonResponse({
                'success': False,
                'error': 'No entries selected'
            }, status=400)

        # Generate journal structure using AI
        structure = JournalCompilerAI.generate_journal_structure(
            user=request.user,
            entries=entries,
            compilation_method=compilation_method,
            journal_type=journal_type,
            ai_enhancements=ai_enhancements
        )

        # Store structure in session for later use
        request.session['journal_structure'] = structure
        request.session['selected_entry_ids'] = list(entries.values_list('id', flat=True))

        return JsonResponse({
            'success': True,
            'structure': structure,
            'estimated_length': structure.get('estimated_length', 0),
            'suggested_price': structure.get('suggested_price', 9.99)
        })

    except Exception as e:
        logger.error(f"Error generating journal structure: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to generate journal structure'
        }, status=500)

@login_required
@require_POST
def publish_compiled_journal(request):
    """Publish the compiled journal to marketplace with image upload support"""
    try:
        # Handle both JSON and FormData (for image uploads)
        if request.content_type and 'application/json' in request.content_type:
            # Handle JSON data (no image)
            data = json.loads(request.body)
            title = data.get('title')
            description = data.get('description')
            price = float(data.get('price', 0))
            cover_image = None
            image_filter = 'none'
        else:
            # Handle FormData (with image)
            title = request.POST.get('title')
            description = request.POST.get('description')
            price = float(request.POST.get('price', 0))
            cover_image = request.FILES.get('cover_image')
            image_filter = request.POST.get('image_filter', 'none')

        # Validate required fields
        if not title or not description:
            return JsonResponse({
                'success': False,
                'error': 'Title and description are required'
            }, status=400)

        # Get structure from session
        structure = request.session.get('journal_structure')
        entry_ids = request.session.get('selected_entry_ids')

        if not structure or not entry_ids:
            return JsonResponse({
                'success': False,
                'error': 'Journal structure not found. Please regenerate.'
            }, status=400)

        # Validate image if provided
        if cover_image:
            # Check file size (5MB limit)
            if cover_image.size > 5 * 1024 * 1024:
                return JsonResponse({
                    'success': False,
                    'error': 'Image size must be less than 5MB'
                }, status=400)

            # Check file type
            if not cover_image.content_type.startswith('image/'):
                return JsonResponse({
                    'success': False,
                    'error': 'Please upload a valid image file (JPG, PNG, or WebP)'
                }, status=400)

        # Create the journal
        journal = JournalCompilerAI.create_compiled_journal(
            user=request.user,
            title=title,
            description=description,
            price=price,
            structure=structure,
            entry_ids=entry_ids,
            cover_image_data=None  # We'll handle image separately
        )

        # Handle cover image upload
        if cover_image:
            journal.cover_image = cover_image

            # Save image filter preference if you have this field
            if hasattr(journal, 'image_filter'):
                journal.image_filter = image_filter

            journal.save()

        # Clear session data
        if 'journal_structure' in request.session:
            del request.session['journal_structure']
        if 'selected_entry_ids' in request.session:
            del request.session['selected_entry_ids']

        return JsonResponse({
            'success': True,
            'journal_id': journal.id,
            'redirect_url': f'/marketplace/journal/{journal.id}/',
            'message': f'Journal "{title}" published successfully!'
        })

    except Exception as e:
        logger.error(f"Error publishing compiled journal: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def preview_journal_structure(request):
    """Preview the generated journal structure"""
    structure = request.session.get('journal_structure')
    entry_ids = request.session.get('selected_entry_ids', [])

    if not structure:
        messages.error(request, "No journal structure found. Please generate one first.")
        return redirect('smart_journal_compiler')

    # Get entries for preview
    entries = Entry.objects.filter(
        id__in=entry_ids,
        user=request.user
    ).order_by('-created_at')

    context = {
        'structure': structure,
        'entries': entries,
        'preview_mode': True
    }

    return render(request, 'diary/journal_structure_preview.html', context)


@login_required
def edit_journal(request, journal_id):
    """Edit a published journal with enhanced image upload support"""
    journal = get_object_or_404(
        Journal,
        id=journal_id,
        author=request.user,
        is_published=True  # Only allow editing published journals
    )

    # Get journal entries for display
    journal_entries = journal.entries.filter(is_included=True).order_by('-entry_date')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '0')

        # Image handling
        cover_image = request.FILES.get('cover_image')
        image_filter = request.POST.get('image_filter', 'none')
        remove_cover_image = request.POST.get('remove_cover_image', 'false') == 'true'

        # Validate inputs
        if not title:
            messages.error(request, "Journal title is required.")
            return render(request, 'diary/edit_journal.html', {
                'journal': journal,
                'journal_entries': journal_entries,
                'filter_choices': get_filter_choices()
            })

        if not description:
            messages.error(request, "Journal description is required.")
            return render(request, 'diary/edit_journal.html', {
                'journal': journal,
                'journal_entries': journal_entries,
                'filter_choices': get_filter_choices()
            })

        try:
            # Handle cover image removal
            if remove_cover_image and journal.cover_image:
                # Delete the old image file
                if journal.cover_image and default_storage.exists(journal.cover_image.name):
                    default_storage.delete(journal.cover_image.name)
                journal.cover_image = None
                journal.image_filter = 'none'

            # Handle new cover image upload
            elif cover_image:
                # Validate image
                if not cover_image.content_type.startswith('image/'):
                    messages.error(request, 'Please upload a valid image file (PNG, JPG, WebP).')
                    return render(request, 'diary/edit_journal.html', {
                        'journal': journal,
                        'journal_entries': journal_entries,
                        'filter_choices': get_filter_choices()
                    })

                if cover_image.size > 5 * 1024 * 1024:  # 5MB limit
                    messages.error(request, 'Image size must be less than 5MB.')
                    return render(request, 'diary/edit_journal.html', {
                        'journal': journal,
                        'journal_entries': journal_entries,
                        'filter_choices': get_filter_choices()
                    })

                # Process and save the image
                try:
                    # Delete old image if it exists
                    if journal.cover_image and default_storage.exists(journal.cover_image.name):
                        default_storage.delete(journal.cover_image.name)

                    # Process the new image
                    processed_image = process_uploaded_image(cover_image)

                    # Save the processed image
                    journal.cover_image = processed_image
                    journal.image_filter = image_filter

                except Exception as e:
                    logger.error(f"Error processing image: {e}")
                    messages.error(request, 'Error processing image. Please try a different image.')
                    return render(request, 'diary/edit_journal.html', {
                        'journal': journal,
                        'journal_entries': journal_entries,
                        'filter_choices': get_filter_choices()
                    })

            # Update image filter if no new image but filter changed
            elif not remove_cover_image and journal.cover_image:
                journal.image_filter = image_filter

            # Update journal fields
            journal.title = title
            journal.description = description

            # Update price if the field exists
            try:
                journal.price = float(price) if price else 0.00
            except (ValueError, AttributeError):
                pass  # Skip if price field doesn't exist or invalid value

            # Update modification timestamp if field exists
            try:
                journal.date_modified = timezone.now()
            except AttributeError:
                pass  # Skip if field doesn't exist

            journal.save()

            messages.success(request, f'Journal "{title}" updated successfully!')

            # Redirect to marketplace journal detail page
            return redirect('marketplace_journal_detail', journal_id=journal.id)

        except Exception as e:
            logger.error(f"Error updating journal: {e}")
            messages.error(request, f'Error updating journal: {str(e)}')
            return render(request, 'diary/edit_journal.html', {
                'journal': journal,
                'journal_entries': journal_entries,
                'filter_choices': get_filter_choices()
            })

    # GET request - show edit form
    context = {
        'journal': journal,
        'journal_entries': journal_entries,
        'filter_choices': get_filter_choices()
    }

    return render(request, 'diary/edit_journal.html', context)


def get_filter_choices():
    """Get available image filter choices"""
    return [
        ('none', 'Original'),
        ('vintage', 'Vintage'),
        ('warm', 'Warm'),
        ('cool', 'Cool'),
        ('mono', 'Monochrome'),
        ('bright', 'Bright'),
    ]


def process_uploaded_image(uploaded_file):
    """Process uploaded image - resize and optimize"""
    try:
        # Open the image
        image = Image.open(uploaded_file)

        # Convert to RGB if necessary (for RGBA images)
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if 'A' in image.mode else None)
            image = background

        # Calculate new dimensions (max width/height of 1200px)
        max_size = 1200
        width, height = image.size

        if width > max_size or height > max_size:
            # Calculate aspect ratio
            if width > height:
                new_width = max_size
                new_height = int((height * max_size) / width)
            else:
                new_height = max_size
                new_width = int((width * max_size) / height)

            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save to bytes
        output = io.BytesIO()

        # Determine format
        original_format = uploaded_file.content_type
        if 'jpeg' in original_format or 'jpg' in original_format:
            image.save(output, format='JPEG', quality=85, optimize=True)
            extension = '.jpg'
        elif 'png' in original_format:
            image.save(output, format='PNG', optimize=True)
            extension = '.png'
        elif 'webp' in original_format:
            image.save(output, format='WEBP', quality=85, optimize=True)
            extension = '.webp'
        else:
            # Default to JPEG
            image.save(output, format='JPEG', quality=85, optimize=True)
            extension = '.jpg'

        output.seek(0)

        # Create a new ContentFile
        file_name = f"journal_cover_{timezone.now().strftime('%Y%m%d_%H%M%S')}{extension}"
        return ContentFile(output.read(), name=file_name)

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        raise e


# Alternative version if you want to handle image upload via AJAX
@login_required
@require_POST
def upload_journal_cover_ajax(request, journal_id):
    """AJAX endpoint for uploading journal cover image"""
    journal = get_object_or_404(
        Journal,
        id=journal_id,
        author=request.user,
        is_published=True
    )

    try:
        cover_image = request.FILES.get('cover_image')
        image_filter = request.POST.get('image_filter', 'none')

        if not cover_image:
            return JsonResponse({
                'success': False,
                'error': 'No image provided'
            }, status=400)

        # Validate image
        if not cover_image.content_type.startswith('image/'):
            return JsonResponse({
                'success': False,
                'error': 'Please upload a valid image file (PNG, JPG, WebP)'
            }, status=400)

        if cover_image.size > 5 * 1024 * 1024:  # 5MB limit
            return JsonResponse({
                'success': False,
                'error': 'Image size must be less than 5MB'
            }, status=400)

        # Delete old image if it exists
        if journal.cover_image and default_storage.exists(journal.cover_image.name):
            default_storage.delete(journal.cover_image.name)

        # Process and save the new image
        processed_image = process_uploaded_image(cover_image)
        journal.cover_image = processed_image
        journal.image_filter = image_filter
        journal.save(update_fields=['cover_image', 'image_filter'])

        return JsonResponse({
            'success': True,
            'image_url': journal.cover_image.url,
            'message': 'Cover image updated successfully!'
        })

    except Exception as e:
        logger.error(f"Error uploading cover image: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Error processing image. Please try again.'
        }, status=500)


@login_required
@require_POST
def remove_journal_cover_ajax(request, journal_id):
    """AJAX endpoint for removing journal cover image"""
    journal = get_object_or_404(
        Journal,
        id=journal_id,
        author=request.user,
        is_published=True
    )

    try:
        if journal.cover_image:
            # Delete the image file
            if default_storage.exists(journal.cover_image.name):
                default_storage.delete(journal.cover_image.name)

            journal.cover_image = None
            journal.image_filter = 'none'
            journal.save(update_fields=['cover_image', 'image_filter'])

        return JsonResponse({
            'success': True,
            'message': 'Cover image removed successfully!'
        })

    except Exception as e:
        logger.error(f"Error removing cover image: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Error removing image. Please try again.'
        }, status=500)


@login_required
@require_POST
def update_image_filter_ajax(request, journal_id):
    """AJAX endpoint for updating image filter"""
    journal = get_object_or_404(
        Journal,
        id=journal_id,
        author=request.user,
        is_published=True
    )

    try:
        data = json.loads(request.body)
        image_filter = data.get('filter', 'none')

        # Validate filter
        valid_filters = [choice[0] for choice in get_filter_choices()]
        if image_filter not in valid_filters:
            return JsonResponse({
                'success': False,
                'error': 'Invalid filter selection'
            }, status=400)

        journal.image_filter = image_filter
        journal.save(update_fields=['image_filter'])

        return JsonResponse({
            'success': True,
            'message': 'Image filter updated successfully!'
        })

    except Exception as e:
        logger.error(f"Error updating image filter: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Error updating filter. Please try again.'
        }, status=500)

# Service Classes

class JournalAnalysisService:
    """Service for analyzing user entries"""

    @staticmethod
    def analyze_user_entries(user, entries):
        """Comprehensive analysis of user's journal entries"""

        analysis = {
            'total_entries': entries.count(),
            'date_range': JournalAnalysisService._get_date_range(entries),
            'themes': JournalAnalysisService._extract_themes(entries),
            'mood_distribution': JournalAnalysisService._analyze_moods(entries),
            'writing_patterns': JournalAnalysisService._analyze_writing_patterns(entries),
            'story_arcs': JournalAnalysisService._identify_story_arcs(entries),
            'quality_score': JournalAnalysisService._calculate_quality_score(entries),
            'marketability': JournalAnalysisService._assess_marketability(entries),
        }

        return analysis

    @staticmethod
    def _get_date_range(entries):
        """Get the date range of entries"""
        if not entries.exists():
            return None

        first_entry = entries.order_by('created_at').first()
        last_entry = entries.order_by('created_at').last()

        return {
            'start_date': first_entry.created_at.date(),
            'end_date': last_entry.created_at.date(),
            'duration_days': (last_entry.created_at - first_entry.created_at).days + 1
        }

    @staticmethod
    def _extract_themes(entries):
        """Extract major themes from entries"""
        theme_counter = Counter()

        for entry in entries:
            # Use existing tags
            for tag in entry.tags.all():
                theme_counter[tag.name] += 1

            # Extract themes from mood
            if entry.mood:
                theme_counter[entry.mood.lower()] += 1

        # Get top themes
        top_themes = theme_counter.most_common(12)

        return [
            {
                'name': theme,
                'count': count,
                'percentage': round((count / len(entries)) * 100, 1),
                'color': get_tag_color(theme)
            }
            for theme, count in top_themes
        ]

    @staticmethod
    def _analyze_moods(entries):
        """Analyze mood distribution and trends"""
        mood_counter = Counter()
        mood_timeline = []

        for entry in entries.order_by('created_at'):
            if entry.mood:
                mood_counter[entry.mood] += 1
                mood_timeline.append({
                    'date': entry.created_at.date(),
                    'mood': entry.mood,
                    'emoji': get_mood_emoji(entry.mood)
                })

        return {
            'distribution': [
                {
                    'mood': mood,
                    'count': count,
                    'percentage': round((count / len(entries)) * 100, 1),
                    'emoji': get_mood_emoji(mood)
                }
                for mood, count in mood_counter.most_common()
            ],
            'timeline': mood_timeline[-30:],  # Last 30 entries
            'dominant_mood': mood_counter.most_common(1)[0][0] if mood_counter else None
        }

    @staticmethod
    def _analyze_writing_patterns(entries):
        """Analyze writing patterns and style"""
        total_words = 0
        entry_lengths = []
        writing_times = defaultdict(int)

        for entry in entries:
            words = len(entry.content.split())
            total_words += words
            entry_lengths.append(words)

            # Analyze writing time patterns
            hour = entry.created_at.hour
            if 6 <= hour < 12:
                writing_times['morning'] += 1
            elif 12 <= hour < 18:
                writing_times['afternoon'] += 1
            elif 18 <= hour < 22:
                writing_times['evening'] += 1
            else:
                writing_times['night'] += 1

        avg_words = total_words / len(entries) if entries else 0

        return {
            'average_length': round(avg_words),
            'total_words': total_words,
            'length_consistency': 'high' if max(entry_lengths) - min(entry_lengths) < avg_words else 'medium',
            'preferred_writing_time': max(writing_times, key=writing_times.get) if writing_times else 'evening',
            'writing_frequency': JournalAnalysisService._calculate_frequency(entries)
        }

    @staticmethod
    def _calculate_frequency(entries):
        """Calculate writing frequency"""
        if entries.count() < 2:
            return 'insufficient_data'

        date_range = JournalAnalysisService._get_date_range(entries)
        if not date_range:
            return 'insufficient_data'

        days_span = date_range['duration_days']
        entries_per_day = entries.count() / days_span

        if entries_per_day >= 0.8:
            return 'daily'
        elif entries_per_day >= 0.4:
            return 'regular'
        elif entries_per_day >= 0.1:
            return 'weekly'
        else:
            return 'occasional'

    @staticmethod
    def _identify_story_arcs(entries):
        """Identify potential story arcs in the entries"""
        # Group entries by time periods and themes
        arcs = []

        # REMOVED: Chapter-based arcs since LifeChapter no longer exists
        # Temporal arcs (by chapters or time periods) - REMOVED
        
        # Thematic arcs (by dominant themes)
        theme_arcs = defaultdict(list)
        for entry in entries:
            for tag in entry.tags.all():
                theme_arcs[tag.name].append(entry)

        for theme, theme_entries in theme_arcs.items():
            if len(theme_entries) >= 5:  # Minimum for a thematic arc
                arcs.append({
                    'type': 'theme',
                    'title': f"{theme.title()} Journey",
                    'entry_count': len(theme_entries),
                    'theme': theme
                })

        return arcs[:6]  # Return top 6 arcs

    @staticmethod
    def _calculate_quality_score(entries):
        """Calculate overall quality score for the entries"""
        if not entries.exists():
            return 0

        score = 0
        factors = []

        # Length factor (30%)
        avg_length = sum(len(entry.content.split()) for entry in entries) / entries.count()
        if avg_length >= 200:
            length_score = 30
        elif avg_length >= 100:
            length_score = 25
        elif avg_length >= 50:
            length_score = 20
        else:
            length_score = 10

        score += length_score
        factors.append(f"Average length: {int(avg_length)} words")

        # Consistency factor (25%)
        date_range = JournalAnalysisService._get_date_range(entries)
        if date_range and date_range['duration_days'] > 0:
            consistency = entries.count() / date_range['duration_days']
            if consistency >= 0.5:
                consistency_score = 25
            elif consistency >= 0.2:
                consistency_score = 20
            elif consistency >= 0.1:
                consistency_score = 15
            else:
                consistency_score = 10
        else:
            consistency_score = 10

        score += consistency_score
        factors.append(f"Writing consistency: {consistency_score}/25")

        # Diversity factor (25%)
        unique_tags = set()
        unique_moods = set()
        for entry in entries:
            unique_tags.update(tag.name for tag in entry.tags.all())
            if entry.mood:
                unique_moods.add(entry.mood)

        diversity_score = min(25, (len(unique_tags) + len(unique_moods)) * 2)
        score += diversity_score
        factors.append(f"Content diversity: {len(unique_tags)} themes, {len(unique_moods)} moods")

        # Engagement factor (20%)
        entries_with_tags = entries.filter(tags__isnull=False).distinct().count()
        entries_with_mood = entries.exclude(mood__isnull=True).count()

        engagement_ratio = (entries_with_tags + entries_with_mood) / (entries.count() * 2)
        engagement_score = int(engagement_ratio * 20)
        score += engagement_score
        factors.append(f"Metadata completeness: {int(engagement_ratio * 100)}%")

        return {
            'score': min(100, score),
            'factors': factors,
            'rating': 'excellent' if score >= 85 else 'good' if score >= 70 else 'fair' if score >= 50 else 'needs_improvement'
        }

    @staticmethod
    def _assess_marketability(entries):
        """Assess marketability potential of the journal"""
        quality = JournalAnalysisService._calculate_quality_score(entries)
        themes = JournalAnalysisService._extract_themes(entries)

        # Market appeal factors
        appeal_score = 0
        factors = []

        # Popular themes
        popular_themes = ['travel', 'growth', 'relationships', 'career', 'health', 'creativity']
        theme_names = [theme['name'].lower() for theme in themes]
        popular_count = sum(1 for theme in popular_themes if theme in theme_names)

        theme_appeal = min(30, popular_count * 6)
        appeal_score += theme_appeal
        factors.append(f"Popular themes: {popular_count}/6")

        # Length and substance
        if quality['score'] >= 70:
            quality_appeal = 25
        elif quality['score'] >= 50:
            quality_appeal = 15
        else:
            quality_appeal = 5

        appeal_score += quality_appeal
        factors.append(f"Content quality: {quality['rating']}")

        # Story potential
        arcs = JournalAnalysisService._identify_story_arcs(entries)
        story_appeal = min(25, len(arcs) * 5)
        appeal_score += story_appeal
        factors.append(f"Story arcs: {len(arcs)}")

        # Uniqueness and authenticity
        unique_appeal = 20  # Base score for personal authentic content
        appeal_score += unique_appeal
        factors.append("Authentic personal narrative")

        return {
            'score': appeal_score,
            'factors': factors,
            'potential': 'high' if appeal_score >= 75 else 'medium' if appeal_score >= 50 else 'developing',
            'suggested_price_range': {
                'min': 4.99 if appeal_score >= 50 else 0.99,
                'max': 19.99 if appeal_score >= 75 else 12.99 if appeal_score >= 50 else 6.99
            }
        }

class JournalCompilerAI:
    """AI-powered journal compilation service"""

    @staticmethod
    def get_compilation_recommendations(user, entries, analysis):
        """Get AI recommendations for compilation methods"""

        recommendations = []

        # AI Smart Compilation
        ai_score = JournalCompilerAI._calculate_ai_suitability(analysis)
        recommendations.append({
            'method': 'ai',
            'title': 'AI Smart Compilation',
            'description': 'Let AI analyze your entries and create the optimal journal structure',
            'score': ai_score,
            'pros': [
                'Automatically identifies the best themes and story arcs',
                'Creates compelling chapter structures',
                'Optimizes for reader engagement'
            ],
            'best_for': 'Diverse entries with multiple themes and rich content'
        })

        # Thematic Compilation
        thematic_score = JournalCompilerAI._calculate_thematic_suitability(analysis)
        recommendations.append({
            'method': 'thematic',
            'title': 'Thematic Collection',
            'description': 'Organize entries around specific themes and topics',
            'score': thematic_score,
            'pros': [
                'Clear, focused narrative around specific topics',
                'Easy for readers to find relevant content',
                'Great for specialized interests'
            ],
            'best_for': 'Entries with strong, consistent themes'
        })

        # Chronological Compilation
        chronological_score = JournalCompilerAI._calculate_chronological_suitability(analysis)
        recommendations.append({
            'method': 'chronological',
            'title': 'Timeline Journey',
            'description': 'Create a chronological narrative of your experiences',
            'score': chronological_score,
            'pros': [
                'Natural story progression over time',
                'Shows personal growth and change',
                'Easy to follow narrative flow'
            ],
            'best_for': 'Consistent journaling over a specific time period'
        })

        # Sort by score
        recommendations.sort(key=lambda x: x['score'], reverse=True)

        return recommendations

    @staticmethod
    def _calculate_ai_suitability(analysis):
        """Calculate suitability score for AI compilation"""
        score = 50  # Base score

        # Quality bonus
        quality_score = analysis.get('quality_score', {}).get('score', 0)
        score += min(25, quality_score * 0.25)

        # Theme diversity bonus
        themes = analysis.get('themes', [])
        if len(themes) >= 5:
            score += 15
        elif len(themes) >= 3:
            score += 10

        # Story arc bonus
        arcs = analysis.get('story_arcs', [])
        score += min(10, len(arcs) * 2)

        return min(100, score)

    @staticmethod
    def _calculate_thematic_suitability(analysis):
        """Calculate suitability score for thematic compilation"""
        score = 40  # Base score

        themes = analysis.get('themes', [])
        if not themes:
            return score

        # Strong themes bonus
        top_theme_percentage = themes[0].get('percentage', 0) if themes else 0
        if top_theme_percentage >= 30:
            score += 30
        elif top_theme_percentage >= 20:
            score += 20
        elif top_theme_percentage >= 15:
            score += 15

        # Multiple strong themes
        strong_themes = sum(1 for theme in themes if theme.get('percentage', 0) >= 15)
        score += min(20, strong_themes * 5)

        # Quality factor
        quality_score = analysis.get('quality_score', {}).get('score', 0)
        score += min(10, quality_score * 0.1)

        return min(100, score)

    @staticmethod
    def _calculate_chronological_suitability(analysis):
        """Calculate suitability score for chronological compilation"""
        score = 45  # Base score

        # Date range factor
        date_range = analysis.get('date_range')
        if date_range:
            duration = date_range.get('duration_days', 0)
            if 30 <= duration <= 365:  # Sweet spot
                score += 25
            elif duration < 30:
                score += 10
            else:
                score += 15

        # Consistency factor
        writing_patterns = analysis.get('writing_patterns', {})
        frequency = writing_patterns.get('writing_frequency', 'occasional')

        frequency_scores = {
            'daily': 20,
            'regular': 15,
            'weekly': 10,
            'occasional': 5
        }
        score += frequency_scores.get(frequency, 5)

        # REMOVED: Story arc factor that referenced chapters
        arcs = analysis.get('story_arcs', [])
        # Only count thematic arcs now
        thematic_arcs = [arc for arc in arcs if arc.get('type') == 'theme']
        score += min(10, len(thematic_arcs) * 3)

        return min(100, score)

    @staticmethod
    def smart_analyze_entries(user, entries):
        """AI-powered smart analysis of entries"""
        base_analysis = JournalAnalysisService.analyze_user_entries(user, entries)

        # Use AI to enhance the analysis
        try:
            ai_insights = AIService.generate_journal_analysis(user, entries)
            base_analysis['ai_insights'] = ai_insights
        except Exception as e:
            logger.warning(f"Failed to generate AI insights: {e}")
            base_analysis['ai_insights'] = "AI analysis temporarily unavailable"

        return base_analysis

    @staticmethod
    def thematic_analyze_entries(user, entries):
        """Analyze entries for thematic compilation"""
        analysis = JournalAnalysisService.analyze_user_entries(user, entries)

        # Group entries by themes
        theme_groups = defaultdict(list)
        for entry in entries:
            for tag in entry.tags.all():
                theme_groups[tag.name].append(entry)

        # Create thematic structure
        thematic_structure = []
        for theme, theme_entries in theme_groups.items():
            if len(theme_entries) >= 2:  # Minimum entries per theme
                thematic_structure.append({
                    'theme': theme,
                    'entry_count': len(theme_entries),
                    'entries': [{'id': e.id, 'title': e.title, 'date': e.created_at.date()} for e in theme_entries],
                    'color': get_tag_color(theme)
                })

        # Sort by entry count
        thematic_structure.sort(key=lambda x: x['entry_count'], reverse=True)

        analysis['thematic_structure'] = thematic_structure
        return analysis

    @staticmethod
    def chronological_analyze_entries(user, entries):
        """Analyze entries for chronological compilation"""
        analysis = JournalAnalysisService.analyze_user_entries(user, entries)

        # Group entries by time periods
        time_groups = defaultdict(list)
        for entry in entries:
            # Group by quarter
            year = entry.created_at.year
            quarter = (entry.created_at.month - 1) // 3 + 1
            period_key = f"Q{quarter} {year}"
            time_groups[period_key].append(entry)

        # Create chronological structure
        chronological_structure = []
        for period, period_entries in sorted(time_groups.items()):
            chronological_structure.append({
                'period': period,
                'entry_count': len(period_entries),
                'entries': [{'id': e.id, 'title': e.title, 'date': e.created_at.date()} for e in period_entries],
                'date_range': {
                    'start': min(e.created_at for e in period_entries).date(),
                    'end': max(e.created_at for e in period_entries).date()
                }
            })

        analysis['chronological_structure'] = chronological_structure
        return analysis

    @staticmethod
    def generate_journal_structure(user, entries, compilation_method, journal_type, ai_enhancements):
        """Generate complete journal structure using AI"""

        # Get analysis based on method
        if compilation_method == 'ai':
            analysis = JournalCompilerAI.smart_analyze_entries(user, entries)
        elif compilation_method == 'thematic':
            analysis = JournalCompilerAI.thematic_analyze_entries(user, entries)
        else:
            analysis = JournalCompilerAI.chronological_analyze_entries(user, entries)

        # Generate AI-powered structure
        try:
            ai_structure = AIService.generate_journal_structure(
                user=user,
                entries=entries,
                analysis=analysis,
                journal_type=journal_type,
                compilation_method=compilation_method
            )
        except Exception as e:
            logger.warning(f"AI structure generation failed: {e}")
            ai_structure = JournalCompilerAI._generate_fallback_structure(
                entries, compilation_method, journal_type
            )

        # Apply AI enhancements
        if ai_enhancements:
            ai_structure = JournalCompilerAI._apply_ai_enhancements(
                ai_structure, ai_enhancements, user
            )

        # Calculate metrics
        ai_structure['estimated_length'] = sum(
            len(entry.content.split()) for entry in entries
        )

        ai_structure['suggested_price'] = JournalCompilerAI._calculate_suggested_price(
            analysis, ai_structure
        )

        return ai_structure

    @staticmethod
    def _generate_fallback_structure(entries, compilation_method, journal_type):
        """Generate fallback structure when AI fails"""

        chapters = []

        if compilation_method == 'thematic':
            # Group by tags
            theme_groups = defaultdict(list)
            for entry in entries:
                if entry.tags.exists():
                    for tag in entry.tags.all():
                        theme_groups[tag.name].append(entry)
                else:
                    theme_groups['reflections'].append(entry)

            for theme, theme_entries in theme_groups.items():
                if len(theme_entries) >= 2:
                    chapters.append({
                        'title': f"{theme.title()} Chronicles",
                        'description': f"Exploring the theme of {theme}",
                        'entry_count': len(theme_entries),
                        'entry_ids': [e.id for e in theme_entries]
                    })

        elif compilation_method == 'chronological':
            # Group by quarters
            time_groups = defaultdict(list)
            for entry in entries:
                quarter = f"Q{(entry.created_at.month - 1) // 3 + 1} {entry.created_at.year}"
                time_groups[quarter].append(entry)

            for period, period_entries in sorted(time_groups.items()):
                chapters.append({
                    'title': f"Chapter: {period}",
                    'description': f"Journey through {period}",
                    'entry_count': len(period_entries),
                    'entry_ids': [e.id for e in period_entries]
                })

        else:  # AI method fallback
            # Create simple chronological chapters
            entry_list = list(entries.order_by('created_at'))
            chunk_size = max(3, len(entry_list) // 4)  # Aim for 4 chapters

            for i in range(0, len(entry_list), chunk_size):
                chunk = entry_list[i:i + chunk_size]
                chapters.append({
                    'title': f"Chapter {len(chapters) + 1}: The Journey Continues",
                    'description': "A collection of personal reflections and experiences",
                    'entry_count': len(chunk),
                    'entry_ids': [e.id for e in chunk]
                })

        return {
            'title': f"My {journal_type.title()} Journal",
            'description': "A personal journey of growth and reflection",
            'chapters': chapters,
            'compilation_method': compilation_method,
            'journal_type': journal_type
        }

    @staticmethod
    def _apply_ai_enhancements(structure, enhancements, user):
        """Apply AI enhancements to the journal structure"""

        if 'chapter_introductions' in enhancements:
            for chapter in structure.get('chapters', []):
                try:
                    intro = AIService.generate_chapter_introduction(
                        chapter_title=chapter['title'],
                        chapter_description=chapter.get('description', ''),
                        user=user
                    )
                    chapter['ai_introduction'] = intro
                except Exception as e:
                    logger.warning(f"Failed to generate chapter introduction: {e}")

        if 'reflection_questions' in enhancements:
            try:
                questions = AIService.generate_reflection_questions(
                    journal_type=structure.get('journal_type', 'growth'),
                    user=user
                )
                structure['reflection_questions'] = questions
            except Exception as e:
                logger.warning(f"Failed to generate reflection questions: {e}")

        if 'thematic_connections' in enhancements:
            try:
                connections = AIService.generate_thematic_connections(structure, user)
                structure['thematic_connections'] = connections
            except Exception as e:
                logger.warning(f"Failed to generate thematic connections: {e}")

        if 'readers_guide' in enhancements:
            try:
                guide = AIService.generate_readers_guide(structure, user)
                structure['readers_guide'] = guide
            except Exception as e:
                logger.warning(f"Failed to generate readers guide: {e}")

        return structure

    @staticmethod
    def _calculate_suggested_price(analysis, structure):
        """Calculate suggested price for the journal"""

        base_price = 4.99

        # Quality factor
        quality_score = analysis.get('quality_score', {}).get('score', 50)
        quality_multiplier = 1 + (quality_score - 50) / 100

        # Length factor
        estimated_length = structure.get('estimated_length', 0)
        if estimated_length > 10000:
            length_multiplier = 1.5
        elif estimated_length > 5000:
            length_multiplier = 1.2
        else:
            length_multiplier = 1.0

        # Chapter count factor
        chapter_count = len(structure.get('chapters', []))
        chapter_multiplier = 1 + (chapter_count - 3) * 0.1

        # AI enhancements factor
        enhancements = structure.get('ai_enhancements', [])
        enhancement_multiplier = 1 + len(enhancements) * 0.15

        suggested_price = base_price * quality_multiplier * length_multiplier * chapter_multiplier * enhancement_multiplier

        # Round to reasonable price points
        if suggested_price < 2.99:
            return 2.99
        elif suggested_price < 4.99:
            return 4.99
        elif suggested_price < 7.99:
            return 7.99
        elif suggested_price < 12.99:
            return 12.99
        elif suggested_price < 19.99:
            return 19.99
        else:
            return 24.99

    @staticmethod
    def create_compiled_journal(user, title, description, price, structure, entry_ids, cover_image_data=None):
        """Create the final compiled journal"""

        # Create journal
        journal = Journal.objects.create(
            title=title,
            description=description,
            author=user,
            price=price,
            is_published=True,
            privacy_setting='public',
            date_published=timezone.now()
        )

        # Handle cover image if provided
        if cover_image_data:
            # Process cover image data (you'd implement this based on your image handling)
            pass

        # Create journal entries based on structure
        entries = Entry.objects.filter(id__in=entry_ids, user=user)

        for chapter in structure.get('chapters', []):
            chapter_entry_ids = chapter.get('entry_ids', [])
            chapter_entries = entries.filter(id__in=chapter_entry_ids)

            # Create chapter introduction if available
            if chapter.get('ai_introduction'):
                JournalEntry.objects.create(
                    journal=journal,
                    title=f"{chapter['title']} - Introduction",
                    content=chapter['ai_introduction'],
                    entry_date=timezone.now().date(),
                    is_included=True,
                    entry_type='introduction'
                )

            # Add chapter entries
            for entry in chapter_entries.order_by('created_at'):
                JournalEntry.objects.create(
                    journal=journal,
                    title=entry.title,
                    content=entry.content,
                    entry_date=entry.created_at.date(),
                    is_included=True,
                    original_entry=entry
                )

        # Add reflection questions if available
        if structure.get('reflection_questions'):
            JournalEntry.objects.create(
                journal=journal,
                title="Reflection Questions",
                content=structure['reflection_questions'],
                entry_date=timezone.now().date(),
                is_included=True,
                entry_type='reflection'
            )

        # Add readers guide if available
        if structure.get('readers_guide'):
            JournalEntry.objects.create(
                journal=journal,
                title="Reader's Guide",
                content=structure['readers_guide'],
                entry_date=timezone.now().date(),
                is_included=True,
                entry_type='guide'
            )

        # Mark original entries as published
        entries.update(published_in_journal=journal)

        # Update journal statistics
        try:
            journal.update_cached_counts()
        except:
            pass

        return journal

class JournalTemplateService:
    """Service for managing journal templates"""

    @staticmethod
    def get_available_templates():
        """Get available journal templates"""

        templates = [
            {
                'id': 'transformation',
                'name': 'The Transformation',
                'description': 'Perfect for documenting life changes, challenges overcome, and lessons learned',
                'category': 'Personal Growth',
                'success_rate': 94,
                'average_price': 15.99,
                'structure': {
                    'chapters': ['The Beginning', 'Facing Challenges', 'Breaking Through', 'New Horizons'],
                    'focus': 'growth_narrative'
                }
            },
            {
                'id': 'adventures',
                'name': 'Adventures',
                'description': 'Share your adventures, cultural discoveries, and travel insights with readers',
                'category': 'Travel & Experiences',
                'success_rate': 89,
                'average_price': 12.99,
                'structure': {
                    'chapters': ['Departure', 'Cultural Immersion', 'Unexpected Encounters', 'Coming Home'],
                    'focus': 'experiential_narrative'
                }
            },
            {
                'id': 'reflections',
                'name': 'Reflections',
                'description': 'Deep thoughts, daily observations, and philosophical reflections on life',
                'category': 'Mindful Living',
                'success_rate': 87,
                'average_price': 9.99,
                'structure': {
                    'chapters': ['Daily Observations', 'Deep Thoughts', 'Life Lessons', 'Future Aspirations'],
                    'focus': 'contemplative_narrative'
                }
            },
            {
                'id': 'creative_journey',
                'name': 'Creative Journey',
                'description': 'Document your creative process, artistic development, and creative breakthroughs',
                'category': 'Creativity & Arts',
                'success_rate': 85,
                'average_price': 14.99,
                'structure': {
                    'chapters': ['Creative Awakening', 'Developing Skills', 'Breakthrough Moments', 'Artistic Vision'],
                    'focus': 'creative_narrative'
                }
            },
            {
                'id': 'relationship_chronicles',
                'name': 'Relationship Chronicles',
                'description': 'Explore relationships, love, friendship, and human connections',
                'category': 'Relationships & Love',
                'success_rate': 88,
                'average_price': 11.99,
                'structure': {
                    'chapters': ['Connection', 'Growing Together', 'Challenges & Growth', 'Deeper Understanding'],
                    'focus': 'relationship_narrative'
                }
            }
        ]

        return templates