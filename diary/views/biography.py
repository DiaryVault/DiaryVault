import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

from ..models import Entry, Biography, LifeChapter
from ..services.ai_service import AIService

logger = logging.getLogger(__name__)

@login_required
def biography(request):
    """View and generate biography"""
    biography = Biography.objects.filter(user=request.user).first()
    entry_count = Entry.objects.filter(user=request.user).count()

    # Get chapters
    chapters = LifeChapter.objects.filter(user=request.user)

    # Determine date range for entries
    first_entry = Entry.objects.filter(user=request.user).order_by('created_at').first()
    last_entry = Entry.objects.filter(user=request.user).order_by('-created_at').first()

    date_range = "No entries yet"
    if first_entry and last_entry:
        if first_entry.created_at.year == last_entry.created_at.year:
            date_range = f"{first_entry.created_at.strftime('%B %Y')}"
        else:
            date_range = f"{first_entry.created_at.strftime('%B %Y')} to {last_entry.created_at.strftime('%B %Y')}"

    # Initialize chapter contents
    chapter_contents = {}

    # Handle regenerate request
    if request.method == 'POST':
        if 'regenerate_biography' in request.POST:
            try:
                # Generate or regenerate the main biography
                AIService.generate_user_biography(request.user)
                messages.success(request, 'Biography generated successfully!')
            except Exception as e:
                logger.error(f"Error generating biography: {str(e)}", exc_info=True)
                messages.error(request, 'Failed to generate biography. Please try again later.')

            return redirect('biography')

        elif 'regenerate_chapter' in request.POST:
            chapter = request.POST.get('chapter')
            if chapter:
                try:
                    # Generate or regenerate a specific chapter
                    AIService.generate_user_biography(request.user, chapter=chapter)
                    messages.success(request, f'Chapter "{chapter}" generated successfully!')
                except Exception as e:
                    logger.error(f"Error generating chapter {chapter}: {str(e)}", exc_info=True)
                    messages.error(request, f'Failed to generate chapter "{chapter}". Please try again later.')

                return redirect('biography')

    # Get chapter contents if biography exists
    if biography and biography.chapters_data:
        # Debug what's actually in chapters_data
        print("CHAPTERS DATA:", biography.chapters_data)

        # Create a normalized mapping (convert to lowercase with underscores)
        for chapter in chapters:
            chapter_key = chapter.title.lower().replace(' ', '_')
            if chapter_key in biography.chapters_data:
                chapter_contents[chapter.title] = biography.chapters_data[chapter_key]['content']

        # Also check for standard chapters that might not be in your LifeChapter model
        standard_chapters = {
            'childhood': 'Childhood',
            'education': 'Education',
            'career': 'Career Journey',
            'relationships': 'Relationships',
            'personal_growth': 'Personal Growth',
            'recent_years': 'Recent Years'
        }

        for key, title in standard_chapters.items():
            if key in biography.chapters_data and key not in chapter_contents:
                chapter_contents[title] = biography.chapters_data[key]['content']

    context = {
        'biography': biography.content if biography else '',
        'biography_obj': biography,
        'chapters': chapters,
        'chapter_contents': chapter_contents,
        'entry_count': entry_count,
        'date_range': date_range,
        'childhood_content': chapter_contents.get('Childhood', ''),
        'education_content': chapter_contents.get('Education', ''),
        'career_content': chapter_contents.get('Career Journey', ''),
        'relationships_content': chapter_contents.get('Relationships', ''),
        'personal_growth_content': chapter_contents.get('Personal Growth', ''),
        'recent_years_content': chapter_contents.get('Recent Years', '')
    }

    return render(request, 'diary/biography.html', context)

@login_required
def manage_chapters(request):
    chapters = LifeChapter.objects.filter(user=request.user)
    return render(request, 'diary/manage_chapters.html', {'chapters': chapters})

@login_required
def edit_chapter(request, chapter_id):
    chapter = get_object_or_404(LifeChapter, id=chapter_id, user=request.user)
    return render(request, 'diary/edit_chapter.html', {'chapter': chapter})

@login_required
def delete_chapter(request, chapter_id):
    chapter = get_object_or_404(LifeChapter, id=chapter_id, user=request.user)
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
