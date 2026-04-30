"""
cloud_update.py — GitHub Actions daily refresh for GYANLIVE Health dashboard
Fetches fresh live stream stats + shorts, updates SEED_VIDEOS & SEED_SHORTS in index.html
"""
import re, json, urllib.request, datetime

API_KEY      = 'AIzaSyCNTUjiXTQ-ftrP1NCiqBQXKO2Vu6XWFXs'
UPLOADS_PL   = 'UU7kQ5xtGhCP91OGjRasXYCw'
HTML_PATH    = 'index.html'
DAYS_BACK    = 92


def yt_get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())

def parse_duration(s):
    if not s or s == 'P0D': return 0
    m = re.match(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', s)
    if not m: return 0
    d, h, mi, sc = (int(m.group(i) or 0) for i in range(1, 5))
    return d*86400 + h*3600 + mi*60 + sc

def detect_subject(title):
    if re.search(r'staff.?nurse|nursing|SMC|staff nurse', title, re.IGNORECASE): return 'Staff Nurse'
    if re.search(r'MPHW|FHW|SI\b|health.?worker', title, re.IGNORECASE):        return 'MPHW/FHW/SI'
    if re.search(r'CHC|PHC|GMERS', title, re.IGNORECASE):                        return 'CHC/PHC'
    if re.search(r'pharmac|ફાર્માસ', title, re.IGNORECASE):                      return 'Pharmacist'
    return 'Other'


# Fetch uploads from last DAYS_BACK days
cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DAYS_BACK)
upload_items, page_token = [], ''
while True:
    url = (f'https://www.googleapis.com/youtube/v3/playlistItems'
           f'?part=snippet,contentDetails&playlistId={UPLOADS_PL}&maxResults=50&key={API_KEY}')
    if page_token: url += f'&pageToken={page_token}'
    data = yt_get(url)
    stop = False
    for it in data.get('items', []):
        pub_dt = datetime.datetime.fromisoformat(
            it['contentDetails']['videoPublishedAt'].replace('Z', '+00:00'))
        if pub_dt < cutoff: stop = True; break
        upload_items.append({
            'id':          it['contentDetails']['videoId'],
            'title':       it['snippet'].get('title', ''),
            'publishedAt': it['contentDetails']['videoPublishedAt'][:10],
        })
    page_token = data.get('nextPageToken', '')
    if not page_token or stop: break

print(f'Uploads fetched: {len(upload_items)}')

# Get video details
all_ids = [u['id'] for u in upload_items]
detail_map = {}
for i in range(0, len(all_ids), 50):
    batch = all_ids[i:i+50]
    data = yt_get(f'https://www.googleapis.com/youtube/v3/videos'
                  f'?part=contentDetails,statistics,snippet,liveStreamingDetails'
                  f'&id={",".join(batch)}&key={API_KEY}')
    for item in data.get('items', []):
        detail_map[item['id']] = item

live_streams, shorts = [], []
for u in upload_items:
    d = detail_map.get(u['id'])
    if not d: continue
    dur = parse_duration(d['contentDetails'].get('duration', ''))
    title   = d['snippet'].get('title', u['title'])
    pub     = d['snippet'].get('publishedAt', u['publishedAt'])[:10]
    stats   = d.get('statistics', {})
    ld      = d.get('liveStreamingDetails', {})
    views   = int(stats.get('viewCount', 0))
    likes   = int(stats.get('likeCount', 0))
    comments= int(stats.get('commentCount', 0))

    is_short = dur <= 180 or bool(re.search(r'#shorts?\b', title, re.IGNORECASE))
    is_live  = bool(ld.get('actualStartTime'))

    if is_live:
        dur_live = 0
        if ld.get('actualEndTime'):
            s = datetime.datetime.fromisoformat(ld['actualStartTime'].replace('Z','+00:00'))
            e = datetime.datetime.fromisoformat(ld['actualEndTime'].replace('Z','+00:00'))
            dur_live = int((e - s).total_seconds())
        live_streams.append({
            'id': u['id'], 'title': title, 'publishedAt': pub,
            'liveDate': ld['actualStartTime'][:10], 'duration': dur_live,
            'views': views, 'likes': likes, 'comments': comments,
            'subject': detect_subject(title),
        })
    elif is_short:
        shorts.append({
            'id': u['id'], 'title': title, 'publishedAt': pub,
            'durationSeconds': dur, 'viewCount': views,
            'likeCount': likes, 'commentCount': comments,
        })

live_streams.sort(key=lambda x: x['liveDate'], reverse=True)
shorts.sort(key=lambda x: x['publishedAt'], reverse=True)

print(f'Live streams: {len(live_streams)}, views: {sum(v["views"] for v in live_streams):,}')
print(f'Shorts: {len(shorts)}, views: {sum(s["viewCount"] for s in shorts):,}')

# Update HTML
with open(HTML_PATH, encoding='utf-8') as f:
    html = f.read()

html = re.sub(r'const SEED_VIDEOS\s*=\s*\[.*?\];',
    f'const SEED_VIDEOS  = {json.dumps(live_streams, ensure_ascii=False, separators=(",",":"))};',
    html, flags=re.DOTALL)
html = re.sub(r'const SEED_SHORTS\s*=\s*\[.*?\];',
    f'const SEED_SHORTS  = {json.dumps(shorts, ensure_ascii=False, separators=(",",":"))};',
    html, flags=re.DOTALL)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)
print('index.html updated ✓')
