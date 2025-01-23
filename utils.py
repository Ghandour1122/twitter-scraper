import re
import http.client
import json
import os
import csv
import pandas as pd

def extract_tweet_id(url):
    """Extract tweet ID from Twitter/X URL."""
    match = re.search(r"status/(\d+)", url)
    return match.group(1) if match else None

def get_user_or_tweet_data(input_str):
    """Determine if input is URL or username."""
    if input_str.startswith(("http://", "https://")):
        tweet_id = extract_tweet_id(input_str)
        return {
            "type": "tweet" if tweet_id else "invalid_url",
            "data": tweet_id
        }
    return {
        "type": "username",
        "data": input_str.strip("@")
    }

def make_request(endpoint, headers):
    """Make API request to Twitter/X."""
    conn = http.client.HTTPSConnection("twitter241.p.rapidapi.com")
    conn.request("GET", endpoint, headers=headers)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    
    return json.loads(data.decode("utf-8")) if res.status == 200 else None

def get_rest_id(username, headers):
    """Get user's REST ID."""
    endpoint = f"/user?username={username}"
    response_data = make_request(endpoint, headers)
    return response_data['result']['data']['user']['result']['rest_id'] if response_data else None

def get_last_10_tweets(id, headers, count=10):
    """Fetch last 10 tweets for a user."""
    endpoint = f"/user-tweets?user={id}&count={count}"
    response = make_request(endpoint, headers)
    
    if not response or "result" not in response or "timeline" not in response["result"]:
        return [], []
    
    tweets, tweet_ids = [], []
    instructions = response["result"]["timeline"]["instructions"]
    i=0
    for instruction in instructions:
        if instruction["type"] == "TimelineAddEntries":
            for entry in instruction["entries"]:
                if "content" in entry and "itemContent" in entry["content"]:
                    item_content = entry["content"]["itemContent"]
                    if "tweet_results" in item_content:
                        tweet_data = item_content["tweet_results"]["result"]
                        legacy_data = tweet_data["legacy"]

                        tweets.append({
                            "tweet_id": legacy_data["id_str"],
                            "text": legacy_data["full_text"],
                            "retweet_count": legacy_data["retweet_count"],
                            "favorite_count": legacy_data["favorite_count"],
                            "language": legacy_data["lang"],
                            "is_retweet": "retweeted_status_result" in tweet_data,
                            "is_quote": legacy_data.get("is_quote_status", False)
                        })
                        tweet_ids.append(legacy_data["id_str"])
        if i>=10 :
            break
        i+=1
    return tweets, tweet_ids

def fetch_all_retweeters(tweet_id, headers, folder):
    """Fetch retweeters for a specific tweet."""
    conn = http.client.HTTPSConnection("twitter-x.p.rapidapi.com")
    endpoint = f"/retweets?pid={tweet_id}&count=40"
    all_retweeters, user_ids = [], set()
    next_cursor, i = None, 0

    while True:
        if next_cursor:
            endpoint = f"/retweets?pid={tweet_id}&count=100&cursor={next_cursor}"
        
        conn.request("GET", endpoint, headers=headers)
        res = conn.getresponse()
        response = json.loads(res.read().decode("utf-8"))
        
        try:
            instructions = response["result"]["timeline"]["instructions"]
            valid_entries = 0
            for instruction in instructions:
                if instruction["type"] == "TimelineAddEntries":
                    for entry in instruction["entries"]:
                        if "content" in entry and "itemContent" in entry["content"]:
                            item_content = entry["content"]["itemContent"]
                            if "user_results" in item_content:
                                try:
                                    user_data = item_content["user_results"]["result"]
                                    legacy_data = user_data["legacy"]
                                    user_id = user_data["rest_id"]
                                    
                                    if user_id in user_ids:
                                        continue
                                    
                                    user_ids.add(user_id)
                                    retweeter_info = {
                                        "username": legacy_data["screen_name"],
                                        "name": legacy_data["name"],
                                        "id": user_id,
                                        "followers_count": legacy_data["followers_count"]
                                    }
                                    all_retweeters.append(retweeter_info)
                                    valid_entries += 1

                                    if int(legacy_data["followers_count"]) >= 800:
                                        file_path = os.path.join(folder, f"tweet_{tweet_id}_data.csv")
                                        file_exists = os.path.isfile(file_path)
                                        
                                        with open(file_path, 'a', encoding="utf-8", newline="") as append_file:
                                            append_writer = csv.DictWriter(append_file, fieldnames=["username", "name", "id", "followers_count"])
                                            if not file_exists:
                                                append_writer.writeheader()
                                            append_writer.writerow(retweeter_info)

                                except KeyError:
                                    pass
                                i += 1
        except Exception:
            break

        try:
            next_cursor = response['cursor']['bottom']
        except Exception:
            break

        if not next_cursor or valid_entries == 0:
            break

    conn.close()
    return all_retweeters

def process_retweeters(tweet_id, username, headers):
    """Process retweeters and combine results."""
    folder = username or tweet_id
    os.makedirs(folder, exist_ok=True)
    
    retweeters = fetch_all_retweeters(tweet_id, headers, folder)
    
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith('tweet') and f.endswith('.csv')]
    
    if files:
        try:
            combined_df = pd.concat([pd.read_csv(file) for file in files], ignore_index=True)
            output_file = os.path.join(folder, f"combined_data_{username or tweet_id}.csv")
            combined_df.to_csv(output_file, index=False)
            return output_file, retweeters
        except Exception:
            return None, retweeters
    
    return None, retweeters