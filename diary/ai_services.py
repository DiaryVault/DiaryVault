# diary/ai_services.py
import json
import requests
from django.conf import settings
from .models import Entry, SummaryVersion, UserInsight, Biography
import time
from requests.exceptions import Timeout, ConnectionError, RequestException
import logging
from django.utils import timezone
from django.apps import apps

logger = logging.getLogger(__name__)

class AIService:
    """Service for interacting with AI models (using Groq)"""

    @staticmethod
    def generate_entry_summary(entry):
        """Generate a summary for a diary entry"""
        try:
            # Store previous summary as a version if it exists
            if entry.summary:
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
                        description=pattern['description'],
                        insight_type='pattern'
                    )
                    insights.append(insight)

                # Add suggestions
                for suggestion in insights_data.get('suggestions', []):
                    insight = UserInsight.objects.create(
                        user=user,
                        title=suggestion['title'],
                        description=suggestion['description'],
                        insight_type='suggestion'
                    )
                    insights.append(insight)

                # Add mood analysis
                mood = insights_data.get('mood_analysis', {})
                if mood:
                    insight = UserInsight.objects.create(
                        user=user,
                        title=mood['title'],
                        description=mood['description'],
                        insight_type='mood'
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
    def _get_groq_response(prompt, temperature=0.7, max_tokens=800):
        """Send a request to Groq API and get response"""
        request_id = int(time.time() * 1000)  # Simple request ID for tracking
        logger.info(f"Groq API Request {request_id} started for prompt length {len(prompt)}")

        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROK_API_KEY}',
                'X-Request-ID': str(request_id)
            }

            payload = {
                'model': 'llama3-70b-8192',
                'messages': [
                    {'role': 'system', 'content': 'You are a helpful AI assistant for journal analysis.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': temperature,
                'max_tokens': max_tokens
            }

            # Add proper timeout to prevent hanging requests
            start_time = time.time()
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=60  # Longer timeout for more complex generations
            )
            api_time = time.time() - start_time

            # Log response time for performance monitoring
            logger.info(f"Groq API Request {request_id} completed in {api_time:.2f}s with status {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Groq API Request {request_id} failed: {response.status_code} - {response.text}")
                return "Error connecting to Groq API. Please try again later."

            response_data = response.json()

            # Validate response structure
            if 'choices' not in response_data or not response_data['choices']:
                error_msg = f"Invalid API response structure: {response_data}"
                logger.error(f"Groq API Request {request_id}: {error_msg}")
                return "Error with AI response format. Please try again later."

            # Extract the message content
            return response_data['choices'][0]['message']['content']

        except Timeout:
            logger.error(f"Groq API Request {request_id} timed out")
            return "Request timed out. Please try again later."
        except ConnectionError as e:
            logger.error(f"Groq API Request {request_id} connection error: {str(e)}")
            return "Connection error. Please check your internet connection."
        except Exception as e:
            logger.error(f"Groq API Request {request_id} error: {str(e)}", exc_info=True)
            return f"Error: {str(e)}. Please try again later."

    @staticmethod
    def _get_ollama_response(prompt, model="mistral"):
        """DEPRECATED: Use _get_groq_response instead"""
        logger.warning("_get_ollama_response is deprecated. Using Groq instead.")
        return AIService._get_groq_response(prompt)

    @staticmethod
    def generate_user_biography(user, chapter=None):
        """
        Generate a biography for a user based on their journal entries
        Returns the generated biography text
        """
        from django.conf import settings
        # Import models using apps.get_model to avoid circular imports
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

                return biography_content

        except Exception as e:
            logger.error(f"Biography generation {request_id} error: {str(e)}", exc_info=True)
            if chapter:
                return f"Unable to generate the '{chapter}' chapter at this time. Please try again later."
            else:
                return "Unable to generate your biography at this time. Please try again later."
