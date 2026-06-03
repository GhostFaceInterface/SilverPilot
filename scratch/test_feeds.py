import httpx
from xml.etree import ElementTree

feeds = {
    "kitco-rss": [
        "https://www.kitco.com/feed/rss/news/gold-silver",
        "https://www.kitco.com/feed/rss/news",
    ],
    "bloomberght-rss": [
        "https://www.bloomberght.com/rss",
        "https://www.bloomberght.com/rss/tum-haberler",
    ],
    "fxstreet-rss": [
        "https://www.fxstreet.com/rss/news",
        "https://xml.fxstreet.com/news/forex-news/index.xml",
    ],
    "investing-rss": [
        "https://www.investing.com/rss/news_287.rss",
        "https://www.investing.com/rss/news_25.rss",
    ],
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

with httpx.Client(timeout=10, follow_redirects=True, headers=headers) as client:
    for source, urls in feeds.items():
        print(f"\n=== Testing {source} ===")
        for url in urls:
            try:
                response = client.get(url)
                print(f"URL: {url} | Status: {response.status_code}")
                if response.status_code == 200:
                    text = response.text.strip()
                    print(f"Content Length: {len(text)}")
                    print(f"Snippet: {text[:200]}...")
                    # Parse test
                    try:
                        root = ElementTree.fromstring(text.encode("utf-8"))
                        channel = root.find("channel")
                        if channel is not None:
                            items = channel.findall("item")
                            print(f"Parsed RSS. Found {len(items)} items.")
                            if items:
                                print(f"Sample item title: {items[0].findtext('title')}")
                                print(f"Sample item pubDate: {items[0].findtext('pubDate')}")
                        else:
                            ns = {"atom": "http://www.w3.org/2005/Atom"}
                            entries = root.findall("atom:entry", ns)
                            print(f"Parsed Atom. Found {len(entries)} entries.")
                    except Exception as parse_err:
                        print(f"XML Parse Error: {parse_err}")
                else:
                    print(f"Body: {response.text[:200]}...")
            except Exception as exc:
                print(f"Fetch Error for {url}: {exc}")
