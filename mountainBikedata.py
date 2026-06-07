import requests
from bs4 import BeautifulSoup
import json

# Function to scrape data
def scrape_data(url, output_filename):
    try:
        # Send GET request to the URL
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors

        soup = BeautifulSoup(response.content, 'html.parser')

        # List to hold scraped data
        trails = []

        # Find the table with the specified class
        table = soup.find('table', class_='table1 tablesorter responsive tablesorter-default')

        if table:
            # Scrape table headers from the thead tag
            headers = [th.text.strip() for th in table.find('thead').find_all('th')]

            # Scrape table rows from the tbody tag
            for row in table.find('tbody').find_all('tr'):
                cells = row.find_all('td')
                if len(cells) == len(headers):
                    trail_data = {headers[i]: cells[i].text.strip() for i in range(len(headers))}
                    trails.append(trail_data)

            # Save the scraped data to a JSON file
            with open(output_filename, 'w') as json_file:
                json.dump(trails, json_file, indent=4)

            print(f'Data successfully scraped and saved to {output_filename}')
        else:
            print('Table not found on the page.')

    except Exception as e:
        print('Error scraping data:', e)

# URL to scrape
url = 'https://www.trailforks.com/region/british-columbia/trails/'
output_filename = 'trails.json'

# Invoke the scraping function
scrape_data(url, output_filename)
