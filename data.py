import requests
from bs4 import BeautifulSoup
import json

def fetch_page(url):
    # Fetches and returns the HTML content of the given URL.
    response = requests.get(url)
    response.raise_for_status()  # Raises an error for bad status codes
    return BeautifulSoup(response.text, 'html.parser')

def parse_table(table):
    # Extracts resort information from an HTML table.
    resort_info = {}
    rows = table.find_all('tr')
    headers = [th.text.strip() for th in rows[0].find_all('th')]

    for row in rows[1:]:
        data = [td.text.strip() for td in row.find_all('td')]
        if data:  # Ensure row_data is not empty
            resort_info[data[0]] = dict(zip(headers, data))
    
    return resort_info

def scrape_resorts_data(url):
    # Scrapes resort data from the given URL.
    soup = fetch_page(url)
    tables = soup.find_all('table')
    return [parse_table(table) for table in tables[:-1]]

def save_to_json(data, filename):
    # Saves data to a JSON file.
    with open(filename, "w") as json_file:
        json.dump(data, json_file, indent=4)

def main():
    # Main function to scrape and save resort data.
    url = "https://www.onthesnow.com/british-columbia/skireport"
    data = scrape_resorts_data(url)
    save_to_json(data, "ski_resorts.json")
    print("Data saved to ski_resorts.json")

if __name__ == "__main__":
    main()
