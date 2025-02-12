#!/usr/bin/env python3

import sys
import time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

# Wait conditions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

from bs4 import BeautifulSoup

# Reconfigure standard output to use UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

def download_truthsocial_page(output_file):
    """
    1.0️⃣ Downloads the fully rendered HTML of Donald Trump's Truth Social page,
    using Selenium and Edge. It clicks the “Truths” tab to ensure we
    see the main feed. Then it waits for the first post to appear.
    """
    edge_options = Options()
    edge_service = Service(r"C:\WebDrivers\msedgedriver.exe")
    driver = webdriver.Edge(service=edge_service, options=edge_options)

    try:
        print("Navigating to Trump's Truth Social page...")
        driver.get("https://truthsocial.com/@realDonaldTrump")

        wait = WebDriverWait(driver, 60)

        print("Waiting for the 'Truths' tab...")
        truths_tab = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Truths']"))
        )

        # JS click to avoid overlays intercepting
        print("Force-clicking 'Truths' tab via JS...")
        driver.execute_script("arguments[0].click();", truths_tab)

        print("Waiting for first post...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='status']")))

        # Optional: scroll a bit for more content
        ActionChains(driver).scroll_by_amount(0, 800).perform()
        time.sleep(3)

        print("Retrieving page source...")
        page_source = driver.page_source
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(page_source)

        print(f"Download complete! HTML saved to: {output_file}")

    finally:
        driver.quit()

def get_latest_post(html_file):
    """
    1.1️⃣ Reads the local HTML file, finds ALL 'div' tags with data-testid='status',
    and returns the first one that has a <p data-markup="true"> and a <time>.
    """
    with open(html_file, 'r', encoding='utf-8') as file:
        content = file.read()

    soup = BeautifulSoup(content, 'html.parser')

    # Grab ALL potential status blocks
    all_posts = soup.find_all('div', {'data-testid': 'status'})
    for post in all_posts:
        p_tag = post.find('p', {'data-markup': 'true'})
        time_tag = post.find('time')
        if p_tag and time_tag:
            # Found a valid post
            post_content = p_tag.get_text(strip=True)
            post_time = time_tag.get('title')
            return post_content, post_time

    # If no post had that structure, fallback:
    return None, None

if __name__ == "__main__":
    """
    1.2️⃣ Main script flow:
    - Download the page to a local file
    - Parse that file
    - Print Trump's latest post
    """

    output_file = r"C:\Users\Noah\OneDrive\Documents\bbschatbot1.0\trumphtml.html"

    # 1.3️⃣ Download the page
    download_truthsocial_page(output_file)

    # 1.4️⃣ Scrape the downloaded HTML
    post_content, post_time = get_latest_post(output_file)

    # 1.5️⃣ Print result
    if post_content and post_time:
        print(f"Latest Post: {post_content}")
        print(f"Posted on: {post_time}")
    else:
        print("No recent post found.")
