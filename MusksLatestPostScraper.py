#!/usr/bin/env python3

import sys
import time
import pickle
import json
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup

# Reconfigure standard output to use UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

def load_credentials():
    """Load login credentials from a JSON file."""
    with open("xcreds.json", "r") as file:
        return json.load(file)

def login_to_x(driver, username, password):
    """Log in to X using the provided credentials."""
    driver.get("https://x.com/login")
    wait = WebDriverWait(driver, 60)

    try:
        # Wait for the username field and enter the username
        username_field = wait.until(EC.presence_of_element_located((By.NAME, "text")))
        username_field.send_keys(username)
        username_field.send_keys(Keys.RETURN)

        # Wait for the password field and enter the password
        password_field = wait.until(EC.presence_of_element_located((By.NAME, "password")))
        password_field.send_keys(password)
        password_field.send_keys(Keys.RETURN)

        # Wait for the home page to load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='primaryColumn']")))

        # Save cookies to a file
        with open("cookies.pkl", "wb") as file:
            pickle.dump(driver.get_cookies(), file)
    except Exception as e:
        print(f"Error during login: {str(e)}")
        driver.quit()
        sys.exit(1)

def load_cookies(driver):
    """Load cookies from a file and add them to the driver."""
    try:
        with open("cookies.pkl", "rb") as file:
            cookies = pickle.load(file)
            for cookie in cookies:
                driver.add_cookie(cookie)
        return True
    except FileNotFoundError:
        return False

def download_x_page(output_file, username, password):
    """
    Downloads Elon Musk's X page with minimal necessary delay.
    """
    edge_options = Options()
    edge_service = Service(r"C:\WebDrivers\msedgedriver.exe")
    driver = webdriver.Edge(service=edge_service, options=edge_options)

    try:
        print("Navigating to Elon Musk's X page...")
        driver.get("https://x.com/elonmusk?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Eauthor")
        if load_cookies(driver):
            driver.refresh()
        else:
            print("Logging in to X...")
            login_to_x(driver, username, password)

        wait = WebDriverWait(driver, 60)
        print("Waiting for first post...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article")))
        
        # Single scroll with short delay
        ActionChains(driver).send_keys(Keys.PAGE_DOWN).perform()
        time.sleep(1)
        
        print("Retrieving page source...")
        page_source = driver.page_source
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(page_source)
        print(f"Download complete! HTML saved to: {output_file}")
    finally:
        driver.quit()

def get_latest_post(html_file):
    """
    Reads the local HTML file and looks for Musk's first non-pinned post.
    Returns the post content and full timestamp.
    """
    with open(html_file, 'r', encoding='utf-8') as file:
        content = file.read()
    
    soup = BeautifulSoup(content, 'html.parser')
    articles = soup.find_all('article')
    print("Debug - Found articles:", len(articles))
    
    for article in articles:
        # Skip if this is a pinned post
        pinned_indicator = article.find('div', string='Pinned')
        if pinned_indicator:
            print("Debug - Skipping pinned post")
            continue
            
        # Find spans with the target class in this article
        spans = article.find_all('span', class_='css-1jxf684 r-bcqeeo r-1ttztb7 r-qvutc0 r-poiln3')
        
        # Need at least 3 spans (username, dot separator, and content)
        if len(spans) < 3:
            continue
            
        for i in range(len(spans) - 2):  # Look at groups of three spans
            current_span = spans[i]
            separator_span = spans[i + 1]
            content_span = spans[i + 2]
            
            # Check if we found the pattern: username -> dot -> content
            if (current_span.get_text(strip=True) == "@elonmusk" and 
                separator_span.get_text(strip=True) == "·"):
                
                text = content_span.get_text(strip=True)
                if text and "keyboard shortcuts" not in text.lower():
                    # Find the timestamp in the article
                    timestamp = article.find('time')
                    time_text = timestamp.get('datetime') if timestamp else "No timestamp"
                    
                    print(f"Debug - Found post text: {text}")
                    print(f"Debug - Found timestamp: {time_text}")
                    return text, time_text
    
    return None, None

if __name__ == "__main__":
    """
    Main script flow:
    - Load credentials from a file
    - Download the page to a local file
    - Parse that file
    - Print Elon Musk's latest post
    """
    output_file = r"C:\Users\Noah\OneDrive\Documents\bbschatbot1.0\muskhtml.html"
    credentials = load_credentials()
    username = credentials["username"]
    password = credentials["password"]

    # Download the page
    download_x_page(output_file, username, password)

    # Scrape the downloaded HTML
    post_content, timestamp = get_latest_post(output_file)

    # Print result as a single chunk
    if post_content:
        print(f"Latest Post: {post_content} (Posted: {timestamp})")
    else:
        print("No recent post found.")
