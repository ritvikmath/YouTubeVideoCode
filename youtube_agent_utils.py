# imports
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
import google.oauth2.credentials
from googleapiclient.http import MediaFileUpload
import urllib.request 
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone, timedelta
import pytz
import pandas as pd
from time import sleep
import seaborn as sns
from openai import OpenAI
import pandas as pd
import re
from datetime import datetime

OPEN_AI_API_KEY = "SET_OPEN_AI_API_KEY_HERE"
CHANNEL_ID = 'SET_YOUR_YOUTUBE_CHANNEL_ID_HERE'

def get_authenticated_youtube_api():
    flow = InstalledAppFlow.from_client_secrets_file(
        '/path/to/your/client_secret.json',
        scopes=['https://www.googleapis.com/auth/youtube']
    )

    # If credentials don't exist, open a web browser to authenticate
    if not os.path.exists('credentials.json'):
        credentials = flow.run_local_server(port=0)
        with open('credentials.json', 'w') as credentials_file:
            credentials_file.write(credentials.to_json())
    else:
        credentials = google.oauth2.credentials.Credentials.from_authorized_user_file('credentials.json')

    youtube = build("youtube", "v3", credentials=credentials)
    return youtube

def get_views_snippet(youtube, video_id):
    video_info = youtube.videos().list(
        id=video_id,
        part='snippet,statistics'
    ).execute()
    views = video_info['items'][0]['statistics']['viewCount']
    snippet = video_info['items'][0]['snippet']
    return int(views), snippet

def update_video_title(youtube, video_id, new_title):
    views, snippet = get_views_snippet(youtube, video_id)
    snippet['title'] = new_title
    youtube.videos().update(
        part="snippet",
        body={
          "id": f"{video_id}",
          "snippet": snippet
        }
    ).execute()

def get_last_n_videos_with_views(youtube, n):
    """
    Fetch the last 10 videos from a YouTube channel with their view counts.
    
    Args:
        youtube: Authenticated YouTube API client.
        
    Returns:
        A list of dictionaries containing video titles, URLs, and view counts.
    """
    try:
        # Step 1: Fetch the last n videos using `search.list`
        search_request = youtube.search().list(
            part="snippet",
            channelId=CHANNEL_ID,
            maxResults=n,
            order="date",
            type="video"
        )
        search_response = search_request.execute()

        # Step 2: Extract video IDs
        video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]

        if not video_ids:
            print("No videos found for the specified channel.")
            return []

        # Step 3: Fetch video statistics using `videos.list`
        videos_request = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(video_ids)
        )
        videos_response = videos_request.execute()

        # Step 4: Process the response
        videos = []
        for item in videos_response.get("items", []):
            title = item["snippet"]["title"]
            publishedAt = datetime.strptime(item["snippet"]["publishedAt"], '%Y-%m-%dT%H:%M:%SZ')
            utc_datetime = publishedAt.replace(tzinfo=timezone.utc)
            pdt_datetime = utc_datetime.astimezone(pytz.timezone('America/Los_Angeles'))
            delta = (datetime.now(pytz.timezone('America/Los_Angeles')) - pdt_datetime).total_seconds()
            video_id = item["id"]
            view_count = int(item["statistics"].get("viewCount", "0"))
            like_count = int(item["statistics"].get("likeCount", "0"))
            dislike_count = int(item["statistics"].get("dislikeCount", "0"))
            comment_count = int(item["statistics"].get("commentCount", "0"))
            views_per_day = view_count / (delta / 3600 / 24)
            videos.append({
                "title": title,
                "publishedAt": pdt_datetime,
                "publishedDaysAgo": delta / 3600 / 24,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "views": view_count,
                "views_per_day": views_per_day,
                "likes": like_count,
                "dislikes": dislike_count,
                "like_dislike_ratio": like_count / dislike_count,
                "comments": comment_count
                
            })

        return videos

    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def get_openai_client():
	client = OpenAI(api_key=OPEN_AI_API_KEY)
	return client

def chat(client, messages):
    completion = client.chat.completions.create(
        model="gpt-4o",
        store=True,
        messages=messages,
        temperature=0
    )
    return completion.choices[0].message.content


def get_messages(last_n_videos, user_input):
	last_n = len(last_n_videos)
	messages = []
	messages.append(
	    {
		    'role': 'system', 
		    'content': 
		        f"""
		        You are an assistant who is an expert in generating video titles for YouTube videos which are likely to get lots of engagement.
		        You will be provided below with information about the last {last_n} videos posted by the YouTube channel ritvikmath.
		        These videos will be in the VIDEO_DATA section at the end of this prompt.
		        This channel focusses on data science, statistics, and mathematics educational videos.
		        Each item in the provided list below has the following schema:
		        - title: the title of the video
		        - publishedAt: the datetime when this video was first published
		        - url: the url of the video
		        - views: the current number of views of the video
		        - views_per_day: the number of views this video got per day so far
		        - likes: the number of likes the video got
		        - dislikes: the number of dislikes the video got
		        - like_dislike_ratio: the ratio of number of likes to number of dislikes
		        - comments: the number of dislikes the video got
		        The user will provide a description of what the a new video is about.
		        Your job is to use the strongly-performing videos from the provided data to suggest a strong title for this new video.
		        By "strong", we mean a video title that is more likely to get engagement.
		        Please output the new title as well as your reasoning in the following json format:
		        {{
		          new_title: the suggested new title,
		          reasoning: the reasoning for this new title
		        }}
		        The reasoning should reference one or more videos provided in the data above.
		        The reasoning should be 75 words or fewer.
		        Return the output as raw JSON without any Markdown formatting or additional text.
		        VIDEO_DATA:
		        {last_n_videos}
		        """
	    }
	)
	messages.append({"role": "user", "content": user_input})
	return messages

