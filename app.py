from flask import Flask, jsonify, request, render_template
import requests
import os
from dotenv import load_dotenv
from groq import Groq
import re
from transformers import GPT2TokenizerFast

app = Flask(__name__)

load_dotenv() # Load environment variables from .env file

tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
YOUTUBE_API_KEY = os.getenv("TUBE_API_KEY")
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
GROQ_TOKEN_LIMIT = 4096

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


def fetch_multiple_comments_text(video_id, max_comments=60):
    """Fetch up to 60 top-level comments from a YouTube video."""
    comments_text = []
    page_token = None
    while len(comments_text) < max_comments:
        params = {
            'key': YOUTUBE_API_KEY,
            'part': 'snippet',
            'videoId': video_id,
            'maxResults': min(50, max_comments - len(comments_text)),  # Get up to 50 comments per request, within max limit
            'pageToken': page_token
        }

        response = requests.get(YOUTUBE_COMMENTS_URL, params=params)
        if response.status_code != 200:
            return None

        data = response.json()
        for item in data.get('items', []):
            comment_text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]

            # Skip entries with links or metadata patterns
            if "<a href=" in comment_text or len(comment_text) > 500:
                continue
            
            # Clean up the comment
            cleaned_comment_text = clean_comment_text(comment_text)
            comments_text.append(cleaned_comment_text)

            if len(comments_text) >= max_comments:
                break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return comments_text[:max_comments]  # Return up to the number of requested comments

def clean_comment_text(comment):
    """Clean up each comment by removing extra newlines and whitespace."""
    cleaned_comment = re.sub(r'\s+', ' ', comment).strip()
    return cleaned_comment

def calculate_total_tokens(comments_text):
    """Calculate the total token count for the combined comments."""
    combined_text = " ".join(comments_text)
    tokenized_text = tokenizer.encode(combined_text)
    return len(tokenized_text)

def rewrite_combined_comments(comments_text):
    """Rewrite comments into a single cohesive summary, chunking if necessary."""
    total_tokens = calculate_total_tokens(comments_text)

    # Check if total tokens exceed the model's token limit (1024 tokens)
    if total_tokens <= 1024:
        # If within token limit, send all comments as one request
        return process_with_groq(comments_text)
    else:
        # If over the limit, chunk comments and process each chunk separately
        chunked_responses = []
        chunk = []
        chunk_tokens = 0

        for comment in comments_text:
            comment_tokens = len(tokenizer.encode(comment))
            if chunk_tokens + comment_tokens > 1024:
                # Process the current chunk and start a new one
                chunked_responses.append(process_with_groq(chunk))
                chunk = []
                chunk_tokens = 0

            chunk.append(comment)
            chunk_tokens += comment_tokens

        # Process the final chunk
        if chunk:
            chunked_responses.append(process_with_groq(chunk))

        # Combine chunked responses into a final summary
        combined_summary = " ".join(chunked_responses)
        return combined_summary

def process_with_groq(comments_chunk):
    """Send a chunk of comments to Groq API and return the cohesive summary."""
    system_message = {
        "role": "system",
        "content": (
            "Take all these comment and write a short paragraph to replect the information. "
            "combine everything and make it overall view of the sentiment"
        )
    }

    # Create user messages for each comment
    user_messages = [{"role": "user", "content": f"Comment #{i+1}:\n{comment}"} for i, comment in enumerate(comments_chunk)]
    messages = [system_message] + user_messages

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # Send the payload with a slightly higher max_tokens if necessary for more data
    payload = {
        "model": "llama3-8b-8192",
        "messages": messages,
        "max_tokens": 4096  # Adjust this if Groq can handle more tokens
    }

    # Make the request and handle the response
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

    # Fetch comments and process them
    comments_text = fetch_multiple_comments_text(video_id)
    if comments_text is None:
        return render_template("result.html", error="Failed to fetch comments")

    cohesive_comment = rewrite_combined_comments(comments_text)
    
    # Render the output to an HTML template
    return render_template("result.html", original_comments=comments_text, cohesive_comment=cohesive_comment)

if __name__ == '__main__':
    app.run(debug=True)
