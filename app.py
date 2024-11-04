from flask import Flask, jsonify, request, render_template
import requests
import os
from dotenv import load_dotenv
from groq import Groq
import re
from transformers import GPT2TokenizerFast
from datetime import datetime, timedelta
from googleapiclient.discovery import build

app = Flask(__name__)

load_dotenv() # Load environment variables from .env file

tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
YOUTUBE_API_KEY = os.getenv("TUBE_API_KEY")
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
GROQ_TOKEN_LIMIT = 1024

@app.route('/video_details', methods=['GET'])
def get_video_details():
    video_id = request.args.get('video_id')
    if not video_id:
        return jsonify({"error": "Please provide a video ID"}), 400

    params = {
        'key': YOUTUBE_API_KEY,
        'part': 'snippet,contentDetails,statistics',
        'id': video_id
    }
    response = requests.get("https://www.googleapis.com/youtube/v3/videos", params=params)

    if response.status_code == 200:
        video_data = response.json().get('items', [])[0]
        video_info = {
            "title": video_data["snippet"]["title"],
            "description": video_data["snippet"]["description"],
            "channel_title": video_data["snippet"]["channelTitle"],
            "published_at": video_data["snippet"]["publishedAt"],
            "view_count": video_data["statistics"]["viewCount"],
            "like_count": video_data["statistics"].get("likeCount", "N/A"),
            "comment_count": video_data["statistics"]["commentCount"]
        }
        return jsonify(video_info)
    else:
        return jsonify({"error": "Failed to fetch video details"}), response.status_code

@app.route('/channel_details', methods=['GET'])
def get_channel_details():
    channel_id = request.args.get('channel_id')
    if not channel_id:
        return jsonify({"error": "Please provide a channel ID"}), 400

    params = {
        'key': YOUTUBE_API_KEY,
        'part': 'snippet,statistics',
        'id': channel_id
    }
    response = requests.get("https://www.googleapis.com/youtube/v3/channels", params=params)

    if response.status_code == 200:
        channel_data = response.json().get('items', [])[0]
        channel_info = {
            "title": channel_data["snippet"]["title"],
            "description": channel_data["snippet"]["description"],
            "published_at": channel_data["snippet"]["publishedAt"],
            "subscriber_count": channel_data["statistics"]["subscriberCount"],
            "video_count": channel_data["statistics"]["videoCount"]
        }
        return jsonify(channel_info)
    else:
        return jsonify({"error": "Failed to fetch channel details"}), response.status_code

@app.route('/comments', methods=['GET'])
def get_comments():
    # Get video_id from the request query parameters
    video_id = request.args.get('video_id')
    if not video_id:
        return jsonify({"error": "Please provide a video ID"}), 400

    # Define parameters for the API request to fetch comments
    params = {
        'key': YOUTUBE_API_KEY,
        'part': 'snippet',
        'videoId': video_id,
        'maxResults': 30  # Limit the results to the top 10 comments for simplicity
    }

    # Make the API request to get comments
    response = requests.get(YOUTUBE_COMMENTS_URL, params=params)

    # Check if the response was successful
    if response.status_code == 200:
        data = response.json()
        comments = []
        
        # Extract relevant information from each comment
        for item in data.get('items', []):
            comment = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "author": comment["authorDisplayName"],
                "text": comment["textDisplay"],
                "like_count": comment["likeCount"],
                "published_at": comment["publishedAt"]
            })

        # Return the comments as a JSON response
        return jsonify(comments)
    else:
        # Handle errors if the API request failed
        return jsonify({"error": "Failed to fetch comments"}), response.status_code

@app.route('/download_comments', methods=['GET'])
def download_comments():
    video_id = request.args.get('video_id')
    if not video_id:
        return jsonify({"error": "Please provide a video ID"}), 400

    params = {
        'key': YOUTUBE_API_KEY,
        'part': 'snippet',
        'videoId': video_id,
        'maxResults': 100  # Fetch a large number if needed
    }

    response = requests.get(YOUTUBE_COMMENTS_URL, params=params)
    if response.status_code == 200:
        data = response.json()
        comments = []
        for item in data.get('items', []):
            comment = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "author": comment["authorDisplayName"],
                "text": comment["textDisplay"],
                "like_count": comment["likeCount"],
                "published_at": comment["publishedAt"]
            })

        # Write comments to CSV
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=["author", "text", "like_count", "published_at"])
        writer.writeheader()
        writer.writerows(comments)
        output.seek(0)

        return send_file(output, mimetype='text/csv', as_attachment=True, download_name=f"{video_id}_comments.csv")
    else:
        return jsonify({"error": "Failed to fetch comments"}), response.status_code

@app.route('/oauth2callback')
def oauth2callback():
    # Here, you will handle the authorization code that Google sends back
    return "OAuth flow completed"

def calculate_total_tokens(comments):
    """Calculate the approximate total token count for a list of comments."""
    combined_text = " ".join(comments)
    tokenized_text = tokenizer.encode(combined_text)
    return len(tokenized_text)

# Example usage
comments_text = ["This is a comment.", "Here's another comment!"]
total_tokens = calculate_total_tokens(comments_text)
print(f"Total tokens: {total_tokens}")


def fetch_recent_comments_text(video_id, max_comments=60):
    """Fetch up to 60 top-level comments from a YouTube video, limited to comments from the past 24 hours."""
    comments_data = []
    page_token = None
    last_day = datetime.utcnow() - timedelta(days=1)  # Define the time limit for 24 hours ago

    while len(comments_data) < max_comments:
        params = {
            'key': YOUTUBE_API_KEY,
            'part': 'snippet',
            'videoId': video_id,
            'maxResults': min(50, max_comments - len(comments_data)),  # Get up to 50 comments per request
            'pageToken': page_token
        }

        response = requests.get(YOUTUBE_COMMENTS_URL, params=params)
        if response.status_code != 200:
            return None

        data = response.json()
        for item in data.get('items', []):
            comment_snippet = item["snippet"]["topLevelComment"]["snippet"]
            comment_text = comment_snippet["textDisplay"]
            author_name = comment_snippet["authorDisplayName"]
            published_at = datetime.strptime(comment_snippet["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")

            # Only add comments from the last 24 hours
            if published_at >= last_day:
                if "<a href=" in comment_text or len(comment_text) > 500:
                    continue

                # Clean up the comment text
                cleaned_comment_text = clean_comment_text(comment_text)
                
                # Append both author name and cleaned comment text
                comments_data.append({
                    "author": author_name,
                    "text": cleaned_comment_text
                })

                if len(comments_data) >= max_comments:
                    break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return comments_data[:max_comments]

def clean_comment_text(comment):
    """Clean up each comment by removing extra newlines and whitespace."""
    cleaned_comment = re.sub(r'\s+', ' ', comment).strip()
    return cleaned_comment

def calculate_total_tokens(comments_text):
    """Calculate the total token count for the combined comments."""
    combined_text = " ".join(comments_text)
    tokenized_text = tokenizer.encode(combined_text)
    return len(tokenized_text)

def rewrite_combined_comments(comments_data):
    """Rewrite comments into a single cohesive summary, chunking if necessary."""
    chunked_responses = []
    chunk = []
    chunk_tokens = 0

    for comment in comments_data:
        comment_text = comment["text"]
        comment_tokens = len(tokenizer.encode(comment_text))
        
        # Check if the current chunk exceeds the token limit
        if chunk_tokens + comment_tokens + 100 > GROQ_TOKEN_LIMIT:
            chunked_responses.append(process_with_groq(chunk))
            chunk = []
            chunk_tokens = 0

        chunk.append(comment)
        chunk_tokens += comment_tokens

    if chunk:
        chunked_responses.append(process_with_groq(chunk))

    # Combine all chunked responses
    combined_summary = " ".join(chunked_responses)
    return combined_summary

def process_with_groq(comments_chunk):
    """Send a chunk of comments to Groq API and return the cohesive summary."""
    system_message = {
        "role": "system",
        "content": (
            "You will receive a series of user comments along with their authors. "
            "Combine all these comments to write a single cohesive essay summarizing the main points. "
            "Focus on creating a unified response that captures the collective opinions and themes."
        )
    }

    # Include author in each user message
    user_messages = [
        {"role": "user", "content": f"{comment['author']} says: {comment['text']}"}
        for comment in comments_chunk
    ]
    messages = [system_message] + user_messages

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # Calculate available tokens
    input_tokens = sum(len(tokenizer.encode(msg["content"])) for msg in messages)
    max_response_tokens = GROQ_TOKEN_LIMIT - input_tokens
    max_response_tokens = max(1, min(max_response_tokens, 500))  # Ensure a positive, reasonable limit

    payload = {
        "model": "llama3-8b-8192",
        "messages": messages,
        "max_tokens": max_response_tokens
    }

    response = requests.post(GROQ_API_URL, json=payload, headers=headers)
    if response.status_code == 200:
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    else:
        return f"Error processing with Groq: {response.status_code} - {response.text}"

@app.route('/display', methods=['GET'])
def display_rewrite():
    video_id = request.args.get('video_id')
    if not video_id:
        return render_template("result.html", error="Please provide a video ID")

    # Fetch recent comments with authors using the correct function
    comments_data = fetch_recent_comments_text(video_id)
    
    # Debugging statements to inspect the video ID and comments data
    print("Video ID:", video_id)
    print("Comments Data:", comments_data)  # This will show the fetched comments for inspection

    if comments_data is None:
        return render_template("result.html", error="Failed to fetch comments")

    cohesive_comment = rewrite_combined_comments(comments_data)
    
    # Render the output to an HTML template
    return render_template("result.html", original_comments=comments_data, cohesive_comment=cohesive_comment)

def search_youtube_videos(query, max_results=10):
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    search_response = youtube.search().list(
        q=query,
        part='snippet',
        type='video',
        maxResults=max_results
    ).execute()
    return search_response.get('items', [])

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        query = request.form.get('query')
        if query:
            videos = search_youtube_videos(query)
            return render_template('results.html', videos=videos)
    return render_template('search.html')


if __name__ == '__main__':
    app.run(debug=True)
