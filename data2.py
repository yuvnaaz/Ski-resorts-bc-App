import requests
from bs4 import BeautifulSoup
import json

def fetch_page(url):
    """Fetches and returns the HTML content of the given URL."""
    response = requests.get(url)
    response.raise_for_status()  # Raise an error for bad status codes
    return response.content

def extract_content(content):
    """Extracts text content from the specific div class."""
    soup = BeautifulSoup(content, 'html.parser')
    div = soup.find('div', class_='styles_box__1sXJN')
    return div.text.strip() if div else None

def save_to_json(data, filename):
    """Saves data to a JSON file."""
    with open(filename, 'w') as json_file:
        json.dump(data, json_file)

def scrape_and_save(url, filename):
    """Scrapes content from the URL and saves it to a JSON file."""
    try:
        content = fetch_page(url)
        div_content = extract_content(content)

        if div_content:
            save_to_json({'content': div_content}, filename)
            print(f"Scraped content saved to {filename} successfully")
        else:
            print("No content found to scrape.")

    except Exception as e:
        print('Error scraping content:', e)

def test_scraping():
    """Test case to verify the scraping functionality."""
    test_url = 'https://www.onthesnow.com/british-columbia/skireport'
    test_filename = 'test_scraped_content.json'
    scrape_and_save(test_url, test_filename)
    try:
        with open(test_filename, 'r') as json_file:
            data = json.load(json_file)
            if 'content' in data and data['content']:
                print("Test passed: Content successfully scraped and saved.")
                print(data)
            else:
                print("Test failed: No content found in the saved file.")
    except FileNotFoundError:
        print("Test failed: File not found.")

if __name__ == "__main__":
    main_url = 'https://www.onthesnow.com/british-columbia/skireport'
    main_filename = 'scraped_content.json'
    scrape_and_save(main_url, main_filename)
    test_scraping()
