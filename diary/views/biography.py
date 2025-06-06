import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from diary.models import LifeChapter as Chapter

from ..models import Entry, Biography, LifeChapter
from ..services.ai_service import AIService

logger = logging.getLogger(__name__)

@login_required
def biography(request):
    """View and generate biography"""
    # Get user's biography if it exists
    biography = Biography.objects.filter(user=request.user).first()

    # Count user entries to show how much data is available
    entry_count = Entry.objects.filter(user=request.user).count()

    # Determine date range for entries
    first_entry = Entry.objects.filter(user=request.user).order_by('created_at').first()
    last_entry = Entry.objects.filter(user=request.user).order_by('-created_at').first()

    date_range = "No entries yet"
    if first_entry and last_entry:
        if first_entry.created_at.year == last_entry.created_at.year:
            date_range = f"{first_entry.created_at.strftime('%B %Y')}"
        else:
            date_range = f"{first_entry.created_at.strftime('%B %Y')} to {last_entry.created_at.strftime('%B %Y')}"

    # Initialize variables
    chapters = []
    chapter_contents = {}

    # Photo selection for biography
    featured_photo = None
    life_photos = []
    chapter_photos = []

    # Handle biography generation request
    if request.method == 'POST' and 'generate_biography' in request.POST:
        try:
            # Check if we have an entry first
            entry_count = Entry.objects.filter(user=request.user).count()
            if entry_count == 0:
                messages.warning(request, 'You need to create some journal entries first before generating a biography.')
                return redirect('biography')

            # Create a simple biography if generation fails
            try:
                # Try the existing method first
                biography_text = AIService.generate_biography(request.user)
            except AttributeError:
                # If that fails, create a simple biography
                biography = Biography.objects.filter(user=request.user).first()
                if not biography:
                    biography = Biography(
                        user=request.user,
                        title="My Life Story",
                        content="Your biographical content will appear here once generated with our AI service.",
                        time_period_start=timezone.now().date() - timezone.timedelta(days=365),
                        time_period_end=timezone.now().date()
                    )
                    biography.save()
                messages.info(request, 'A placeholder biography has been created. The full AI-generated biography will be available soon.')
            else:
                # If original method succeeds
                messages.success(request, 'Your biography has been generated successfully!')

            return redirect('biography')

        except Exception as e:
            logger.error(f"Error generating biography: {str(e)}", exc_info=True)
            messages.error(request, 'Failed to generate biography. Please try again later.')
            return redirect('biography')

    # If biography exists, process chapters
    if biography and biography.content:
        # Get or create standard chapters
        chapters = LifeChapter.objects.filter(user=request.user)

        # If we have chapters_data, extract chapter contents
        if biography.chapters_data:
            # Auto-extract chapter content from chapters_data
            for chapter in chapters:
                # Try various possible keys for flexibility
                possible_keys = [
                    chapter.title,
                    chapter.title.lower(),
                    chapter.title.lower().replace(' ', '_'),
                    chapter.title.lower().replace(' ', '')
                ]

                # Check if any key matches in chapters_data
                for key in possible_keys:
                    if key in biography.chapters_data:
                        try:
                            if isinstance(biography.chapters_data[key], dict) and 'content' in biography.chapters_data[key]:
                                chapter_contents[chapter.title] = biography.chapters_data[key]['content']
                            elif isinstance(biography.chapters_data[key], str):
                                chapter_contents[chapter.title] = biography.chapters_data[key]
                        except Exception as e:
                            logger.error(f"Error extracting chapter content: {str(e)}")
                        break

        # Find entries with photos for the biography
        if entry_count > 0:
            try:
                # Simplified approach to find a featured photo
                entries_with_photos = []

                # First try to get entries with photos
                for entry in Entry.objects.filter(user=request.user).order_by('-created_at')[:10]:
                    # Check for photos relationship
                    if hasattr(entry, 'photos') and entry.photos.exists():
                        entries_with_photos.append(entry)
                    # Check for single photo field
                    elif hasattr(entry, 'photo') and entry.photo:
                        entries_with_photos.append(entry)

                # If we found entries with photos, select one for the featured photo
                if entries_with_photos:
                    # Prioritize entries with positive mood if possible
                    positive_entry = None
                    for entry in entries_with_photos:
                        if hasattr(entry, 'mood') and entry.mood in ['happy', 'excited', 'content']:
                            positive_entry = entry
                            break

                    # Use a positive entry if found, otherwise use the first one
                    selected_entry = positive_entry or entries_with_photos[0]

                    # Get photo from the selected entry
                    if hasattr(selected_entry, 'photos') and selected_entry.photos.exists():
                        featured_photo = selected_entry.photos.first().photo
                    elif hasattr(selected_entry, 'photo') and selected_entry.photo:
                        featured_photo = selected_entry.photo
            except Exception as e:
                logger.error(f"Error selecting featured photo: {e}", exc_info=True)

            # Select photos for the gallery
            try:
                # Collect up to 5 unique photos
                photo_count = 0
                for entry in Entry.objects.filter(user=request.user).order_by('-created_at')[:20]:
                    if photo_count >= 5:
                        break

                    # Check for photos relationship
                    if hasattr(entry, 'photos') and entry.photos.exists():
                        for photo in entry.photos.all()[:1]:  # Just get one photo per entry
                            if photo.photo and photo.photo.url:
                                life_photos.append(photo.photo.url)
                                photo_count += 1
                                if photo_count >= 5:
                                    break

                    # Check for single photo field
                    elif hasattr(entry, 'photo') and entry.photo:
                        life_photos.append(entry.photo.url)
                        photo_count += 1
            except Exception as e:
                logger.error(f"Error selecting life photos: {e}", exc_info=True)

            # Select photos for each chapter
            if chapters:
                try:
                    for chapter in chapters:
                        # Try to find entries related to this chapter
                        found_photo = False

                        for entry in Entry.objects.filter(user=request.user)[:50]:
                            # Check if entry has a chapter field matching this chapter
                            if hasattr(entry, 'chapter') and entry.chapter == chapter:
                                # Check if entry has photos
                                if hasattr(entry, 'photos') and entry.photos.exists():
                                    photo = entry.photos.first()
                                    if photo and photo.photo:
                                        chapter_photos.append((str(chapter.id), photo.photo.url))
                                        found_photo = True
                                        break
                                # Check if entry has a photo
                                elif hasattr(entry, 'photo') and entry.photo:
                                    chapter_photos.append((str(chapter.id), entry.photo.url))
                                    found_photo = True
                                    break

                        # If we didn't find a photo specifically related to this chapter,
                        # just use any entry that might be relevant by searching for keywords
                        if not found_photo:
                            # Use the chapter title as a keyword to search in entries
                            keywords = chapter.title.lower().split()

                            for entry in Entry.objects.filter(user=request.user)[:50]:
                                for keyword in keywords:
                                    if (keyword in entry.title.lower() or
                                        (hasattr(entry, 'content') and keyword in entry.content.lower())):
                                        # Check if entry has photos
                                        if hasattr(entry, 'photos') and entry.photos.exists():
                                            photo = entry.photos.first()
                                            if photo and photo.photo:
                                                chapter_photos.append((str(chapter.id), photo.photo.url))
                                                found_photo = True
                                                break
                                        # Check if entry has a photo
                                        elif hasattr(entry, 'photo') and entry.photo:
                                            chapter_photos.append((str(chapter.id), entry.photo.url))
                                            found_photo = True
                                            break
                                if found_photo:
                                    break
                except Exception as e:
                    logger.error(f"Error selecting chapter photos: {e}", exc_info=True)

    # Build context for template
    context = {
        'biography': biography.content if biography and biography.content else None,
        'biography_date': biography.updated_at.strftime('%B %d, %Y') if biography and hasattr(biography, 'updated_at') else None,
        'biography_obj': biography,
        'chapters': chapters,
        'chapter_contents': chapter_contents,
        'entry_count': entry_count,
        'date_range': date_range,
        'has_chapters': len(chapter_contents) > 0,
        'featured_photo': featured_photo,
        'life_photos': life_photos,
        'chapter_photos': chapter_photos
    }

    return render(request, 'diary/biography.html', context)

@login_required
def manage_chapters(request):
    if request.method == 'POST':
        # Process form data
        title = request.POST.get('title')
        description = request.POST.get('description')
        time_period = request.POST.get('time_period')

        # Create a new chapter (you might need to parse time_period here)
        chapter = LifeChapter(
            user=request.user,
            title=title,
            description=description,
            # Handle time_period -> start_date, end_date conversion
        )
        chapter.save()

        messages.success(request, f"Chapter '{title}' created successfully.")
        return redirect('manage_chapters')

    # GET request - display the page with existing chapters
    chapters = LifeChapter.objects.filter(user=request.user)
    return render(request, 'diary/manage_chapters.html', {'chapters': chapters})

@login_required
def regenerate_chapter(request, chapter_id):
    """Regenerate a specific chapter"""
    chapter = get_object_or_404(LifeChapter, id=chapter_id, user=request.user)

    try:
        # Generate just this chapter
        AIService.generate_user_biography(request.user, chapter=chapter.title)
        messages.success(request, f'Chapter "{chapter.title}" has been refreshed!')
    except Exception as e:
        logger.error(f"Error regenerating chapter: {str(e)}", exc_info=True)
        messages.error(request, f'Failed to regenerate chapter. Please try again later.')

    return redirect('biography')

@login_required
def edit_chapter(request, chapter_id):
    """Edit an existing life chapter"""
    chapter = get_object_or_404(LifeChapter, id=chapter_id, user=request.user)

    if request.method == 'POST':
        title = request.POST.get('title')
        time_period = request.POST.get('time_period')
        description = request.POST.get('description')

        if title:
            chapter.title = title
            chapter.time_period = time_period
            chapter.description = description
            chapter.save()
            messages.success(request, f'Chapter "{title}" updated successfully!')
            return redirect('manage_chapters')

    return render(request, 'diary/edit_chapter.html', {'chapter': chapter})

@login_required
def delete_chapter(request, chapter_id):
    """Delete a life chapter"""
    chapter = get_object_or_404(LifeChapter, id=chapter_id, user=request.user)

    if request.method == 'POST':
        title = chapter.title
        chapter.delete()
        messages.success(request, f'Chapter "{title}" deleted successfully!')
        return redirect('manage_chapters')

    return render(request, 'diary/delete_chapter.html', {'chapter': chapter})

@login_required
def generate_biography_api(request):
    """API endpoint to generate a biography or specific chapter"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        # Check if a specific chapter was requested
        chapter = request.GET.get('chapter')

        # Generate the biography or chapter
        content = AIService.generate_user_biography(request.user, chapter=chapter)

        return JsonResponse({
            'success': True,
            'content': content,
            'generated_at': timezone.now().isoformat()
        })
    except Exception as e:
        logger.error(f"API biography generation error: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def delete_chapter(request, chapter_id):
    # Get the chapter or return 404
    chapter = get_object_or_404(Chapter, id=chapter_id, user=request.user)

    # Delete the chapter
    chapter.delete()

    # Add a success message
    messages.success(request, f"Chapter '{chapter.title}' has been deleted successfully.")

    # Redirect back to the manage chapters page
    return redirect('manage_chapters')
