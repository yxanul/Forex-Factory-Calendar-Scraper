# Forex Factory Calendar Scraper

This project provides two Python scripts for scraping economic calendar data from [ForexFactory.com](https://www.forexfactory.com/calendar), with full parsing of event time, currency, impact level, and outcome details.

## 🧰 Scripts

### 1. `workers_scraper.py`
- Multi-threaded scraper using `ThreadPoolExecutor`
- Designed for collecting historical data over large ranges
- Handles date batching and Chrome driver pooling
- Saves the entire dataset to CSV

### 2. `single_day_scraper.py`
- Simpler script to scrape data for one day or a small range
- Quick to run for recent data pulls

## ⚠️ Note on Undetected Chrome Driver (UC) and Cloudflare

Forex Factory uses **Cloudflare bot protection**, which can block automated browsers — especially when run in headless mode.

To work around this:
- Both scripts use `undetected-chromedriver` (UC)
- **Headless mode is disabled intentionally**
- UC helps bypass Cloudflare and keeps the session human-like

You’ll see a visible Chrome browser window when scraping — this is expected and required for reliable operation.

## 📦 Requirements

- Python 3.7+
- Google Chrome installed
- [ChromeDriver](https://chromedriver.chromium.org/downloads) (handled automatically by `undetected-chromedriver`)

Install dependencies:

```bash
pip install -r requirements.txt


🚀 Usage
Batch Historical Scraping
```bash
python workers_scraper.py
Edit the overall_start_date and overall_end_date in the script.

Single-Day Scraping
```bash
python single_day_scraper.py
Edit start_date and end_date directly in the script.


💾 Output
Each script saves results to a CSV file:
forex_factory_data_YYYYMMDD_to_YYYYMMDD.csv
With columns:

-datetime

-currency

-impact

-event

-actual

-forecast

-previous


🧠 Tip
The first time you run it, Chrome may open with cookie prompts. The scripts try to auto-accept cookie banners where possible.
