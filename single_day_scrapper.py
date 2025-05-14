import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
from datetime import datetime, timedelta, date
import os # For user_data_dir example

def setup_driver():
    options = uc.ChromeOptions()
    options.add_argument('--no-first-run')
    options.add_argument('--no-service-autorun')
    options.add_argument('--password-store=basic')
    # options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    # To persist session (e.g. for FF timezone settings):
    # user_data_dir = os.path.join(os.path.expanduser("~"), ".config", "uc_chrome_profile_ff")
    # if not os.path.exists(user_data_dir):
    #     os.makedirs(user_data_dir)
    # options.add_argument(f'--user-data-dir={user_data_dir}')

    try:
        driver = uc.Chrome(options=options)
        driver.maximize_window()
        print(f"Browser window maximized to: {driver.get_window_size()}")
        driver.get("https://www.forexfactory.com/calendar") # Initial visit
        print("Initial visit to Forex Factory calendar done. Allowing 5s for page load/cookies...")
        time.sleep(5) # Allow time for cookie banners or initial redirects
        # Example: Click cookie consent if it appears and blocks interaction
        try:
            accept_button = driver.find_element(By.XPATH, "//*[contains(@class, 'cookie-consent__button') or contains(text(), 'Accept') or contains(@id, 'cookie-accept')]") # General XPaths
            if accept_button.is_displayed() and accept_button.is_enabled():
                accept_button.click()
                print("Clicked a cookie consent button.")
                time.sleep(1)
        except Exception:
            print("No obvious cookie consent button found or interaction needed.")

    except Exception as e:
        print(f"Error setting up driver: {e}")
        print("Please ensure Chrome is installed and chromedriver is compatible or in PATH.")
        return None
    return driver

def generate_url_for_date(target_date):
    month_abbr = target_date.strftime("%b").lower()
    day_num = target_date.day
    year_num = target_date.year
    return f"https://www.forexfactory.com/calendar?day={month_abbr}{day_num}.{year_num}"

def scroll_to_bottom(driver):
    print("Scrolling to load all events...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    attempts = 0
    max_attempts = 5 # Max attempts to scroll if height doesn't change, in case of slow loads
    while attempts < max_attempts:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2) # Increased wait for new content to load
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            attempts += 1 # Increment attempts if height hasn't changed
            if attempts >= 2 : # if it hasn't changed for 2 consecutive scrolls, break.
                 print("Page height unchanged after scroll, assuming all loaded.")
                 break
        else:
            attempts = 0 # Reset attempts if height changed
        last_height = new_height
    print("Finished scrolling.")

def parse_impact(impact_cell_element):
    try:
        # The impact icon is usually within a <span> inside the <td>
        span = impact_cell_element.find_element(By.TAG_NAME, "span")
        title = span.get_attribute("title").lower() # Convert to lowercase for easier matching

        if "non-economic" in title or "holiday" in title: # Handle bank holiday (grey icon)
            return "Holiday"
        elif "low impact expected" in title:
            return "Low"
        elif "medium impact expected" in title:
            return "Medium"
        elif "high impact expected" in title:
            return "High"
        return "Unknown Impact Title: " + title # If title exists but not matched
    except:
        # This means the <td> for impact was found, but no <span> or no title, or cell was empty
        return "N/A"

def scrape_day_data(driver, target_date_obj):
    url = generate_url_for_date(target_date_obj)
    print(f"Scraping data for {target_date_obj.strftime('%Y-%m-%d')} from {url}")
    driver.get(url)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.calendar__table tr.calendar__row"))
        )
    except Exception as e:
        print(f"Timeout or error waiting for calendar table rows on {url}: {e}")
        # Check for "no events" message
        try:
            no_events_msg = driver.find_element(By.XPATH, "//*[contains(text(),'There are no news events scheduled')]")
            if no_events_msg:
                print("No news events scheduled for this day.")
                return []
        except:
            pass # No "no events" message found, or other error
        return []

    scroll_to_bottom(driver)

    events_data = []
    current_event_time_str = None # Carries over time for events under same timestamp

    try:
        calendar_table = driver.find_element(By.CSS_SELECTOR, "table.calendar__table")
        all_rows = calendar_table.find_elements(By.CSS_SELECTOR, "tr.calendar__row") # More specific
    except Exception as e:
        print(f"Could not find calendar table or rows on {target_date_obj.strftime('%Y-%m-%d')}: {e}")
        return []

    for row_index, row in enumerate(all_rows):
        # Check if it's a "Date Header" row (e.g., "Thursday, Jan 1")
        # These typically have one <td> with a colspan attribute and class 'calendar__date'
        try:
            date_header_cell = row.find_element(By.CSS_SELECTOR, "td.calendar__date[colspan]")
            # print(f"Skipping date header row: {date_header_cell.text.strip()}")
            continue # Skip this row, it's just a date separator
        except:
            # Not a date header row by the above criteria, proceed to parse as event
            pass

        # Attempt to parse as an event row.
        # Event rows should have specific cells. We'll use class-based selection.
        try:
            time_cell_text = row.find_element(By.CSS_SELECTOR, "td.calendar__time").text.strip()
            currency = row.find_element(By.CSS_SELECTOR, "td.calendar__currency").text.strip()
            impact_cell_element = row.find_element(By.CSS_SELECTOR, "td.calendar__impact")
            event_name_element = row.find_element(By.CSS_SELECTOR, "td.calendar__event")
            event_name = event_name_element.text.strip()
            # Sometimes event name might be inside a div or span
            if not event_name: # If text of td is empty, try to find inner div
                try:
                    event_name = event_name_element.find_element(By.TAG_NAME, "div").text.strip()
                except:
                    pass # stick with empty if no div

            actual = row.find_element(By.CSS_SELECTOR, "td.calendar__actual").text.strip()
            forecast = row.find_element(By.CSS_SELECTOR, "td.calendar__forecast").text.strip()
            previous = row.find_element(By.CSS_SELECTOR, "td.calendar__previous").text.strip()

        except Exception as e:
            # This row doesn't have the expected structure of an event row.
            # It could be an empty row, a malformed row, or one we haven't accounted for.
            # print(f"Skipping row {row_index+1} due to missing standard event cell structure. Text: '{row.text[:100]}'. Error: {e}")
            continue

        # Process time
        if time_cell_text: # If this row explicitly specifies a time
            current_event_time_str = time_cell_text
        
        if not current_event_time_str: # Should not happen if first event has time
            print(f"Warning: No current_event_time_str for event '{event_name}'. Skipping.")
            continue

        event_datetime_obj = None
        datetime_display_str = f"{target_date_obj.strftime('%Y-%m-%d')} {current_event_time_str}"

        if current_event_time_str.lower() == "all day":
            event_datetime_obj = datetime.combine(target_date_obj, datetime.min.time())
            datetime_display_str = event_datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
        elif "tentative" in current_event_time_str.lower():
            event_datetime_obj = datetime.combine(target_date_obj, datetime.min.time())
            datetime_display_str = f"{target_date_obj.strftime('%Y-%m-%d')} Tentative"
        else:
            try:
                # Forex Factory usually shows am/pm
                time_part = datetime.strptime(current_event_time_str, "%I:%M%p").time()
                event_datetime_obj = datetime.combine(target_date_obj, time_part)
                datetime_display_str = event_datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                # This can happen if time is something else like '--' or unexpected format
                print(f"Warning: Could not parse time '{current_event_time_str}' for event '{event_name}'. Using date and raw time string.")
                event_datetime_obj = datetime.combine(target_date_obj, datetime.min.time()) # Default to midnight


        impact = parse_impact(impact_cell_element)

        events_data.append({
            "datetime": datetime_display_str,
            "currency": currency,
            "impact": impact,
            "event": event_name,
            "actual": actual,
            "forecast": forecast,
            "previous": previous
        })
            
    return events_data


def main():
    driver = setup_driver()
    if not driver:
        print("Driver setup failed. Exiting.")
        return

    # Define your date range
    start_date = date(2016, 3, 1)
    end_date = date(2016, 3, 1) # Inclusive
    
    # For a single day test:
    # start_date = date(2024, 3, 15) # Example of a more recent date
    # end_date = date(2024, 3, 15)


    all_scraped_data = []
    current_scrape_date = start_date

    try:
        while current_scrape_date <= end_date:
            daily_data = scrape_day_data(driver, current_scrape_date)
            if daily_data: # Only extend if data was found
                all_scraped_data.extend(daily_data)
            current_scrape_date += timedelta(days=1)
            if current_scrape_date <= end_date: # Avoid sleeping after the last day
                 print("Sleeping for 2 seconds before next day...")
                 time.sleep(2) # Be polite to the server
    finally:
        print("Quitting driver...")
        driver.quit()

    if all_scraped_data:
        df = pd.DataFrame(all_scraped_data)
        df = df[['datetime', 'currency', 'impact', 'event', 'actual', 'forecast', 'previous']] # Ensure column order
        
        output_filename = f"forex_factory_data_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
        df.to_csv(output_filename, index=False, encoding='utf-8-sig') # utf-8-sig for Excel compatibility
        print(f"\nData saved to {output_filename}")
        print("Sample of scraped data:")
        print(df.head())
    else:
        print("\nNo data was scraped for the specified date range.")

if __name__ == "__main__":
    main()