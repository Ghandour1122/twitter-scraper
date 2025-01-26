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



def get_posts_commenters(id, headers, folder, count=20):
    conn = http.client.HTTPSConnection("twitter-x.p.rapidapi.com")
    endpoint = f"/comments?pid={id}&count={count}"
    next_cursor = None
    commenters = []
    ids_checker = set()
    i = 0

    while True:
        print(f"Scraped {i} unique users so far.")
        if next_cursor:
            endpoint = f"/comments?pid={id}&count={count}&cursor={next_cursor}"
        
        try:
            conn.request("GET", endpoint, headers=headers)
            res = conn.getresponse()
            data = res.read()
            response = json.loads(data.decode("utf-8"))
            valid_entries = 0

            if response and "result" in response and "instructions" in response["result"]:
                instructions = response["result"]["instructions"]
                for instruction in instructions:
                    if instruction and "entries" in instruction:
                        for entry in instruction["entries"]:
                            if "content" in entry :
                                if "items" in entry["content"]:
                                    for item in  entry["content"]["items"]:
                                        item_content = item["item"]["itemContent"]
                                        if "tweet_results" in item_content:
                                            tweet_data = item_content["tweet_results"]["result"]
                                            legacy_data = tweet_data["legacy"]
                                            id_of_comment = legacy_data["id_str"]
                                            if id_of_comment in ids_checker:
                                                print('scraped before')
                                                continue
                                            
                                            ids_checker.add(id_of_comment)
                                            valid_entries += 1
                                            
                                            core_data = tweet_data["core"]["user_results"]['result']
                                            legacy_needed = core_data['legacy']
                                            commenters.append({
                                                "username": legacy_needed["screen_name"],
                                                "name": legacy_needed["name"],
                                                "id": core_data["rest_id"],
                                                "followers_count": legacy_needed["followers_count"]
                                            })
                                            if int(legacy_needed["followers_count"]) >= 800:
                                                file_path = f"{folder}/tweet_commenters_{id}_data.csv"
                                                file_exists = os.path.isfile(file_path)
                                                with open(file_path, 'a', encoding="utf-8", newline="") as append_file:
                                                    append_writer = csv.DictWriter(append_file, fieldnames=["username", "name", "id", "followers_count"])
                                                    if not file_exists:
                                                        append_writer.writeheader()
                                                    append_writer.writerow({
                                                        "username": legacy_needed["screen_name"],
                                                        "name": legacy_needed["name"],
                                                        "id": core_data["rest_id"],
                                                        "followers_count": legacy_needed["followers_count"]
                                                    })
                                            
                                            i += 1
        except Exception as e:
            print(f"Error: {e}")
            break

        next_cursor = None
        try:
            next_cursor = response['cursor']['bottom']
        except Exception as e:
            print(f"Error fetching next cursor: {e}")

        if not next_cursor or valid_entries == 0:
            print(f"No next cursor or no valid entries found.")
            break

    conn.close()
    return commenters


def get_posts_quotes(id,headers,folder,count=20):
    # it doesnt get the number we want it just returns 20 in all ways shity api
    conn = http.client.HTTPSConnection("twitter-x.p.rapidapi.com")
    endpoint = f"/quotes?pid={id}&count=40"
    next_cursor = None
    tweet_ids = []
    tweets = []
    queters=[]
    ids_checker=set()
    i = 0

    while True:
        print(f"Scraped {i} unique users so far.")
        if next_cursor:
            endpoint = f"/quotes?pid={id}&count=20&cursor={next_cursor}"
        
        conn.request("GET", endpoint, headers=headers)
        res = conn.getresponse()
        data = res.read()
        response = json.loads(data.decode("utf-8"))
        valid_entries = 0
        try:
         if response and "result" in response and "timeline" in response["result"]:

            instructions = response["result"]["timeline"]["instructions"]
            for instruction in instructions:
                if instruction["type"] == "TimelineAddEntries":
                    for entry in instruction["entries"]:
                        if "content" in entry and "itemContent" in entry["content"]:
                            item_content = entry["content"]["itemContent"]
                            if "tweet_results" in item_content:
                                tweet_data = item_content["tweet_results"]["result"]
                                legacy_data = tweet_data["legacy"]

                                # Check if it's a retweet
                                is_retweet = "retweeted_status_result" in tweet_data
                                is_quote = legacy_data.get("is_quote_status", False)
                                id_of_tweet=legacy_data["id_str"]
                                if id_of_tweet in ids_checker:
                                    print('scraped before')
                                    continue
                                        
                                ids_checker.add(id_of_tweet)
                                valid_entries += 1
                                tweets.append({
                                    "tweet_id": legacy_data["id_str"],
                                    "text": legacy_data["full_text"],
                                    "retweet_count": legacy_data["retweet_count"],
                                    "favorite_count": legacy_data["favorite_count"],
                                    "language": legacy_data["lang"],
                                    "is_retweet": is_retweet,
                                    "is_quote": is_quote
                                })
                                tweet_ids.append(legacy_data["id_str"])
                                core_data=tweet_data["core"]["user_results"]['result']
                                legacy_needed=core_data['legacy']
                                queters.append({
                                            "username": legacy_needed["screen_name"],
                                            "name": legacy_needed["name"],
                                            "id": core_data["rest_id"],
                                            "followers_count": legacy_needed["followers_count"]
                                        })
                                if int(legacy_needed["followers_count"]) >= 800:
                                        file_path = f"{folder}/tweet_quoters_{id}_data.csv"
                                        file_exists = os.path.isfile(file_path)
                                        with open(file_path, 'a', encoding="utf-8", newline="") as append_file:
                                            append_writer = csv.DictWriter(append_file, fieldnames=["username", "name", "id", "followers_count"])
                                            # Write the header only if the file does not exist
                                            if not file_exists:
                                                append_writer.writeheader()

                                            # Write the data
                                            append_writer.writerow({
                                                "username": legacy_needed["screen_name"],
                                                "name": legacy_needed["name"],
                                                "id": core_data["rest_id"],
                                                "followers_count": legacy_needed["followers_count"]
                                            })
                                
                                i+=1
        except Exception as e :
            print(e)
        next_cursor = None
        try:
            next_cursor=response['cursor']['bottom']
            # print('next_cursor',next_cursor)
        except Exception as e :
            print(e)
        if not next_cursor or valid_entries == 0:
            print(f"No next cursor or no valid entries found.") # Response: {response}
            break        
    conn.close()
    return tweets, tweet_ids,queters

def process_retweeters(tweet_id, username, headers):
    folder = username or tweet_id
    os.makedirs(folder, exist_ok=True)
    
    retweeters = fetch_all_retweeters(tweet_id, headers, folder)
    
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith('tweet') and f.endswith('.csv')]
    
    if files:
        try:
            combined_df = pd.concat([pd.read_csv(file) for file in files], ignore_index=True)
            output_file = os.path.join(folder, f"combined_retweeters_{username or tweet_id}.csv")
            combined_df.to_csv(output_file, index=False)
            return output_file, retweeters
        except Exception:
            return None, retweeters
    
    return None, retweeters

def process_comments(tweet_id, username, headers):
    folder = username or tweet_id
    os.makedirs(folder, exist_ok=True)
    
    commenters = get_posts_commenters(tweet_id, headers, folder)
    
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith('tweet_commenters') and f.endswith('.csv')]
    
    if files:
        try:
            combined_df = pd.concat([pd.read_csv(file) for file in files], ignore_index=True)
            output_file = os.path.join(folder, f"combined_commenters_{username or tweet_id}.csv")
            combined_df.to_csv(output_file, index=False)
            return output_file, commenters
        except Exception:
            return None, commenters
    
    return None, commenters

def process_quotes(tweet_id, username, headers):
    folder = username or tweet_id
    os.makedirs(folder, exist_ok=True)
    
    tweets, tweet_ids, quoters = get_posts_quotes(tweet_id, headers, folder)
    
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith('tweet_quoters') and f.endswith('.csv')]
    
    if files:
        try:
            combined_df = pd.concat([pd.read_csv(file) for file in files], ignore_index=True)
            output_file = os.path.join(folder, f"combined_quoters_{username or tweet_id}.csv")
            combined_df.to_csv(output_file, index=False)
            return output_file, quoters
        except Exception:
            return None, quoters
    
    return None, quoters


def combine_all_data(folder, username_or_tweet_id):
    """Combine retweeters, commenters, and quoters into a single file."""
    combined_files = [
        os.path.join(folder, f"combined_retweeters_{username_or_tweet_id}.csv"),
        os.path.join(folder, f"combined_commenters_{username_or_tweet_id}.csv"),
        os.path.join(folder, f"combined_quoters_{username_or_tweet_id}.csv")
    ]
    
    if all(os.path.exists(file) for file in combined_files):
        try:
            combined_df = pd.concat([pd.read_csv(file) for file in combined_files], ignore_index=True)
            # Remove duplicates based on 'id'
            combined_df.drop_duplicates(subset=['id'], inplace=True)
            output_file = os.path.join(folder, f"combined_all_data_{username_or_tweet_id}.csv")
            combined_df.to_csv(output_file, index=False)
            return output_file
        except Exception as e:
            print(f"Error combining data: {e}")
            return None
    return None