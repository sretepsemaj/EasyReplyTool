from flask import Flask, jsonify, request
import requests
import os
from dotenv import load_dotenv
from groq import Groq

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Get the YouTube API key from environment variables
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
YOUTUBE_API_KEY = os.getenv("TUBE_API_KEY")
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

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

def fetch_single_comment_text(video_id):
    """Fetch a single top-level comment from a YouTube video."""
    params = {
        'key': YOUTUBE_API_KEY,
        'part': 'snippet',
        'videoId': video_id,
        'maxResults': 1  # Limit to 1 comment
    }

    response = requests.get(YOUTUBE_COMMENTS_URL, params=params)
    if response.status_code != 200:
        return None

    data = response.json()
    # Extract the text of the first comment, if available
    if data.get('items'):
        comment_text = data['items'][0]["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
        return comment_text
    else:
        return None

def rewrite_comment(comment_text):
    """Send a single comment to Groq API to generate a rewritten or expanded version."""
    if not comment_text:
        return "No comment available to rewrite."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama3-8b-8192",  # Using the specified model
        "messages": [{"role": "user", "content": comment_text}],  # Sending 'messages' format
        "max_tokens": 150  # Adjust as needed
    }

    try:
        response = requests.post(GROQ_API_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            # Extract the rewritten comment text correctly
            full_response = response.json()
            print("Full response from Groq API:", full_response)  # For debugging purposes
            
            # Extract the content from 'message'
            rewritten_text = full_response.get("choices", [{}])[0].get("message", {}).get("content", "Rewrite was successful, but no content was returned.")
            return rewritten_text.strip()
        else:
            # Print the full error response for debugging
            print("Error response:", response.json())
            return f"Failed to rewrite comment: {response.status_code} - {response.json()}"
    except Exception as e:
        return f"Failed to rewrite comment: {str(e)}"


@app.route('/rewrite', methods=['GET'])
def get_rewrite():
    video_id = request.args.get('video_id')
    if not video_id:
        return jsonify({"error": "Please provide a video ID"}), 400

    # Fetch a single comment from the video
    comment_text = fetch_single_comment_text(video_id)
    if comment_text is None:
        return jsonify({"error": "Failed to fetch comment"}), 500

    # Rewrite the comment using Groq API
    rewritten_comment = rewrite_comment(comment_text)
    return jsonify({"original_comment": comment_text, "rewritten_comment": rewritten_comment})

if __name__ == '__main__':
    app.run(debug=True)
