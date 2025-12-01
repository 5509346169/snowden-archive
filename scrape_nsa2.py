import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import argparse
import sqlite3

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36'
}

def get_next_page_url(soup, current_url):
    nav = soup.find('nav', class_='page-numbers')
    if nav:
        next_a = nav.find('a', class_='next')
        if next_a and next_a.get('href'):
            return urljoin("https://www.aclu.org", next_a['href'])

    current_page = None
    for a in soup.select('a.page-numbers, span.page-numbers'):
        try:
            page_num = int(a.get_text(strip=True))
            if 'current' in a.get('class', []) or a.name == 'span':
                current_page = page_num
        except:
            pass

    if current_page is not None:
        from urllib.parse import urlparse, parse_qs, urlencode
        parsed = urlparse(current_url)
        query = parse_qs(parsed.query)
        next_page = current_page + 1
        new_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/page/{next_page}"
        if query:
            new_url += "?" + urlencode(query, doseq=True)
        if parsed.fragment:
            new_url += "#" + parsed.fragment
        return new_url
    return None

def get_detail_pages_from_listing(soup):
    items = []
    for card in soup.select('a.document-listing-card'):
        href = card.get('href')
        if not href:
            continue
        detail_url = urljoin("https://www.aclu.org", href)

        title_div = card.find('div', class_='is-size-4')
        title = title_div.get_text(strip=True) if title_div else "Unknown Title"

        date_span = card.find(string=lambda t: t and "Document Date:" in t)
        doc_date = date_span.find_parent().get_text() if date_span else "Unknown Date"
        doc_date = doc_date.replace("Document Date:", "").strip()

        items.append({'detail_url': detail_url, 'title': title, 'doc_date': doc_date})
    return items

def get_direct_pdf_url(detail_url):
    try:
        r = requests.get(detail_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        a = soup.find('a', download=True) or soup.find('a', string=lambda x: x and 'Download document' in x)
        if a and a.get('href'):
            return urljoin("https://www.aclu.org", a['href'])
    except Exception as e:
        print(f"      PDF extraction failed: {e}")
    return None

def init_db(db_name='ACLU_NSA_Snowden-D.db'):
    conn = sqlite3.connect(db_name)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS ACLU (
            Page TEXT PRIMARY KEY,
            Document_Date TEXT,
            DirectPDF_Link TEXT,
            Duplicate TEXT DEFAULT 'No',
            Year_From_URL INTEGER
        )
    ''')
    # Add index for faster queries by year
    c.execute('CREATE INDEX IF NOT EXISTS idx_year ON ACLU (Year_From_URL);')
    conn.commit()
    return conn

def insert_into_db(conn, page_url, doc_date, pdf_url, year_from_url):
    c = conn.cursor()
    try:
        # Check if page already exists
        c.execute("SELECT 1 FROM ACLU WHERE Page = ?", (page_url,))
        exists = c.fetchone()
        duplicate = 'Yes' if exists else 'No'

        c.execute('''
            INSERT OR REPLACE INTO ACLU
            (Page, Document_Date, DirectPDF_Link, Duplicate, Year_From_URL)
            VALUES (?, ?, ?, ?, ?)
        ''', (page_url, doc_date, pdf_url, duplicate, year_from_url))

        conn.commit()
        print(f"      DB → Saved (Year: {year_from_url}, Dupe: {duplicate})")
    except Exception as e:
        print(f"      DB INSERT FAILED: {e}")

def scrape_year(base_url, year, conn, delay=2.0):
    all_pdfs = []
    page = 1

    print(f"\n{'='*80}")
    print(f" SCRAPING YEAR: {year} (from ?document_date={year})")
    print(f"{'='*80}")

    while True:
        url = f"{base_url}/page/{page}?document_date={year}#listings"
        print(f"\nPage {page} → {url}")

        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f"  Failed to load page: {e}")
            break

        soup = BeautifulSoup(r.text, 'html.parser')
        items = get_detail_pages_from_listing(soup)

        if not items:
            print("  No more documents → end of year")
            break

        print(f"  Found {len(items)} document(s)")
        for item in items:
            print(f"  • [{year}] {item['doc_date']} | {item['title'][:85]}{'...' if len(item['title'])>85 else ''}")
            pdf = get_direct_pdf_url(item['detail_url'])
            if pdf:
                insert_into_db(conn, item['detail_url'], item['doc_date'], pdf, year)
                all_pdfs.append({**item, 'pdf_url': pdf, 'year': year})
            else:
                print(f"      No PDF (likely redacted/withheld)")
            time.sleep(0.4)

        next_url = get_next_page_url(soup, url)
        if next_url and 'page/' in next_url:
            page += 1
            time.sleep(delay)
        else:
            print(f"  No next page → finished year {year}")
            break

    print(f"\nYear {year} → {len(all_pdfs)} PDFs saved to DB")
    return all_pdfs

# === MAIN ===
if __name__ == "__main__":
    base_url = "https://www.aclu.org/foia-collections/nsa-documents-search"
    years = [2018,2017,2016,2015,2014,2013,2012,2011,2010,2009,2008,
             2007,2006,2005,2004,2003,2002,2001,1997,1993,1905]

    parser = argparse.ArgumentParser()
    parser.add_argument('--delay', type=float, default=2.0)
    parser.add_argument('--db', type=str, default='ACLU_NSA_Snowden-D.db')
    args = parser.parse_args()

    conn = init_db(args.db)
    total = 0

    print("Starting ACLU NSA FOIA Scraper → Year_From_URL now 100% saved!\n")

    for year in years:
        count = len(scrape_year(base_url, year, conn, delay=args.delay))
        total += count
        print(f"Cumulative total: {total} documents")

    conn.close()
    print(f"\nALL DONE! {total} records with correct Year_From_URL saved")
    print(f"Database: {args.db}")
    print("Query example:")
    print("  SELECT COUNT(*) FROM ACLU WHERE Year_From_URL = 2013 AND Duplicate = 'No';")
