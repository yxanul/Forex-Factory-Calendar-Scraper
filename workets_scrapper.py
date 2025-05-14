import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
from datetime import datetime, timedelta, date
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from calendar import monthrange
import threading # <--- Import threading

# --- Configuration ---
NUM_WORKERS = 3
CHUNK_SIZE_MONTHS = 1
# --- End Configuration ---

# Global lock for driver setup
driver_setup_lock = threading.Lock() # <--- Initialize the lock

def setup_worker_driver():
    """Sets up a Chrome driver instance for a worker thread, protected by a lock."""
    driver = None
    with driver_setup_lock: # <--- Acquire lock before setup
        print(f"[DriverSetup {os.getpid()}] Attempting to set up driver...")
        try:
            options = uc.ChromeOptions()
            options.add_argument('--no-first-run')
            options.add_argument('--no-service-autorun')
            options.add_argument('--password-store=basic')
            # options.add_argument('--headless')
            # options.add_argument('--disable-gpu')

            # Ensure the directory for undetected_chromedriver exists
            # This might not be strictly necessary if uc handles it, but can't hurt
            uc_path = os.path.join(os.getenv('APPDATA', ''), 'undetected_chromedriver')
            if not os.path.exists(uc_path):
                try:
                    os.makedirs(uc_path, exist_ok=True)
                except Exception as e:
                    print(f"[DriverSetup {os.getpid()}] Warning: Could not create uc_path {uc_path}: {e}")
            
            # Optional: Specify a version_main if you know your Chrome version
            # driver = uc.Chrome(options=options, version_main=108) # Example

            driver = uc.Chrome(options=options)
            print(f"[DriverSetup {os.getpid()}] Driver created successfully.")
            # driver.maximize_window()

            driver.get("https://www.forexfactory.com/calendar")
            print(f"[DriverSetup {os.getpid()}] Navigated to calendar. Waiting for page load...")
            time.sleep(4) # Increased sleep after initial navigation
            try:
                accept_button = driver.find_element(By.XPATH, "//*[contains(@class, 'cookie-consent__button') or contains(text(), 'Accept') or contains(@id, 'cookie-accept') or contains(@class, 'CybotCookiebotDialogBodyButton')]")
                if accept_button.is_displayed() and accept_button.is_enabled():
                    accept_button.click()
                    print(f"[DriverSetup {os.getpid()}] Clicked a cookie consent button.")
                    time.sleep(1)
            except Exception:
                # print(f"[DriverSetup {os.getpid()}] No obvious cookie consent button found.")
                pass
            print(f"[DriverSetup {os.getpid()}] Driver setup complete for worker.")
        except Exception as e:
            print(f"[DriverSetup {os.getpid()}] Error setting up driver: {e}")
            if driver:
                driver.quit()
            return None
    # Lock is released automatically when exiting the 'with' block
    return driver

# ... (rest of your code: generate_url_for_date, scroll_to_bottom, parse_impact, scrape_day_data)
# Ensure that these functions DO NOT call setup_worker_driver themselves.
# scrape_date_range_worker is the one that calls setup_worker_driver.

def generate_url_for_date(target_date):
    month_abbr = target_date.strftime("%b").lower()
    day_num = target_date.day
    year_num = target_date.year
    return f"https://www.forexfactory.com/calendar?day={month_abbr}{day_num}.{year_num}"

def scroll_to_bottom(driver, worker_id=""):
    # print(f"[Worker {worker_id}] Scrolling to load all events...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    attempts = 0
    max_attempts = 3
    while attempts < max_attempts:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5) # Wait for new content to load
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            attempts += 1
            if attempts >= 2:
                break
        else:
            attempts = 0
        last_height = new_height
    # print(f"[Worker {worker_id}] Finished scrolling.")


def parse_impact(impact_cell_element):
    try:
        span = impact_cell_element.find_element(By.TAG_NAME, "span")
        title = span.get_attribute("title").lower()
        if "non-economic" in title or "holiday" in title:
            return "Holiday"
        elif "low impact expected" in title:
            return "Low"
        elif "medium impact expected" in title:
            return "Medium"
        elif "high impact expected" in title:
            return "High"
        return "Unknown Impact: " + title
    except:
        return "N/A"

def scrape_day_data(driver, target_date_obj, worker_id=""):
    url = generate_url_for_date(target_date_obj)
    # print(f"[Worker {worker_id}] Scraping {target_date_obj.strftime('%Y-%m-%d')} from {url}")
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.calendar__table tr.calendar__row"))
        )
    except Exception:
        try:
            if "There are no news events scheduled" in driver.page_source:
                # print(f"[Worker {worker_id}] No events for {target_date_obj.strftime('%Y-%m-%d')}")
                return []
        except: pass # Ignore if page_source check fails
        # print(f"[Worker {worker_id}] Timeout/Error for {target_date_obj.strftime('%Y-%m-%d')}")
        return []

    scroll_to_bottom(driver, worker_id)
    events_data = []
    current_event_time_str = None

    try:
        calendar_table = driver.find_element(By.CSS_SELECTOR, "table.calendar__table")
        all_rows = calendar_table.find_elements(By.CSS_SELECTOR, "tr.calendar__row")
    except Exception:
        return [] # No table or rows found

    for row in all_rows:
        try:
            row.find_element(By.CSS_SELECTOR, "td.calendar__date[colspan]")
            continue # Skip date header row
        except:
            pass

        try:
            time_cell_text = row.find_element(By.CSS_SELECTOR, "td.calendar__time").text.strip()
            currency = row.find_element(By.CSS_SELECTOR, "td.calendar__currency").text.strip()
            impact_cell_element = row.find_element(By.CSS_SELECTOR, "td.calendar__impact")
            event_name_element = row.find_element(By.CSS_SELECTOR, "td.calendar__event")
            event_name = event_name_element.text.strip()
            if not event_name:
                try: event_name = event_name_element.find_element(By.TAG_NAME, "div").text.strip()
                except: pass

            actual = row.find_element(By.CSS_SELECTOR, "td.calendar__actual").text.strip()
            forecast = row.find_element(By.CSS_SELECTOR, "td.calendar__forecast").text.strip()
            previous = row.find_element(By.CSS_SELECTOR, "td.calendar__previous").text.strip()
        except Exception:
            continue # Skip malformed event row

        if time_cell_text:
            current_event_time_str = time_cell_text
        if not current_event_time_str:
            continue

        datetime_display_str = f"{target_date_obj.strftime('%Y-%m-%d')} {current_event_time_str}"
        if current_event_time_str.lower() == "all day":
            event_datetime_obj = datetime.combine(target_date_obj, datetime.min.time())
            datetime_display_str = event_datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
        elif "tentative" in current_event_time_str.lower():
            datetime_display_str = f"{target_date_obj.strftime('%Y-%m-%d')} Tentative"
        else:
            try:
                time_part = datetime.strptime(current_event_time_str, "%I:%M%p").time()
                event_datetime_obj = datetime.combine(target_date_obj, time_part)
                datetime_display_str = event_datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass # Keep raw time string if parsing fails

        impact = parse_impact(impact_cell_element)
        events_data.append({
            "datetime": datetime_display_str, "currency": currency, "impact": impact,
            "event": event_name, "actual": actual, "forecast": forecast, "previous": previous
        })
    return events_data

def scrape_date_range_worker(chunk_start_date, chunk_end_date, worker_id):
    """
    Worker function to scrape data for a given date range (chunk).
    Each worker manages its own driver.
    """
    print(f"[Worker {worker_id} ({os.getpid()})] Starting. Range: {chunk_start_date.strftime('%Y-%m-%d')} to {chunk_end_date.strftime('%Y-%m-%d')}")
    driver = setup_worker_driver() # This call is now thread-safe
    if not driver:
        print(f"[Worker {worker_id} ({os.getpid()})] Failed to initialize driver. Exiting task.")
        return []

    all_chunk_data = []
    current_day = chunk_start_date
    try:
        while current_day <= chunk_end_date:
            # print(f"[Worker {worker_id}] Processing day: {current_day.strftime('%Y-%m-%d')}")
            daily_data = scrape_day_data(driver, current_day, worker_id)
            if daily_data:
                all_chunk_data.extend(daily_data)
            
            time.sleep(1.5) 
            
            current_day += timedelta(days=1)
    except Exception as e:
        print(f"[Worker {worker_id} ({os.getpid()})] Error during scraping range {chunk_start_date} - {chunk_end_date}: {e}")
    finally:
        if driver:
            print(f"[Worker {worker_id} ({os.getpid()})] Quitting driver.")
            driver.quit() # This should also be safe now.
    
    print(f"[Worker {worker_id} ({os.getpid()})] Finished. Found {len(all_chunk_data)} events in range.")
    return all_chunk_data


def create_date_chunks(overall_start_date, overall_end_date, chunk_months):
    chunks = []
    current_start = overall_start_date
    while current_start <= overall_end_date:
        year = current_start.year
        month = current_start.month
        
        chunk_end_month = month + chunk_months - 1
        chunk_end_year = year
        
        while chunk_end_month > 12:
            chunk_end_month -= 12
            chunk_end_year += 1
            
        days_in_month = monthrange(chunk_end_year, chunk_end_month)[1]
        # Make sure chunk_end_day does not exceed the day of overall_end_date if it's the last chunk month
        if chunk_end_year == overall_end_date.year and chunk_end_month == overall_end_date.month:
            chunk_end_day = min(days_in_month, overall_end_date.day)
        else:
            chunk_end_day = days_in_month

        current_chunk_end = date(chunk_end_year, chunk_end_month, chunk_end_day)
        current_chunk_end = min(current_chunk_end, overall_end_date)
        
        chunks.append((current_start, current_chunk_end))
        
        current_start = current_chunk_end + timedelta(days=1)
        if current_start > overall_end_date:
            break
            
    return chunks


def main():
    overall_start_date = date(2015, 1, 1)
    #overall_end_date = date(2024, 12, 31) # Example: ~10 years of data
    overall_end_date = date(2015, 3, 31) # Shorter range for testing

    print(f"Starting Forex Factory Scraper for range: {overall_start_date} to {overall_end_date}")
    print(f"Number of parallel workers: {NUM_WORKERS}")
    print(f"Chunk size: {CHUNK_SIZE_MONTHS} month(s) per worker batch")

    date_chunks = create_date_chunks(overall_start_date, overall_end_date, CHUNK_SIZE_MONTHS)
    
    if not date_chunks:
        print("No date chunks to process.")
        return

    print(f"Total chunks to process: {len(date_chunks)}")

    all_scraped_data = []
    
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        future_to_chunk = {}
        for i, (chunk_start, chunk_end) in enumerate(date_chunks):
            future = executor.submit(scrape_date_range_worker, chunk_start, chunk_end, f"{i+1}")
            future_to_chunk[future] = (chunk_start, chunk_end)
            # Stagger initial driver setups by a bit more
            if i < NUM_WORKERS * 2: # Stagger the first few batches of workers more
                 time.sleep(2) # Increased stagger for initial worker launches
            elif i > 0 and i % (NUM_WORKERS * 2) == 0 : # Then stagger less frequently
                 time.sleep(5)


        for future in as_completed(future_to_chunk):
            chunk_start, chunk_end = future_to_chunk[future]
            try:
                chunk_data = future.result()
                if chunk_data:
                    all_scraped_data.extend(chunk_data)
                print(f"Completed chunk: {chunk_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}. Events: {len(chunk_data if chunk_data else [])}")
            except Exception as exc:
                print(f"Chunk {chunk_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')} generated an exception: {exc}")
    
    print("\nAll scraping tasks completed.")

    if all_scraped_data:
        try:
            df = pd.DataFrame(all_scraped_data)
            def robust_to_datetime(dt_str):
                try:
                    return pd.to_datetime(dt_str, format="%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        return pd.to_datetime(dt_str.split(' ')[0], format="%Y-%m-%d")
                    except:
                        return pd.NaT
            df['parsed_datetime'] = df['datetime'].apply(robust_to_datetime)
            df = df.sort_values(by='parsed_datetime').drop(columns=['parsed_datetime'])
        except Exception as e:
            print(f"Could not sort by datetime due to parsing issues: {e}. Data will be in order of chunk completion.")
            df = pd.DataFrame(all_scraped_data)

        df = df[['datetime', 'currency', 'impact', 'event', 'actual', 'forecast', 'previous']]
        
        output_filename = f"forex_factory_data_{overall_start_date.strftime('%Y%m%d')}_to_{overall_end_date.strftime('%Y%m%d')}.csv"
        df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"\nData saved to {output_filename}")
        print(f"Total events scraped: {len(df)}")
        print("Sample of scraped data (first 5 rows):")
        print(df.head())
        print("Sample of scraped data (last 5 rows):")
        print(df.tail())
    else:
        print("\nNo data was scraped for the specified date range.")

if __name__ == "__main__":
    main()