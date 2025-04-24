import json
import logging
import time
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.shortcuts import get_object_or_404

from ..models import Entry, Tag
from ..utils.ai_helpers import generate_ai_content, generate_ai_content_personalized
from ..utils.analytics import get_content_hash, auto_generate_tags
from ..services.ai_service import AIService

logger = logging.getLogger(__name__)

@require_POST
@csrf_exempt
def demo_journal(request):
    request_id = int(time.time() * 1000)
    logger.info(f"Journal request {request_id} started")

    try:
        start_time = time.time()

        data = json.loads(request.body)
        journal_content = data.get('journal_content', '')
        # Check if personalization is requested
        personalize = data.get('personalize', False)

        if not journal_content:
            logger.warning(f"Journal request {request_id}: No content provided")
            return JsonResponse({'error': 'No content provided'}, status=400)

        # If personalization is requested and user is logged in, use that
        if personalize and request.user.is_authenticated:
            # Create a unique cache key based on content and user
            user_id = request.user.id
            cache_key = f"journal_entry:user{user_id}:{get_content_hash(journal_content)}"
        else:
            # Otherwise use standard cache key
            cache_key = f"journal_entry:{get_content_hash(journal_content)}"

        # Try to get cached response
        cached_response = cache.get(cache_key)
        if cached_response:
            logger.info(f"Journal request {request_id} served from cache")
            cached_response['cache_hit'] = True
            cached_response['cache_type'] = 'server'
            cached_response['response_time'] = round(time.time() - start_time, 3)
            return JsonResponse(cached_response)

        # Generate new content if not cached
        if personalize and request.user.is_authenticated:
            # Use personalized generation
            response_data = generate_ai_content_personalized(journal_content, request.user)
        else:
            # Use standard generation
            response_data = generate_ai_content(journal_content)

        # Add metadata
        response_data['cache_hit'] = False
        response_data['cache_type'] = 'none'
        response_data['request_time'] = round(time.time() - start_time, 2)

        # Cache the response (only if successful and no errors)
        if 'error' not in response_data:
            cache.set(cache_key, response_data, timeout=3600)  # Cache for 1 hour

        logger.info(f"Journal request {request_id} completed in {response_data['request_time']}s")
        return JsonResponse(response_data)

    except json.JSONDecodeError:
        logger.error(f"Journal request {request_id}: Invalid JSON in request")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Journal request {request_id} failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Server error processing your request',
            'error_details': str(e),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, status=500)

@require_POST
def regenerate_summary_ajax(request, entry_id):
    """AJAX view to regenerate an entry summary"""
    if request.method == 'POST':
        entry = get_object_or_404(Entry, id=entry_id, user=request.user)
        summary = AIService.generate_entry_summary(entry)
        return JsonResponse({'success': True, 'summary': summary})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@require_POST
def save_generated_entry(request):
    """Save a generated journal entry to the database"""
    try:
        data = json.loads(request.body)
        title = data.get('title')
        content = data.get('content')

        # Store in session regardless of authentication status
        request.session['pending_entry'] = {
            'title': title,
            'content': content,
            'mood': data.get('mood'),
            'tags': data.get('tags', [])
        }

        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'login_required': True,
                'message': 'Please log in to save your entry'
            }, status=401)

        # User is authenticated, proceed with saving
        if not title or not content:
            return JsonResponse({'success': False, 'error': 'Missing title or content'}, status=400)

        # Create the new entry
        entry = Entry.objects.create(
            user=request.user,
            title=title,
            content=content,
            mood=data.get('mood')
        )

        # Add tags if provided
        tags = data.get('tags', [])
        if not tags and content:
            # Auto-generate tags if none were provided
            tags = auto_generate_tags(content, data.get('mood'))

        if tags:
            for tag_name in tags:
                tag, created = Tag.objects.get_or_create(
                    name=tag_name.lower().strip(),
                    user=request.user
                )
                entry.tags.add(tag)

        # Clear the pending entry from session
        if 'pending_entry' in request.session:
            del request.session['pending_entry']

        return JsonResponse({
            'success': True,
            'entry_id': entry.id,
            'message': 'Entry saved successfully'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error saving generated entry: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Server error while saving entry',
            'details': str(e)
        }, status=500)
