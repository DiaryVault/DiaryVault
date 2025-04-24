import json
import logging
import time
import requests
from datetime import datetime, timedelta
from requests.exceptions import Timeout, ConnectionError, RequestException

from django.utils import timezone
from django.conf import settings
from django.apps import apps

from ..utils.ai_helpers import generate_ai_content, generate_ai_content_personalized

logger = logging.getLogger(__name__)

class AIService:
    """
    Service class for AI integration features

    This class centralizes all AI-related functionality, making it easier to:
    1. Track and log AI usage
    2. Swap out AI providers if needed
    3. Implement rate limiting or quotas
    4. Cache common requests
    """

    @staticmethod
    def generate_entry_summary(entry):
        """Generate a summary for a diary entry"""
        try:
            # Store previous summary as a version if it exists
            if entry.summary:
                SummaryVersion = apps.get_model('diary', 'SummaryVersion')
                SummaryVersion.objects.create(
                    entry=entry,
                    summary=entry.summary
                )

            # Get response from Groq
            prompt = f"""
            Analyze this diary entry and provide a thoughtful summary with insights about the person's feelings,
            motivations, and patterns. Identify any notable themes or emotional states:

            Title: {entry.title}
            Date: {entry.created_at.strftime('%Y-%m-%d')}
            Content: {entry.content}

            Format your response as a brief summary (2-3 paragraphs) focused on psychological insights.
            """

            summary = AIService._get_groq_response(prompt)

            # Update the entry with new summary
            entry.summary = summary
            entry.summary_generated_at = timezone.now()
            entry.save()

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return "Unable to generate summary at this time."

    @staticmethod
    def extract_json_from_text(text):
        """Extract JSON from text that might contain backticks and explanatory text"""
        # Look for JSON between triple backticks
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1).strip()

        # If no backticks, try to find JSON by looking for opening brace
        try:
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return text[json_start:json_end]
        except:
            pass

        # If all else fails, return the original text
        return text

    @staticmethod
    def generate_insights(user, entries=None):
        """Generate insights based on user's diary entries"""
        try:
            Entry = apps.get_model('diary', 'Entry')
            UserInsight = apps.get_model('diary', 'UserInsight')

            if entries is None:
                entries = Entry.objects.filter(user=user).order_by('-created_at')[:20]

            if not entries:
                return []

            # Prepare entry data
            entry_data = "\n\n".join([
                f"Entry {i+1}:\nTitle: {entry.title}\nDate: {entry.created_at.strftime('%Y-%m-%d')}\nContent: {entry.content[:200]}..."
                for i, entry in enumerate(entries)
            ])

            prompt = f"""
            Based on these diary entries, identify patterns, make observations about mood trends,
            and suggest personal growth opportunities. Focus on:

            1. Recurring themes or concerns
            2. Mood patterns
            3. Potential areas for personal development
            4. Notable achievements or progress

            {entry_data}

            Format your response as JSON with the following structure:
            {{
                "patterns": [
                    {{"title": "Pattern title", "description": "Description of pattern"}}
                ],
                "suggestions": [
                    {{"title": "Suggestion title", "description": "Description of suggestion"}}
                ],
                "mood_analysis": {{"title": "Mood Analysis", "description": "Overall mood analysis"}}
            }}
            """

            response = AIService._get_groq_response(prompt)

            # Parse JSON response
            try:
                json_text = AIService.extract_json_from_text(response)
                insights_data = json.loads(json_text)

                # Clear previous insights
                UserInsight.objects.filter(user=user).delete()

                # Create new insights
                insights = []

                # Add patterns
                for pattern in insights_data.get('patterns', []):
                    insight = UserInsight.objects.create(
                        user=user,
                        title=pattern['title'],
                        content=pattern.get('description', ''),  # Handle both description and content keys
                        insight_type='pattern'
                    )
                    insights.append(insight)

                # Add suggestions
                for suggestion in insights_data.get('suggestions', []):
                    insight = UserInsight.objects.create(
                        user=user,
                        title=suggestion['title'],
                        content=suggestion.get('description', ''),  # Handle both description and content keys
                        insight_type='suggestion'
                    )
                    insights.append(insight)

                # Add mood analysis
                mood = insights_data.get('mood_analysis', {})
                if mood:
                    insight = UserInsight.objects.create(
                        user=user,
                        title=mood['title'],
                        content=mood.get('description', ''),  # Handle both description and content keys
                        insight_type='mood_analysis'  # Use consistent naming
                    )
                    insights.append(insight)

                return insights

            except json.JSONDecodeError:
                logger.error(f"Error parsing AI response as JSON: {response}")
                return []

        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            return []

    @staticmethod
    def generate_biography(user, time_period_start=None, time_period_end=None):
        """Generate a biography based on a user's diary entries"""
        try:
            Entry = apps.get_model('diary', 'Entry')
            Biography = apps.get_model('diary', 'Biography')

            # Get entries for the specified time period
            entries = Entry.objects.filter(user=user)
            if time_period_start:
                entries = entries.filter(created_at__date__gte=time_period_start)
            if time_period_end:
                entries = entries.filter(created_at__date__lte=time_period_end)

            entries = entries.order_by('created_at')

            if not entries:
                return None

            # Prepare entry data
            entry_data = "\n\n".join([
                f"Entry {i+1}:\nTitle: {entry.title}\nDate: {entry.created_at.strftime('%Y-%m-%d')}\nContent: {entry.content[:500]}..."
                for i, entry in enumerate(entries[:30])  # Limit to 30 entries to avoid token limits
            ])

            period_description = ""
            if time_period_start and time_period_end:
                period_description = f"from {time_period_start.strftime('%B %Y')} to {time_period_end.strftime('%B %Y')}"

            prompt = f"""
            Write a cohesive, first-person biography based on these diary entries {period_description}.
            Craft a narrative that captures the person's experiences, growth, and significant events.
            Use a personal, reflective tone as if the person is telling their own life story.

            {entry_data}

            Write the biography as a thoughtful, introspective personal narrative with natural transitions
            between events and themes. Use the first person perspective. Make it emotionally resonant and
            capture the person's voice based on their diary entries.

            The biography should be divided into clear paragraphs and should be around 500-800 words.
            """

            biography_content = AIService._get_groq_response(prompt)

            # Create or update biography
            biography, created = Biography.objects.update_or_create(
                user=user,
                time_period_start=time_period_start,
                time_period_end=time_period_end,
                defaults={
                    'content': biography_content,
                    'title': f"My Life Story {period_description}"
                }
            )

            return biography

        except Exception as e:
            logger.error(f"Error generating biography: {str(e)}")
            return None

    @staticmethod
    def generate_journal_entry(journal_content, user=None, personalize=False):
        """Generate a full journal entry from brief notes"""
        try:
            if personalize and user:
                return generate_ai_content_personalized(journal_content, user)
            else:
                return generate_ai_content(journal_content)
        except Exception as e:
            logger.error(f"Error generating journal entry: {str(e)}", exc_info=True)
            return {
                'error': f"Failed to generate journal entry: {str(e)}",
                'title': "Journal Entry",
                'entry': journal_content
            }

    @staticmethod
    def generate_user_biography(user, chapter=None):
        """
        Generate a biography for a user based on their journal entries
        Returns the generated biography text
        """
        # Import models using apps.get_model to avoid circular imports
        from django.apps import apps
        from django.utils import timezone
        import time
        import json
        import requests
        from django.conf import settings
        from requests.exceptions import RequestException
        import logging

        logger = logging.getLogger(__name__)

        Entry = apps.get_model('diary', 'Entry')
        UserInsight = apps.get_model('diary', 'UserInsight')
        Biography = apps.get_model('diary', 'Biography')

        # Try to get LifeChapter if it exists
        try:
            LifeChapter = apps.get_model('diary', 'LifeChapter')
            has_life_chapters = True
        except LookupError:
            has_life_chapters = False

        request_id = int(time.time() * 1000)
        logger.info(f"Biography generation {request_id} started for user {user.username}")

        try:
            # Get all entries for this user
            entries = Entry.objects.filter(user=user).order_by('-created_at')

            if not entries:
                logger.warning(f"No journal entries found for user {user.username}")
                return "Add more journal entries to generate your biography. Your life story will be crafted based on your journaling history."

            # Get entry content samples (limit to prevent token overflow)
            entry_samples = []
            for entry in entries[:20]:  # Use up to 20 most recent entries
                entry_sample = {
                    'date': entry.created_at.strftime('%Y-%m-%d'),
                    'title': entry.title,
                    'content': entry.content[:300] + "..." if len(entry.content) > 300 else entry.content,
                }

                # Add mood if it exists
                if hasattr(entry, 'mood') and entry.mood:
                    entry_sample['mood'] = entry.mood

                # Add tags if they exist
                if hasattr(entry, 'tags'):
                    try:
                        entry_sample['tags'] = ", ".join([tag.name for tag in entry.tags.all()])
                    except:
                        pass

                entry_samples.append(entry_sample)

            # Get user insights if available
            insights = UserInsight.objects.filter(user=user)
            insight_texts = [f"{insight.title}: {insight.content}" for insight in insights]

            # Format entries and insights as context for the API
            entries_text = json.dumps(entry_samples, indent=2)
            insights_text = "\n".join(insight_texts) if insight_texts else "No insights available yet."

            # Determine which chapter to generate
            chapter_content = ""
            if chapter and has_life_chapters:
                chapter_obj = None
                try:
                    chapter_obj = LifeChapter.objects.get(user=user, title__iexact=chapter) or \
                                LifeChapter.objects.get(user=user, slug__iexact=chapter)

                    chapter_title = chapter_obj.title
                    chapter_description = chapter_obj.description

                except LifeChapter.DoesNotExist:
                    # Use the provided chapter name directly
                    chapter_title = chapter
                    chapter_description = f"Events related to {chapter}"

                chapter_content = f"""
                Focus on generating content for the chapter: "{chapter_title}"
                Chapter description: {chapter_description}

                This should be a cohesive section focusing specifically on this area of the user's life.
                """
            elif chapter:
                # Handle case when LifeChapter doesn't exist but chapter is specified
                chapter_title = chapter
                chapter_content = f"""
                Focus on generating content for the chapter: "{chapter_title}"
                This should be a cohesive section focusing specifically on this area of the user's life.
                """

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROK_API_KEY}',
                'X-Request-ID': str(request_id)
            }

            prompt = f"""
            Generate a thoughtful, biographical narrative based on the user's journal entries.

            USER'S JOURNAL ENTRIES (sample):
            {entries_text}

            USER'S INSIGHTS:
            {insights_text}

            {chapter_content}

            Guidelines:
            1. Write in third person, as if this is a biography about the person's life
            2. Maintain a respectful, reflective tone
            3. Extract themes, patterns, and significant events from their entries
            4. Create a coherent narrative that captures their personality and experiences
            5. Avoid inventing major life events not supported by the entries
            6. Use elegant, thoughtful language appropriate for a biographical work
            7. Organize content into meaningful paragraphs with good flow
            8. Length should be approximately 800-1200 words
            """

            payload = {
                'model': 'llama3-70b-8192',
                'messages': [
                    {'role': 'system', 'content': 'You are a skilled biographer who creates compelling life narratives based on journal entries.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.7,
                'max_tokens': 1500
            }

            start_time = time.time()
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30  # Biography generation needs more time
            )
            api_time = time.time() - start_time

            logger.info(f"Biography generation {request_id} completed in {api_time:.2f}s with status {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Biography generation {request_id} failed: {response.status_code} - {response.text}")
                raise RequestException(f"API returned status code {response.status_code}")

            response_data = response.json()

            # Validate response structure
            if 'choices' not in response_data or not response_data['choices']:
                error_msg = f"Invalid API response structure: {response_data}"
                logger.error(f"Biography generation {request_id}: {error_msg}")
                raise ValueError(error_msg)

            biography_content = response_data['choices'][0]['message']['content']

            # Store the generated biography or chapter
            if chapter:
                # Get most recent biography or create a new one
                biography = Biography.objects.filter(user=user).order_by('-updated_at').first()
                if not biography:
                    biography = Biography(
                        user=user,
                        title="My Life Story",
                        content="",
                        time_period_start=timezone.now().date() - timezone.timedelta(days=365*5),  # Last 5 years
                        time_period_end=timezone.now().date()
                    )
                    biography.save()

                # Update the specific chapter content in the biography object
                chapter_key = chapter.lower().replace(' ', '_')
                chapters_data = biography.chapters_data or {}
                chapters_data[chapter_key] = {
                    'title': chapter,
                    'content': biography_content,
                    'last_updated': timezone.now().isoformat()
                }
                biography.chapters_data = chapters_data
                biography.save()

                return biography_content
            else:
                # Get most recent biography or create a new one
                biography = Biography.objects.filter(user=user).order_by('-updated_at').first()
                if not biography:
                    biography = Biography(
                        user=user,
                        title="My Life Story",
                        time_period_start=timezone.now().date() - timezone.timedelta(days=365*5),  # Last 5 years
                        time_period_end=timezone.now().date()
                    )

                biography.content = biography_content
                biography.save()

                # Auto-classify biography into chapters
                from ..services.ai_service import AIService
                auto_chapters = AIService._auto_classify_biography_into_chapters(biography_content, user)

                # If we already have chapters_data, merge with new data
                if biography.chapters_data:
                    chapters_data = biography.chapters_data
                    for key, value in auto_chapters.items():
                        chapters_data[key] = value
                else:
                    chapters_data = auto_chapters

                biography.chapters_data = chapters_data
                biography.save()

                # If we have LifeChapter model and no chapters exist, create default ones based on the auto-classification
                if has_life_chapters and not LifeChapter.objects.filter(user=user).exists():
                    standard_chapters = {
                        "childhood": "Childhood",
                        "education": "Education",
                        "career": "Career",
                        "relationships": "Relationships",
                        "personal_growth": "Personal Growth",
                        "recent_years": "Recent Years"
                    }

                    for key, title in standard_chapters.items():
                        if key in chapters_data and chapters_data[key].get('content'):
                            # Create the chapter if it has content
                            LifeChapter.objects.create(
                                user=user,
                                title=title,
                                time_period=f"Your {title.lower()} period",
                                description=f"This chapter covers your {title.lower()} experiences."
                            )

                return biography_content

        except Exception as e:
            logger.error(f"Biography generation {request_id} error: {str(e)}", exc_info=True)
            if chapter:
                return f"Unable to generate the '{chapter}' chapter at this time. Please try again later."
            else:
                return "Unable to generate your biography at this time. Please try again later."

    def _auto_classify_biography_into_chapters(biography_content, user):
        """
        Automatically classify a biography into standard chapters.
        This uses AI to identify and separate content into appropriate life chapters.
        """
        # Import models here to avoid circular imports
        from django.apps import apps
        from django.utils import timezone
        import json
        import re
        import time
        import requests
        from django.conf import settings

        # Get models
        LifeChapter = apps.get_model('diary', 'LifeChapter')

        request_id = int(time.time() * 1000)
        logger.info(f"Auto-classification {request_id} started for user {user.username}")

        try:
            # Standard chapter categories
            standard_chapters = [
                "Childhood",
                "Education",
                "Career",
                "Relationships",
                "Personal Growth",
                "Recent Years"
            ]

            # Create prompt for classification
            classification_prompt = f"""
            I have a biography text that needs to be separated into the following chapters:

            {', '.join(standard_chapters)}

            Please read the biography and extract content relevant to each chapter.
            For each chapter, return only the content that belongs to that specific chapter.

            Format the response as JSON with the following structure:
            {{
                "childhood": {{ "content": "extracted content for childhood chapter here" }},
                "education": {{ "content": "extracted content for education chapter here" }},
                "career": {{ "content": "extracted content for career chapter here" }},
                "relationships": {{ "content": "extracted content for relationships chapter here" }},
                "personal_growth": {{ "content": "extracted content for personal growth chapter here" }},
                "recent_years": {{ "content": "extracted content for recent years chapter here" }}
            }}

            Here is the biography to classify:

            {biography_content}
            """

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROK_API_KEY}',
                'X-Request-ID': str(request_id)
            }

            payload = {
                'model': 'llama3-70b-8192',
                'messages': [
                    {'role': 'system', 'content': 'You are an expert at analyzing and organizing biographies into thematic chapters.'},
                    {'role': 'user', 'content': classification_prompt}
                ],
                'temperature': 0.3,  # Lower temperature for more deterministic output
                'max_tokens': 1500
            }

            start_time = time.time()
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            api_time = time.time() - start_time

            logger.info(f"Auto-classification {request_id} completed in {api_time:.2f}s with status {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Auto-classification {request_id} failed: {response.status_code} - {response.text}")
                return {}

            response_data = response.json()

            # Extract the JSON content from the response
            content = response_data['choices'][0]['message']['content']

            # Try to extract JSON from the response

            # First try to extract JSON from code blocks
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # If no code block, look for opening and closing braces
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                else:
                    # No JSON found
                    logger.error(f"Auto-classification {request_id}: No JSON found in response")
                    return {}

            try:
                chapters_data = json.loads(json_str)

                # Ensure all keys are properly formatted
                formatted_data = {}
                for chapter in standard_chapters:
                    key = chapter.lower().replace(' ', '_')
                    normalized_key = key.replace('-', '_')

                    # Check for various possible keys
                    if key in chapters_data:
                        formatted_data[key] = chapters_data[key]
                    elif normalized_key in chapters_data:
                        formatted_data[key] = chapters_data[normalized_key]
                    elif chapter.lower() in chapters_data:
                        formatted_data[key] = chapters_data[chapter.lower()]
                    elif chapter in chapters_data:
                        formatted_data[key] = chapters_data[chapter]

                # Add timestamps to each chapter
                current_time = timezone.now().isoformat()
                for key in formatted_data:
                    if isinstance(formatted_data[key], dict) and 'content' in formatted_data[key]:
                        formatted_data[key]['last_updated'] = current_time
                    else:
                        # If it's not a dict with content (just text or wrong format), convert to proper format
                        if isinstance(formatted_data[key], dict):
                            content_value = formatted_data[key].get('content', str(formatted_data[key]))
                        else:
                            content_value = str(formatted_data[key])

                        formatted_data[key] = {
                            'content': content_value,
                            'last_updated': current_time
                        }

                return formatted_data

            except json.JSONDecodeError:
                logger.error(f"Auto-classification {request_id}: JSON parsing error: {json_str}")
                return {}

        except Exception as e:
            logger.error(f"Auto-classification {request_id} error: {str(e)}", exc_info=True)
            return {}


    @staticmethod
    def _get_groq_response(prompt, model="llama3-70b-8192", temperature=0.7, max_tokens=1000):
        """
        Get a response from the Groq API

        Args:
            prompt (str): The prompt to send to the API
            model (str): The model to use (default: llama3-70b-8192)
            temperature (float): Randomness parameter (default: 0.7)
            max_tokens (int): Maximum number of tokens to generate (default: 1000)

        Returns:
            str: The generated text response
        """
        try:
            import requests
            import time
            from django.conf import settings

            request_id = int(time.time() * 1000)

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROK_API_KEY}',  # Using GROK_API_KEY from settings
                'X-Request-ID': str(request_id)
            }

            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'You are a helpful assistant.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': temperature,
                'max_tokens': max_tokens
            }

            start_time = time.time()
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            api_time = time.time() - start_time

            logger.info(f"Groq API request {request_id} completed in {api_time:.2f}s with status {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Groq API request {request_id} failed: {response.status_code} - {response.text}")
                raise RequestException(f"API returned status code {response.status_code}")

            response_data = response.json()

            # Validate response structure
            if 'choices' not in response_data or not response_data['choices']:
                error_msg = f"Invalid API response structure: {response_data}"
                logger.error(f"Groq API request {request_id}: {error_msg}")
                raise ValueError(error_msg)

            return response_data['choices'][0]['message']['content']

        except Exception as e:
            logger.error(f"Error in _get_groq_response: {str(e)}", exc_info=True)
            raise
