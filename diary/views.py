from .models import DiaryEntry, SummaryVersion, Tag
from .forms import DiaryEntryForm
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
import subprocess, requests
from django.views.decorators.csrf import csrf_exempt



def call_mistral(prompt):
    try:
        result = subprocess.run(
            ["ollama", "run", "mistral"],
            input=prompt,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"


@login_required
def home(request):
    if request.method == 'POST':
        form = DiaryEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user

            prompt = f"Summarize this diary entry in 2-3 reflective sentences:\n\nTitle: {entry.title}\n\n{entry.content}"
            summary = call_mistral(prompt)
            entry.summary = summary if not summary.startswith("Error") else "AI summary unavailable at the moment."

            entry.save()
            form.save_m2m()
            return redirect('home')
    else:
        form = DiaryEntryForm()

    entries = DiaryEntry.objects.filter(user=request.user).order_by('-created_at')
    tags = Tag.objects.all()
    return render(request, 'diary/home.html', {
        'form': form,
        'entries': entries,
        'tags': tags
    })


def generate_ai_entry(request):
    prompt = "Write a reflective journal entry for someone who had a meaningful but emotionally mixed day."
    content = call_mistral(prompt)
    if content.startswith("Error"):
        return JsonResponse({'error': content}, status=500)
    return JsonResponse({'content': content})


def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'auth/signup.html', {'form': form})


@login_required
def biography(request):
    entries = DiaryEntry.objects.filter(user=request.user).order_by('created_at')

    if not entries.exists():
        return render(request, 'diary/biography.html', {
            'biography': "You haven't written any diary entries yet. Start writing to generate your story!"
        })

    diary_text = "\n\n".join([f"{entry.created_at.date()} - {entry.title}\n{entry.content}" for entry in entries])
    prompt = f"""Based on the following diary entries, write a compelling, emotional, and reflective personal biography for the user.\n\nDiary Entries:\n{diary_text}"""

    bio_text = call_mistral(prompt)
    if bio_text.startswith("Error"):
        bio_text = f"An error occurred while generating your biography: {bio_text}"

    return render(request, 'diary/biography.html', {
        'biography': bio_text
    })


@login_required
def regenerate_summary(request, entry_id):
    entry = DiaryEntry.objects.filter(id=entry_id, user=request.user).first()
    if not entry:
        return JsonResponse({"error": "Entry not found."}, status=404)

    if entry.summary:
        SummaryVersion.objects.create(entry=entry, summary=entry.summary)

    prompt = f"Summarize this diary entry in 2-3 reflective sentences:\n\nTitle: {entry.title}\n\n{entry.content}"
    summary = call_mistral(prompt)
    entry.summary = summary if not summary.startswith("Error") else entry.summary
    entry.save()

    if summary.startswith("Error"):
        return JsonResponse({"error": summary}, status=500)

    return JsonResponse({"summary": entry.summary})


@require_POST
@login_required
def restore_summary(request, version_id):
    version = get_object_or_404(SummaryVersion, id=version_id, entry__user=request.user)
    entry = version.entry
    entry.summary = version.summary
    entry.save()
    return JsonResponse({'summary': entry.summary})

@csrf_exempt
@login_required
def stream_summary(request, entry_id):
    entry = DiaryEntry.objects.filter(id=entry_id, user=request.user).first()
    if not entry:
        return JsonResponse({"error": "Entry not found."}, status=404)

    # Save the old summary as versioned
    if entry.summary:
        SummaryVersion.objects.create(entry=entry, summary=entry.summary)

    prompt = f"Summarize this diary entry in 2-3 reflective sentences:\n\nTitle: {entry.title}\n\n{entry.content}"

    def generate():
        try:
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "mistral",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True
                },
                stream=True
            )

            buffer = ""
            for line in response.iter_lines(decode_unicode=True):
                if line.strip() == "":
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                try:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    buffer += token
                    yield token
                except Exception as e:
                    print("Error parsing chunk:", e)
                    continue

            # Save final summary
            entry.summary = buffer.strip()
            entry.save()

        except Exception as e:
            yield "\n[Error generating summary]"

    return StreamingHttpResponse(generate(), content_type="text/plain")
