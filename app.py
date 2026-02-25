import os
import json
import tempfile
from flask import Flask, request, jsonify
import yt_dlp
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
API_SECRET = os.environ.get("API_SECRET", "changeme")

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/extract', methods=['POST'])
def extract():
    auth = request.headers.get('X-API-Key')
    if auth != API_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        # Step 1: Get metadata and transcript
        info = {}
        transcript = ''

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, 'audio.mp3')

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(tmpdir, 'audio.%(ext)s'),
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '64',
                }],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if os.path.exists(audio_path):
                with open(audio_path, 'rb') as f:
                    result = client.audio.transcriptions.create(
                        model='whisper-1',
                        file=f
                    )
                transcript = result.text

        title = info.get('title', '')
        description = info.get('description', '')
        thumbnail = info.get('thumbnail', '')

        context = f"Title: {title}\n\nCaption/Description: {description}\n\nSpoken audio transcript: {transcript}"

        prompt = f"""Extract the recipe from this TikTok video. Return a JSON object with:
- name (string)
- description (one sentence, string)
- ingredients (list of strings)
- steps (list of strings)
- prep_time (string or null)
- cook_time (string or null)
- servings (string or null)

If no recipe is found, return {{"error": "No recipe found"}}.
Return only valid JSON, no markdown.

Video info:
{context}"""

        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            response_format={'type': 'json_object'}
        )

        recipe = json.loads(response.choices[0].message.content)
        recipe['thumbnail_url'] = thumbnail
        recipe['source_url'] = url
        recipe['video_title'] = title

        return jsonify(recipe)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
