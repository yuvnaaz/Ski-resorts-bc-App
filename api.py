#flask api for content text at the top of the app 
from flask import Flask, jsonify

from flask_cors import CORS
from data2 import scrape_and_save
import json

app = Flask(__name__)
CORS(app) 

@app.route('/')
def index():
    url_to_scrape = 'https://www.onthesnow.com/british-columbia/skireport'  
    # Filename to save the scraped data
    filename_to_save = 'scraped_content.json'

    scrape_and_save(url_to_scrape, filename_to_save)

    with open(filename_to_save, 'r') as json_file:
        scraped_data = json.load(json_file)

    return jsonify(scraped_data)

if __name__ == '__main__':
    app.run(debug=True, port=3000)
