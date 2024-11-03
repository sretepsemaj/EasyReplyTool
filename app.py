from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

YOUTUBE_API_KEY = "AIzaSyC8csQoRm0_ENUm2MW9DFTMdaUX4DdrGc0"  # Replace with your actual YouTube Data API Key
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

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
        'maxResults': 10  # Limit the results to the top 10 comments for simplicity
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

@app.route('/oauth2callback')
def oauth2callback():
    # Here, you will handle the authorization code that Google sends back
    return "OAuth flow completed"


if __name__ == '__main__':
    app.run(debug=True)

