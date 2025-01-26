from flask import Flask, render_template, request, send_file, Response
from utils import (
    get_user_or_tweet_data, 
    get_rest_id, 
    get_last_10_tweets, 
    process_retweeters,
    process_quotes,
    process_comments,
    combine_all_data
)
import os
import json

app = Flask(__name__)

# Replace with your actual RapidAPI key
HEADERS = {
    'x-rapidapi-key': os.getenv('RAPIDAPI_KEY'),
    'x-rapidapi-host': "twitter241.p.rapidapi.com"
}


@app.route('/')
def index():
    return render_template('index.html')

def generate_scraping_log(user_input):
    """Generator to stream scraping progress to client."""
    # Capture and stream progress
    log_entries = []
    
    try:
        # Identify input type
        log_entries.append({"status": "info", "message": f"Processing input: {user_input}"})
        result = get_user_or_tweet_data(user_input)
        
        if result['type'] == 'invalid_url':
            log_entries.append({"status": "error", "message": "Invalid URL or username"})
            yield f"data: {json.dumps({'status': 'error', 'message': 'Invalid URL or username'})}\n\n"
            return
        
        # Determine username or tweet ID
        if result['type'] == 'username':
            username = result['data']
            log_entries.append({"status": "info", "message": f"Fetching data for username: {username}"})
            
            # Get REST ID
            rest_id = get_rest_id(username, HEADERS)
            if not rest_id:
                log_entries.append({"status": "error", "message": "Could not fetch user REST ID"})
                yield f"data: {json.dumps({'status': 'error', 'message': 'Could not fetch user REST ID'})}\n\n"
                return
            
            log_entries.append({"status": "info", "message": f"Retrieved REST ID: {rest_id}"})
            
            # Get tweets
            tweets, tweet_ids = get_last_10_tweets(rest_id, HEADERS)
            log_entries.append({"status": "info", "message": f"Found {len(tweets)} tweets"})
        else:
            username = None
            tweet_ids = [result['data']]
            log_entries.append({"status": "info", "message": f"Processing single tweet ID: {tweet_ids[0]}"})
        
        # Ensure folder exists
        folder = username or tweet_ids[0]
        os.makedirs(folder, exist_ok=True)
        
        # Process each tweet
        all_retweeters = []
        for tweet_id in tweet_ids:
            log_entries.append({"status": "info", "message": f"Fetching retweeters for tweet: {tweet_id}"})
            
            # Process retweeters
            output_file, retweeters = process_retweeters(tweet_id, username, HEADERS)
            
            log_entries.append({
                "status": "info", 
                "message": f"Found {len(retweeters)} retweeters for tweet {tweet_id}",
                "output_file": output_file
            })
            
            all_retweeters.extend(retweeters)
            
            # Stream progress
            yield f"data: {json.dumps(log_entries[-1])}\n\n"
            log_entries.append({"status": "info", "message": f"Fetching comments for tweet: {tweet_id}"})
            
            # Process retweeters
            output_file_commenters, commenters = process_comments(tweet_id, username, HEADERS)
            
            log_entries.append({
                "status": "info", 
                "message": f"Found {len(commenters)} commeters for tweet {tweet_id}",
                "output_file": output_file_commenters
            })
            
            all_retweeters.extend(commenters)
            
            # Stream progress
            yield f"data: {json.dumps(log_entries[-1])}\n\n"
            log_entries.append({"status": "info", "message": f"Fetching quoters for tweet: {tweet_id}"})
            
            # Process retweeters
            output_file_quoters, quoters = process_quotes(tweet_id, username, HEADERS)
            
            log_entries.append({
                "status": "info", 
                "message": f"Found {len(quoters)} quoters for tweet {tweet_id}",
                "output_file": output_file_quoters
            })
            
            all_retweeters.extend(quoters)
            
            # Stream progress
            yield f"data: {json.dumps(log_entries[-1])}\n\n"
        
        # Find CSV files
        csv_files = [
            f for f in os.listdir(folder) 
            if f.startswith(('tweet', 'combined')) and f.endswith('.csv')
        ]
        output_files = [os.path.join(folder, f) for f in csv_files]
        
        log_entries.append({
            "status": "complete", 
            "message": f"Scraping complete. Generated {len(output_files)} CSV files",
            "output_files": output_files,
            "total_retweeters": len(all_retweeters),
            "retwitters":all_retweeters
        })
        
        yield f"data: {json.dumps(log_entries[-1])}\n\n"
        # Combine all data into a single file
        combined_file = combine_all_data(folder, username or tweet_ids[0])
        if combined_file:
            log_entries.append({
                "status": "info",
                "message": f"Combined all data into {combined_file}"
            })
            yield f"data: {json.dumps(log_entries[-1])}\n\n"

        # Final log entry
        log_entries.append({
            "status": "complete", 
            "message": f"Scraping complete. Generated {len(output_files)} CSV files",
            "output_files": combined_file,
            "total_retweeters": len(all_retweeters),
            "retweeters": all_retweeters
        })
        yield f"data: {json.dumps(log_entries[-1])}\n\n"
    
    except Exception as e:
        error_entry = {"status": "error", "message": str(e)}
        log_entries.append(error_entry)
        yield f"data: {json.dumps(error_entry)}\n\n"

@app.route('/scrape', methods=['POST'])
def scrape():
    user_input = request.form['input']
    return render_template('results.html', stream_url=f'/stream_scrape?input={user_input}')

@app.route('/stream_scrape')
def stream_scrape():
    user_input = request.args.get('input')
    return Response(generate_scraping_log(user_input), mimetype='text/event-stream')

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)