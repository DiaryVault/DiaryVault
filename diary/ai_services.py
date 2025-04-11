# diary/ai_services.py
import json
import requests
from django.conf import settings
from .models import Entry, SummaryVersion, UserInsight, Biography

class AIService:
    """Service for interacting with AI models (Mistral via Ollama)"""

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

            # Get response from Ollama (Mistral model)
            prompt = f"""
            Analyze this diary entry and provide a thoughtful summary with insights about the person's feelings,
            motivations, and patterns. Identify any notable themes or emotional states:

            Title: {entry.title}
            Date: {entry.created_at.strftime('%Y-%m-%d')}
            Content: {entry.content}

            Format your response as a brief summary (2-3 paragraphs) focused on psychological insights.
            """

            summary = AIService._get_ollama_response(prompt)

            # Update the entry with new summary
            entry.summary = summary
            entry.save()

            return summary

        except Exception as e:
            print(f"Error generating summary: {str(e)}")
            return "Unable to generate summary at this time."

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

            response = AIService._get_ollama_response(prompt)

            # Parse JSON response
            try:
                insights_data = json.loads(response)

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
                print(f"Error parsing AI response as JSON: {response}")
                return []

        except Exception as e:
            print(f"Error generating insights: {str(e)}")
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

            biography_content = AIService._get_ollama_response(prompt)

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
            print(f"Error generating biography: {str(e)}")
            return None

    @staticmethod
    def _get_ollama_response(prompt, model="mistral"):
        """Send a request to Ollama API and get response"""
        # For local Ollama
        ollama_url = getattr(settings, 'OLLAMA_URL', 'http://localhost:11434/api/generate')

        try:
            response = requests.post(
                ollama_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60
            )

            if response.status_code == 200:
                return response.json().get('response', '')
            else:
                print(f"Ollama API error: {response.status_code} - {response.text}")
                return "Error connecting to Ollama. Please make sure it's running."

        except Exception as e:
            print(f"Error calling Ollama API: {str(e)}")
            return f"Error connecting to Ollama: {str(e)}. Please make sure it's running locally."
