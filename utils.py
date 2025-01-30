import re
import http.client
import json
import os
import csv
import pandas as pd
import urllib.parse
import requests
import time
import zstandard as zstd
import io
import binascii
import gzip               # For gzip decompression
import random

def handle_compressed_response(response,logger):
    """Handle potentially mislabeled zstd compression"""
    # Check magic number for actual zstd compression
    zstd_magic = b'\x28\xb5\x2f\xfd'
    content = response.content
    
    try:
        # First check if it's valid JSON despite zstd header
        try:
            return json.loads(content.decode('utf-8'))
        except UnicodeDecodeError:
            pass
            
        # Verify zstd compression
        if content.startswith(zstd_magic):
            dctx = zstd.ZstdDecompressor()
            return json.loads(dctx.decompress(content))
            
        # Check for gzip fallback
        if content[:2] == b'\x1f\x8b':  # gzip magic number
            return json.loads(gzip.decompress(content))
            
        # Final fallback attempt
        return json.loads(content.decode('utf-8', errors='replace'))
        
    except Exception as e:
        logger.info(f"Raw content (hex): {binascii.hexlify(content[:8])}")
        raise ValueError(f"Failed to decode response: {e}")


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

def fetch_all_retweeters(tweet_id,folder,logger,formated_cookies,x_csrf_token,x_client_uuid,x_client_transaction_id):
    # Step 1: Define base URL and endpoint
    BASE_URL = "https://x.com/i/api/graphql"
    ENDPOINT = "8fXdisbSK0JGESmFrHcp1g/Retweeters"

    features = {
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_enhance_cards_enabled": False
}

# Step 5: Define headers
    headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
    "connection": "keep-alive",
    "content-type": "application/json",
    "cookie":formated_cookies,    
    "host": "x.com",
    "referer": f"https://x.com/solana/status/{tweet_id}/retweets",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "x-client-transaction-id": x_client_transaction_id,
    "x-client-uuid": x_client_uuid,
    "x-csrf-token": x_csrf_token,
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session",
    "x-twitter-client-language": "en"
}
    # Step 2: Define variables and features
    variables = {
        "tweetId": f"{tweet_id}",
        "count": 64,
        "includePromotedContent": True
    }
    all_retweeters = []
    next_cursor = None
    i = 0
    user_ids = set()  # Use a set to avoid duplicates
    while True:
        print(f"Scraped {i} unique users so far.")
        logger.info(f"Scraped {i} unique users so far.")
        if next_cursor:
           variables=  {
            "tweetId": f"{tweet_id}",
            "count": 64,
            "cursor": f"{next_cursor}",
            "includePromotedContent": True
           }
        
        # Step 3: Encode variables and features
        encoded_variables = urllib.parse.urlencode({"variables": json.dumps(variables)})
        encoded_features = urllib.parse.urlencode({"features": json.dumps(features)})
        # Step 4: Construct the full URL
        url = f"{BASE_URL}/{ENDPOINT}?{encoded_variables}&{encoded_features}"
        # Step 6: Make the request
        response = requests.get(url, headers=headers)

        # Step 7: Check the response
        print(f"Status Code:{response.status_code}")
        logger.info(f"Status Code:{response.status_code}")
        logger.info(f"Response Headers: {response.headers}")
        
        if "application/json" in response.headers.get("Content-Type", ""):
            try:
                logger.info("Processing JSON response.")
                # Check for zstd compression
                response_text = response.text
                # Add this to see the actual content structure
                logger.info(f"First 8 bytes (hex): {binascii.hexlify(response.content[:8])}")
                try:
                        response_text = handle_compressed_response(response,logger)
                        # Process response_data here
                except Exception as e:
                        logger.error(f"Final decoding failed: {e}")
                        logger.error(f"First 16 bytes (hex): {binascii.hexlify(response.content[:16])}")
                        return []
                response = response_text
                logger.info("Successfully parsed JSON response.")

                instructions = response["data"]["retweeters_timeline"]["timeline"]["instructions"]
                valid_entries = 0
                logger.info(f"Instructions: {instructions}")
                for instruction in instructions:
                    if instruction["type"] == "TimelineAddEntries":
                        for entry in instruction["entries"]:
                            logger.info(f"Processing Entry: {entry}")

                            if "itemContent" in entry["content"] and "user_results" in entry["content"]["itemContent"]:
                                try:
                                    user_data = entry["content"]["itemContent"]["user_results"]["result"]
                                    legacy_data = user_data["legacy"]
                                    user_id = user_data["rest_id"]

                                    logger.info(f"Processing user: {legacy_data['screen_name']} ({user_id})")

                                    if user_id in user_ids:
                                        logger.info(f"User {user_id} already processed, skipping.")
                                        continue

                                    user_ids.add(user_id)
                                    all_retweeters.append({
                                        "username": legacy_data["screen_name"],
                                        "name": legacy_data["name"],
                                        "id": user_id,
                                        "followers_count": legacy_data["followers_count"]
                                    })
                                    valid_entries += 1
                                    logger.info(f"Added user: {legacy_data['screen_name']} - Followers: {legacy_data['followers_count']}")

                                    if int(legacy_data["followers_count"]) >= 800:
                                        file_path = os.path.join(folder, f"tweet_{tweet_id}_data.csv")
                                        file_exists = os.path.isfile(file_path)
                                        
                                        with open(file_path, 'a', encoding="utf-8", newline="") as append_file:
                                            append_writer = csv.DictWriter(append_file, fieldnames=["username", "name", "id", "followers_count"])
                                            
                                            if not file_exists:
                                                append_writer.writeheader()
                                            
                                            append_writer.writerow({
                                                "username": legacy_data["screen_name"],
                                                "name": legacy_data["name"],
                                                "id": user_id,
                                                "followers_count": legacy_data["followers_count"]
                                            })
                                        
                                        logger.info(f"User {legacy_data['screen_name']} saved to CSV.")

                                except KeyError as e:
                                    logger.error(f"Error processing user: {e}", exc_info=True)
                                i += 1

                # Check if there's a next cursor for pagination
                next_cursor = None
                for instruction in instructions:
                    if instruction["type"] == "TimelineAddEntries":
                        for entry in instruction["entries"]:
                            if entry["content"]["entryType"] == "TimelineTimelineCursor" and entry["content"].get("cursorType") == "Bottom":
                                next_cursor = entry["content"]["value"]
                                logger.info(f"Next cursor found: {next_cursor}")

                # Save the response if there's no next cursor
                if not next_cursor or valid_entries == 0:
                    logger.warning("No next cursor or no valid entries found.")
                    break

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)

        time.sleep(1)


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

def process_retweeters(tweet_id, username, headers,logger):
    folder = username or tweet_id
    os.makedirs(folder, exist_ok=True)
    
    while True:
        processed_accounts = accs_fetcher()
        random_acc=random.choice(processed_accounts)
        x_csrf_token = random_acc['headers']['x-csrf-token']
        x_client_uuid = random_acc['headers']['x-client-uuid']
        x_client_transaction_id = random_acc['headers']['x-client-transaction-id']
        formated_cookies = random_acc['formatted_cookies']
        logger.info(f"acc usernmae {random_acc['username']}")
        if tester(formated_cookies, x_csrf_token, x_client_uuid, x_client_transaction_id) == 200 :
            break
        else:
            logger.info('acc not logged in any more use another one')

    retweeters = fetch_all_retweeters(tweet_id, folder,logger,formated_cookies,x_csrf_token,x_client_uuid,x_client_transaction_id)
    
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

def accs_fetcher():
    def process_account(account):
        """
        Process a single account and format its information including cookies and headers
        """
        account_info = {
            "username": account.get("username"),
            "password": account.get("password"),
            "email": account.get("email"),
            "secondary_password": account.get("secondary_password"),
            "token": account.get("token"),
            "headers": account.get("headers", {}),
            "formatted_cookies": format_cookies_for_header(account.get("cookies", []))
        }
        return account_info

    def format_cookies_for_header(cookies):
        """
        Format cookies list into a header-compatible string, filtering for x.com domain only
        """
        cookie_pairs = []
        for cookie in cookies:
            # Check if the domain contains 'x.com'
            domain = cookie.get('domain', '').lower()
            if 'x.com' in domain or "twitter.com" in domain:
                cookie_pairs.append(f"{cookie['name']}={cookie['value']}")
        return "; ".join(cookie_pairs)

    def extract_accounts_info():
        """
        Securely extract and process account information from Render's Secret File
        """
        secret_path = os.getenv('ACCOUNTS_SECRET_PATH', '/etc/secrets/twitter_accounts.json')
        with open(secret_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        # Process each account
        processed_accounts = []
        for account in data.get("accounts", []):
            processed_account = process_account(account)
            processed_accounts.append(processed_account)
        return processed_accounts

    processed_accounts = extract_accounts_info()
    return processed_accounts


def tester(formated_cookies, x_csrf_token, x_client_uuid, x_client_transaction_id):
    BASE_URL = "https://x.com/i/api/graphql"
    ENDPOINT = "8fXdisbSK0JGESmFrHcp1g/Retweeters"
    variables = {
        "tweetId": "1882807731993870784",
        "count": 5,
        "includePromotedContent": True
    }

    features = {
        "profile_label_improvements_pcf_label_in_post_enabled": True,
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "premium_content_api_read_enabled": False,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
        "responsive_web_grok_analyze_post_followups_enabled": True,
        "responsive_web_jetfuel_frame": False,
        "responsive_web_grok_share_attachment_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_grok_image_annotation_enabled": True,
        "responsive_web_enhance_cards_enabled": False
    }

    encoded_variables = urllib.parse.urlencode(
        {"variables": json.dumps(variables)})
    encoded_features = urllib.parse.urlencode(
        {"features": json.dumps(features)})

    url = f"{BASE_URL}/{ENDPOINT}?{encoded_variables}&{encoded_features}"

    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "connection": "keep-alive",
        "content-type": "application/json",
        "cookie": formated_cookies,
        "host": "x.com",
        "referer": "https://x.com/solana/status/1882807731993870784/retweets",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "x-client-transaction-id": x_client_transaction_id,
        "x-client-uuid": x_client_uuid,
        "x-csrf-token": x_csrf_token,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en"
    }

    response = requests.get(url, headers=headers)
    return response.status_code