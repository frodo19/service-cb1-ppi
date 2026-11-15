"""Library, TV shows, artwork and control for the mobile app (JSON-RPC based)."""
import json, os, threading, time, zlib
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

import xbmc, xbmcvfs

import lib

LIB_LOCK = threading.Lock()
LIB_REV = 0           # incremented on Kodi VideoLibrary events
_CACHE = {}           # kulcs -> (rev, adat)


def bump():
    global LIB_REV
    LIB_REV += 1


def rpc(method, params=None):
    req = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params:
        req['params'] = params
    try:
        out = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
    except (ValueError, TypeError):
        return {}
    return out if isinstance(out, dict) else {}


def result(method, params=None):
    r = rpc(method, params).get('result')
    return r if isinstance(r, dict) else {}


def _cached(key, build):
    with LIB_LOCK:
        hit = _CACHE.get(key)
        if hit and hit[0] == LIB_REV:
            return hit[1]
    data = build()
    with LIB_LOCK:
        _CACHE[key] = (LIB_REV, data)
    return data


# --------------------------------------------------------------- artwork ---
def tag(path):
    return '%08x' % (zlib.crc32(path.encode('utf-8', 'replace')) & 0xffffffff) if path else ''


def _unwrap(path):
    if path.startswith('image://'):
        inner = unquote(path[len('image://'):])
        return inner[:-1] if inner.endswith('/') else inner
    return path


def read_picture(path):
    """(bytes, type) or None. Kodi texture cache first, then the original."""
    if not path:
        return None
    sources = (path, _unwrap(path)) if path.startswith('image://') \
        else ('image://' + quote(path, safe='') + '/', path)
    for src in sources:
        try:
            f = xbmcvfs.File(src)
            try:
                data = bytes(f.readBytes(8 * 1024 * 1024))
            finally:
                f.close()
        except (RuntimeError, OSError):
            continue
        if not data:
            continue
        if data[:3] == b'\xff\xd8\xff':
            return data, 'image/jpeg'
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return data, 'image/png'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return data, 'image/webp'
        return data, 'image/jpeg'
    return None


def playing_art(kind):
    names = {'poster': ('Player.Art(poster)', 'Player.Art(tvshow.poster)', 'Player.Art(thumb)'),
             'fanart': ('Player.Art(fanart)', 'Player.Art(tvshow.fanart)'),
             'thumb': ('Player.Art(thumb)',)}.get(kind, ())
    for n in names:
        v = (xbmc.getInfoLabel(n) or '').strip()
        if v:
            return v
    return ''


def item_art(kind, query):
    def one(name):
        return (query.get(name) or [''])[0]
    if one('movieid'):
        art = result('VideoLibrary.GetMovieDetails', {'movieid': int(one('movieid') or 0),
                     'properties': ['art']}).get('moviedetails', {}).get('art', {})
    elif one('tvshowid'):
        art = result('VideoLibrary.GetTVShowDetails', {'tvshowid': int(one('tvshowid') or 0),
                     'properties': ['art']}).get('tvshowdetails', {}).get('art', {})
    elif one('episodeid'):
        art = result('VideoLibrary.GetEpisodeDetails', {'episodeid': int(one('episodeid') or 0),
                     'properties': ['art']}).get('episodedetails', {}).get('art', {})
        if kind == 'poster':
            return art.get('tvshow.poster') or art.get('thumb') or ''
        if kind == 'fanart':
            return art.get('tvshow.fanart') or art.get('fanart') or ''
    else:
        return playing_art(kind)
    return art.get(kind) or (art.get('thumb') if kind == 'thumb' else '') or ''


# --------------------------------------------------------------- common ---
_HDR = {'dolbyvision': 'dv', 'hdr10plus': 'hdr10plus', 'hdr10+': 'hdr10plus',
        'hdr10': 'hdr10', 'hlg': 'hlg'}
_AUDIO = {'truehd_atmos': 'atmos', 'eac3_ddp_atmos': 'atmos', 'eac3_atmos': 'atmos', 'atmos': 'atmos',
          'dtshd_ma_x': 'dtsx', 'dtshd_ma_x_imax': 'dtsx', 'dtsx': 'dtsx',
          'truehd': 'truehd', 'mlp': 'truehd', 'eac3': 'eac3', 'ac3': 'ac3',
          'dtshd_ma': 'dtshd_ma', 'dtshd_hra': 'dtshd_hra', 'dts': 'dts',
          'flac': 'flac', 'aac': 'aac', 'opus': 'opus', 'mp3': 'mp3', 'vorbis': 'vorbis'}


def _formats(streamdetails):
    out = {}
    if not isinstance(streamdetails, dict):
        return out
    video = (streamdetails.get('video') or [{}])[0]
    audio = (streamdetails.get('audio') or [{}])[0]
    if video:
        hdr = _HDR.get(str(video.get('hdrtype') or '').lower(), 'sdr')
        out['video'] = hdr
        if hdr == 'dv':
            detail = str(video.get('hdrdetail') or '').strip()
            if detail:
                out['dv_profile'] = detail
        w = video.get('width') or 0
        out['resolution'] = '2160p' if w >= 3200 else '1080p' if w >= 1700 else '720p' if w >= 1100 else 'sd'
    codec = str(audio.get('codec') or '').lower()
    fam = _AUDIO.get(codec) or ('pcm' if codec.startswith('pcm') else '')
    if fam:
        out['audio'] = fam
    return out


def _resume(r):
    try:
        pos, total = float(r.get('position') or 0), float(r.get('total') or 0)
    except (TypeError, ValueError, AttributeError):
        return 0
    return int(pos) if pos >= 30 and total > pos else 0


def _resume_any(r):
    try:
        pos = float((r or {}).get('position') or 0)
    except (TypeError, ValueError):
        return 0
    return int(pos) if pos > 0 else 0


_SRC = (('imdb', 'imdb'), ('themoviedb', 'tmdb'), ('tmdb', 'tmdb'), ('trakt', 'trakt'), ('tvdb', 'tvdb'),
        ('letterboxd', 'letterboxd'), ('metacritic', 'metacritic'), ('metascore', 'metacritic'),
        ('metacriticuser', 'metacriticuser'), ('rottentomatoes', 'rottentomatoes'),
        ('tomatometer', 'rottentomatoes'), ('tomatometerallcritics', 'rottentomatoes'),
        ('tomatoes', 'rottentomatoes'), ('popcorn', 'popcorn'), ('popcornmeter', 'popcorn'),
        ('tomatometerallaudience', 'popcorn'), ('tomatoesaudience', 'popcorn'), ('audience', 'popcorn'),
        ('rogerebert', 'rogerebert'), ('myanimelist', 'myanimelist'), ('mdblist', 'mdblist'))
_ALIAS = dict(_SRC)
_ORDER = {n: i for i, n in enumerate(dict.fromkeys(_ALIAS.values()))}


def rating_list(ratings):
    """Kodi 'ratings' dict -> list by the app's source names (known sources first)."""
    found = {}
    for raw, held in (ratings or {}).items():
        if not isinstance(held, dict):
            continue
        key = str(raw).strip().lower()[:24]
        name = _ALIAS.get(key, key)
        try:
            value = float(held.get('rating') or 0)
        except (TypeError, ValueError):
            continue
        if name and name not in found and 0 < value <= 10:
            found[name] = {'source': name, 'rating': round(value, 1), 'votes': int(held.get('votes') or 0)}
    return sorted(found.values(), key=lambda r: (_ORDER.get(r['source'], len(_ORDER)), r['source']))[:25]


def _rating(row):
    ratings = row.get('ratings')
    if isinstance(ratings, dict) and ratings:
        name, data = next(((k, v) for k, v in ratings.items() if v.get('default')),
                          next(iter(ratings.items())))
        return round(float(data.get('rating') or 0), 1), name
    return round(float(row.get('rating') or 0), 1), ''


def _duration(row):
    rt = row.get('runtime') or 0
    return int(rt)


# --------------------------------------------------------------- filmek ---
def movies():
    def build():
        rows = result('VideoLibrary.GetMovies', {'properties': [
            'title', 'year', 'art', 'runtime', 'playcount', 'resume', 'ratings', 'rating',
            'dateadded', 'genre', 'streamdetails']}).get('movies', [])
        out = []
        for r in rows:
            rating, src = _rating(r)
            film = {'id': r.get('movieid', 0), 'title': r.get('title', ''), 'year': r.get('year') or 0,
                    'poster': tag((r.get('art') or {}).get('poster', '')), 'duration': _duration(r),
                    'rating': rating, 'rating_from': src, 'watched': (r.get('playcount') or 0) > 0,
                    'resume': _resume(r.get('resume')), 'added': r.get('dateadded', ''),
                    'genres': r.get('genre') or []}
            film.update(_formats(r.get('streamdetails')))
            out.append(film)
        return {'movies': out, 'count': len(out), 'tag': '%x-%x' % (LIB_REV, len(out))}
    return _cached('movies', build)


def shows():
    def build():
        rows = result('VideoLibrary.GetTVShows', {'properties': [
            'title', 'year', 'art', 'episode', 'watchedepisodes', 'rating', 'ratings',
            'dateadded', 'genre']}).get('tvshows', [])
        out = []
        for r in rows:
            total, seen = r.get('episode') or 0, r.get('watchedepisodes') or 0
            rating, src = _rating(r)
            art = r.get('art') or {}
            out.append({'id': r.get('tvshowid', 0), 'title': r.get('title', ''), 'year': r.get('year') or 0,
                        'poster': tag(art.get('poster', '')), 'fanart': tag(art.get('fanart', '')),
                        'episodes': total, 'unseen': max(total - seen, 0), 'rating': rating,
                        'rating_from': src, 'watched': total > 0 and seen >= total,
                        'added': r.get('dateadded', ''), 'genres': r.get('genre') or []})
        return {'shows': out, 'count': len(out), 'tag': '%x-%x' % (LIB_REV, len(out))}
    return _cached('shows', build)


def _episode(r):
    return {'id': r.get('episodeid', 0), 'title': r.get('title', ''), 'season': r.get('season', -1),
            'episode': r.get('episode', -1), 'thumb': tag((r.get('art') or {}).get('thumb', '')),
            'duration': _duration(r), 'watched': (r.get('playcount') or 0) > 0,
            'resume': _resume(r.get('resume'))}


_EP_PROPS = ['title', 'season', 'episode', 'art', 'runtime', 'playcount', 'resume']


def episodes(show_id):
    def build():
        rows = result('VideoLibrary.GetEpisodes', {'tvshowid': show_id, 'properties': _EP_PROPS,
                      'sort': {'method': 'episode'}}).get('episodes', [])
        rows.sort(key=lambda r: (r.get('season', 0), r.get('episode', 0)))
        title = result('VideoLibrary.GetTVShowDetails', {'tvshowid': show_id,
                       'properties': ['title']}).get('tvshowdetails', {}).get('title', '')
        eps = [_episode(r) for r in rows]
        return {'tvshowid': show_id, 'title': title, 'episodes': eps, 'count': len(eps),
                'tag': '%x-%x' % (LIB_REV, len(eps))}
    return _cached('ep%d' % show_id, build)


def continuing():
    def build():
        items = []
        flt = {'field': 'inprogress', 'operator': 'true', 'value': ''}
        mv = result('VideoLibrary.GetMovies', {'filter': flt, 'limit': 20,
                    'sort': {'method': 'lastplayed', 'order': 'descending'},
                    'properties': ['title', 'year', 'art', 'runtime', 'resume', 'lastplayed',
                                   'ratings', 'rating']}).get('movies', [])
        for r in mv:
            rating, src = _rating(r)
            items.append({'kind': 'movie', 'id': r.get('movieid', 0), 'title': r.get('title', ''),
                          'year': r.get('year') or 0, 'poster': tag((r.get('art') or {}).get('poster', '')),
                          'duration': _duration(r), 'resume': _resume_any(r.get('resume')),
                          'lastplayed': r.get('lastplayed', ''), 'rating': rating, 'rating_from': src})
        ep = result('VideoLibrary.GetEpisodes', {'filter': flt, 'limit': 20,
                    'sort': {'method': 'lastplayed', 'order': 'descending'},
                    'properties': ['title', 'showtitle', 'tvshowid', 'season', 'episode', 'art',
                                   'runtime', 'resume', 'lastplayed']}).get('episodes', [])
        for r in ep:
            art = r.get('art') or {}
            items.append({'kind': 'episode', 'id': r.get('episodeid', 0), 'title': r.get('title', ''),
                          'poster': tag(art.get('tvshow.poster') or art.get('thumb') or ''),
                          'duration': _duration(r), 'resume': _resume_any(r.get('resume')),
                          'show': r.get('showtitle', ''), 'tvshowid': r.get('tvshowid', 0),
                          'season': r.get('season', -1), 'episode': r.get('episode', -1),
                          'lastplayed': r.get('lastplayed', '')})
        items.sort(key=lambda i: i.get('lastplayed', ''), reverse=True)
        nxt = []
        started = result('VideoLibrary.GetTVShows', {'limit': 10, 'sort': {'method': 'lastplayed',
                         'order': 'descending'}, 'properties': ['title', 'episode', 'watchedepisodes',
                         'art']}).get('tvshows', [])
        for s in started:
            if not (s.get('watchedepisodes') or 0) or (s.get('watchedepisodes') or 0) >= (s.get('episode') or 0):
                continue
            rows = result('VideoLibrary.GetEpisodes', {'tvshowid': s['tvshowid'],
                          'filter': {'field': 'playcount', 'operator': 'is', 'value': '0'},
                          'properties': ['title', 'season', 'episode', 'art', 'runtime', 'resume']}
                          ).get('episodes', [])
            rows = [r for r in rows if r.get('season', 0) > 0] or rows
            if not rows:
                continue
            r = min(rows, key=lambda r: (r.get('season', 0), r.get('episode', 0)))
            art = r.get('art') or {}
            nxt.append({'kind': 'episode', 'id': r.get('episodeid', 0), 'title': r.get('title', ''),
                        'poster': tag(art.get('tvshow.poster') or art.get('thumb') or ''),
                        'duration': _duration(r), 'resume': _resume_any(r.get('resume')),
                        'show': s.get('title', ''), 'tvshowid': s['tvshowid'],
                        'season': r.get('season', -1), 'episode': r.get('episode', -1)})
        return {'items': items, 'next': nxt, 'count': len(items) + len(nxt),
                'tag': '%x-%x' % (LIB_REV, len(items) + len(nxt))}
    return build()  # no cache: the resume list is always fresh


# --------------------------------------------------------------- details ---
def _cast(rows):
    return [{'name': c.get('name', ''), 'role': c.get('role', '')} for c in (rows or [])[:20]]


def details(query):
    def one(n):
        v = (query.get(n) or [''])[0]
        return int(v) if v.isdigit() else 0
    common = ['title', 'plot', 'genre', 'cast', 'art', 'streamdetails', 'ratings', 'mpaa', 'playcount',
              'resume', 'runtime', 'uniqueid']
    if one('movieid'):
        r = result('VideoLibrary.GetMovieDetails', {'movieid': one('movieid'), 'properties': common + [
            'year', 'tagline', 'director', 'writer', 'studio', 'country', 'premiered', 'top250', 'userrating']}
        ).get('moviedetails', {})
        kind, rid = 'movie', one('movieid')
    elif one('episodeid'):
        r = result('VideoLibrary.GetEpisodeDetails', {'episodeid': one('episodeid'), 'properties': common + [
            'showtitle', 'season', 'episode', 'director', 'writer', 'firstaired', 'userrating']}
        ).get('episodedetails', {})
        kind, rid = 'episode', one('episodeid')
    elif one('tvshowid'):
        r = result('VideoLibrary.GetTVShowDetails', {'tvshowid': one('tvshowid'), 'properties': [
            'title', 'plot', 'genre', 'cast', 'art', 'ratings', 'mpaa', 'year', 'studio', 'premiered',
            'userrating', 'uniqueid']}).get('tvshowdetails', {})
        kind, rid = 'tvshow', one('tvshowid')
    else:
        return None
    if not r:
        return None
    ratings = with_mdblist(rating_list(r.get('ratings')), kind, r.get('uniqueid'), block=True)
    art = r.get('art') or {}
    out = {'kind': kind, 'id': rid, 'title': r.get('title', ''), 'plot': r.get('plot', ''),
           'tagline': r.get('tagline', ''), 'show': r.get('showtitle', ''), 'mpaa': r.get('mpaa', ''),
           'year': r.get('year') or 0, 'duration': _duration(r), 'ratings': ratings,
           'season': r.get('season', -1), 'episode': r.get('episode', -1),
           'userrating': r.get('userrating') or 0, 'top250': r.get('top250') or 0,
           'premiered': r.get('premiered') or r.get('firstaired') or '',
           'genres': r.get('genre') or [], 'directors': [], 'writers': [],
           'studios': r.get('studio') or [],
           'countries': r.get('country') or [], 'cast': [], 'cast_more': False,
           'poster': tag(art.get('poster') or art.get('tvshow.poster') or ''),
           'fanart': tag(art.get('fanart') or art.get('tvshow.fanart') or ''),
           'thumb': tag(art.get('thumb') or '')}
    if kind != 'tvshow':
        out['watched'] = (r.get('playcount') or 0) > 0
        out['resume'] = _resume(r.get('resume'))
        out.update(_formats(r.get('streamdetails')))
    return out


# --------------------------------------------------------------- playback ---
def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def play(body):
    resume = body.get('resume')
    if _int(body.get('movieid')):
        item = {'movieid': _int(body['movieid'])}
    elif _int(body.get('episodeid')):
        item = {'episodeid': _int(body['episodeid'])}
    else:
        return False
    # The app sends resume=false only for the "from start" button; otherwise resume.
    params = {'item': item, 'options': {'resume': resume is not False}}
    return 'result' in rpc('Player.Open', params)


def set_watched(body):
    watched = body.get('watched')
    if not isinstance(watched, bool):
        return False
    count = 1 if watched else 0
    if _int(body.get('movieid')):
        r = rpc('VideoLibrary.SetMovieDetails', {'movieid': _int(body['movieid']), 'playcount': count,
                'resume': {'position': 0, 'total': 0}})
    elif _int(body.get('episodeid')):
        r = rpc('VideoLibrary.SetEpisodeDetails', {'episodeid': _int(body['episodeid']), 'playcount': count,
                'resume': {'position': 0, 'total': 0}})
    elif _int(body.get('tvshowid')):
        eps = result('VideoLibrary.GetEpisodes', {'tvshowid': _int(body['tvshowid']),
                     'properties': ['playcount']}).get('episodes', [])
        r = {'result': 'OK'}
        for e in eps:
            if ((e.get('playcount') or 0) > 0) != watched:
                rpc('VideoLibrary.SetEpisodeDetails', {'episodeid': e['episodeid'], 'playcount': count,
                    'resume': {'position': 0, 'total': 0}})
    else:
        return False
    bump()
    return 'result' in r


def clear_resume(body):
    z = {'resume': {'position': 0, 'total': 0}}
    if _int(body.get('movieid')):
        r = rpc('VideoLibrary.SetMovieDetails', dict(z, movieid=_int(body['movieid'])))
    elif _int(body.get('episodeid')):
        r = rpc('VideoLibrary.SetEpisodeDetails', dict(z, episodeid=_int(body['episodeid'])))
    else:
        return False
    bump()
    return 'result' in r


# --------------------------------------------------------------- control ---
def _player_id():
    for p in result_list('Player.GetActivePlayers'):
        if p.get('type') == 'video':
            return p.get('playerid')
    return None


def result_list(method):
    r = rpc(method).get('result')
    return r if isinstance(r, list) else []


def _num(v, lo, hi):
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _action(name):
    return rpc('Input.ExecuteAction', {'action': name}).get('result') == 'OK'


def command(action, value=None):
    ok = lambda m, p: 'result' in rpc(m, p)
    if action == 'volume_up':
        return _action('volumeup')
    if action == 'volume_down':
        return _action('volumedown')
    if action == 'mute':
        return _action('mute')
    pid = _player_id()
    if pid is None:
        return False
    if action == 'playpause':
        return ok('Player.PlayPause', {'playerid': pid})
    if action == 'stop':
        return ok('Player.Stop', {'playerid': pid})
    if action == 'seek':
        n = _num(value, -3600, 3600)
        return n is not None and ok('Player.Seek', {'playerid': pid, 'value': {'seconds': int(n)}})
    if action == 'seek_percent':
        n = _num(value, 0, 100)
        return n is not None and ok('Player.Seek', {'playerid': pid, 'value': {'percentage': n}})
    if action == 'chapter_next':
        return _action('chapterorbigstepforward')
    if action == 'chapter_previous':
        return _action('chapterorbigstepback')
    if action == 'audio':
        n = _num(value, 0, 64)
        return n is not None and ok('Player.SetAudioStream', {'playerid': pid, 'stream': int(n)})
    if action == 'subtitle':
        n = _num(value, -1, 64)
        if n is None:
            return False
        if n < 0:
            return ok('Player.SetSubtitle', {'playerid': pid, 'subtitle': 'off'})
        return ok('Player.SetSubtitle', {'playerid': pid, 'subtitle': int(n), 'enable': True})
    if action == 'audio_delay':
        n = _num(value, -10, 10)
        return n is not None and ok('Player.SetAudioDelay', {'playerid': pid, 'offset': round(n, 3)})
    return False


def controls():
    """The snapshot 'controls' field: audio and subtitle tracks, volume, mute."""
    out = {'audio': [], 'subtitle': [], 'audio_current': -1, 'subtitle_current': -1,
           'subtitle_on': False, 'muted': False, 'chapters': 0}
    app = result('Application.GetProperties', {'properties': ['volume', 'muted']})
    out['volume'] = app.get('volume')
    out['muted'] = bool(app.get('muted'))
    pid = _player_id()
    if pid is None:
        return out
    p = result('Player.GetProperties', {'playerid': pid, 'properties': [
        'audiostreams', 'currentaudiostream', 'subtitles', 'currentsubtitle', 'subtitleenabled']})

    def tracks(rows):
        res = []
        for s in rows or []:
            label = ' · '.join(x for x in (s.get('language'), s.get('name'), s.get('codec')) if x)
            res.append({'index': s.get('index', 0), 'label': label or '%s %s' % (lib.T('Sáv'), s.get('index', 0))})
        return res
    out['audio'] = tracks(p.get('audiostreams'))
    out['subtitle'] = tracks(p.get('subtitles'))
    out['audio_current'] = (p.get('currentaudiostream') or {}).get('index', -1)
    out['subtitle_current'] = (p.get('currentsubtitle') or {}).get('index', -1)
    out['subtitle_on'] = bool(p.get('subtitleenabled'))
    return out


# ----------------------------------------------- data of the playing title ---
_EXTRA = {}

# TMDb Helper service window properties (Window(Home).Property(TMDbHelper.Player.*)),
# which skins also use for ratings: property -> (app source name, scale factor)
_HELPER = (('IMDb_Rating', 'imdb', 1), ('TMDb_Rating', 'tmdb', 1), ('Trakt_Rating', 'trakt', 1),
           ('Letterboxd_Rating', 'letterboxd', 2), ('MetaCritic_Rating', 'metacritic', 1),
           ('MetaCriticUser_Rating', 'metacriticuser', 1), ('RottenTomatoes_Rating', 'rottentomatoes', 1),
           ('RottenTomatoes_UserMeter', 'popcorn', 1), ('RogerEbert_Rating', 'rogerebert', 2.5),
           ('MyAnimeList_Rating', 'myanimelist', 1), ('MDBList_Rating', 'mdblist', 1))


def helper_ratings():
    """Ratings filled in by TMDb Helper, scaled to 0-10."""
    out = {}
    for prop, name, mult in _HELPER:
        raw = (xbmc.getInfoLabel('Window(Home).Property(TMDbHelper.Player.%s)' % prop) or '').strip()
        m = __import__('re').search(r'\d+(?:[.,]\d+)?', raw)
        if not m:
            continue
        v = float(m.group(0).replace(',', '.'))
        if v > 10:           # percentage (RT, Metacritic, MDBList)
            v /= 10.0
        elif mult != 1 and v <= 5:
            v *= mult
        if 0 < v <= 10:
            out[name] = {'source': name, 'rating': round(v, 1), 'votes': 0}
    return out


# --------------------------------------------------------- MDBList (optional) ---
_MDB_FILE = os.path.join(xbmcvfs.translatePath('special://profile/addon_data/service.cb1.ppi/'), 'mdblist.json')
_MDB_TTL = 7 * 86400      # lifetime of a successful hit
_MDB_RETRY = 3600         # retry delay after an error / no data
_MDB = {}                 # 'movie:tt123' -> [time, [ratings]]
_MDB_BUSY = set()
_MDB_LOCK = threading.Lock()
_MDB_LOADED = []


def _mdb_load():
    if _MDB_LOADED:
        return
    _MDB_LOADED.append(1)
    try:
        with open(_MDB_FILE, encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            _MDB.update(data)
    except (OSError, ValueError):
        pass


def _mdb_save():
    try:
        os.makedirs(os.path.dirname(_MDB_FILE), exist_ok=True)
        with open(_MDB_FILE, 'w', encoding='utf-8') as fh:
            json.dump(_MDB, fh)
    except OSError:
        pass


def _mdb_key():
    try:
        return (lib.ADDON.getSetting('mdblist_key') or '').strip()
    except Exception:
        return ''


def _mdb_id(kind, uid):
    """(provider, id) from the Kodi uniqueid dict."""
    uid = uid if isinstance(uid, dict) else {}
    for prov in ('imdb', 'tmdb'):
        v = str(uid.get(prov) or '').strip()
        if v and (prov == 'tmdb' and v.isdigit() or prov == 'imdb' and v.startswith('tt')):
            return prov, v
    return None


def _mdb_norm(item):
    """MDBList rating row -> (app source name, 0-10 value) or None."""
    name = _ALIAS.get(str(item.get('source') or '').strip().lower())
    if not name:
        return None
    score, value = item.get('score'), item.get('value')
    try:
        if score is not None and float(score) > 0:
            v = float(score) / 10.0
        elif value is not None and float(value) > 0:
            v = float(value)
            if name == 'rogerebert':
                v *= 2.5
            elif name == 'letterboxd':
                v *= 2
            elif v > 10:
                v /= 10.0
        else:
            return None
    except (TypeError, ValueError):
        return None
    return (name, round(v, 1)) if 0 < v <= 10 else None


def _mdb_fetch(ckey, kind, prov, pid, key):
    out = []
    try:
        media = 'show' if kind == 'tvshow' else 'movie'
        url = 'https://api.mdblist.com/%s/%s/%s?apikey=%s' % (prov, media, pid, quote(key))
        req = Request(url, headers={'User-Agent': 'service.cb1.ppi'})
        with urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        seen = set()
        for it in data.get('ratings') or []:
            n = _mdb_norm(it) if isinstance(it, dict) else None
            if n and n[0] not in seen:
                seen.add(n[0])
                out.append({'source': n[0], 'rating': n[1],
                            'votes': int(it.get('votes') or 0) if str(it.get('votes') or '0').isdigit() else 0})
    except Exception as exc:  # network, key, format - not fatal
        lib.log('MDBList: %s' % exc, xbmc.LOGDEBUG)
    with _MDB_LOCK:
        _MDB[ckey] = [time.time(), out]
        _mdb_save()
        _MDB_BUSY.discard(ckey)
    bump()   # the app gets a new list on its next request


def mdb_ratings(kind, uid, block):
    key = _mdb_key()
    ident = _mdb_id(kind, uid)
    if not key or not ident:
        return []
    ckey = '%s:%s:%s' % (kind, ident[0], ident[1])
    with _MDB_LOCK:
        _mdb_load()
        hit = _MDB.get(ckey)
        age = time.time() - hit[0] if hit else None
        fresh = hit and age < (_MDB_TTL if hit[1] else _MDB_RETRY)
        if fresh or ckey in _MDB_BUSY:
            return list(hit[1]) if hit else []
        _MDB_BUSY.add(ckey)
    if block:
        _mdb_fetch(ckey, kind, ident[0], ident[1], key)
    else:
        threading.Thread(target=_mdb_fetch, args=(ckey, kind, ident[0], ident[1], key), daemon=True).start()
    with _MDB_LOCK:
        hit = _MDB.get(ckey)
    return list(hit[1]) if hit else []


def with_mdblist(rows, kind, uid, block=False):
    """Extend the existing (library) ratings with MDBList sources."""
    found = {r['source']: r for r in rows}
    for r in mdb_ratings(kind, uid, block):
        found.setdefault(r['source'], r)
    return sorted(found.values(), key=lambda r: (_ORDER.get(r['source'], len(_ORDER)), r['source']))[:25]


def merged_ratings(kodi_ratings, kind='', uid=None):
    """Kodi library ratings plus TMDb Helper sources (the library wins)."""
    found = {r['source']: r for r in rating_list(kodi_ratings)}
    for name, r in helper_ratings().items():
        found.setdefault(name, r)
    return with_mdblist(list(found.values()), kind, uid)


def playing_extras(kind, dbid):
    """Ratings etc. of the playing library item for the snapshot 'media' field."""
    key = (kind, dbid, LIB_REV)
    hit = _EXTRA.get('k')
    if hit and hit[0] == key:
        out = dict(hit[1])
        if out:  # TMDb Helper values may arrive later
            out['ratings'] = merged_ratings(hit[2][0], kind, hit[2][1])
        return out
    out = {}
    if kind == 'movie':
        r = result('VideoLibrary.GetMovieDetails', {'movieid': dbid, 'properties': [
            'ratings', 'userrating', 'mpaa', 'top250', 'tagline', 'director', 'writer', 'studio',
            'cast', 'genre', 'uniqueid']}).get('moviedetails', {})
    elif kind == 'episode':
        r = result('VideoLibrary.GetEpisodeDetails', {'episodeid': dbid, 'properties': [
            'ratings', 'userrating', 'director', 'writer', 'cast']}).get('episodedetails', {})
    else:
        r = {}
    if r:
        cast = r.get('cast') or []
        out = {'ratings': merged_ratings(r.get('ratings'), kind, r.get('uniqueid')), 'mpaa': r.get('mpaa', ''),
               'userrating': r.get('userrating') or 0, 'top250': r.get('top250') or 0,
               'tagline': r.get('tagline', ''), 'directors': [], 'writers': [],
               'studios': (r.get('studio') or [])[:1], 'genres': r.get('genre') or [],
               'cast': [], 'roles': [], 'cast_more': False}
    _EXTRA['k'] = (key, out, (r.get('ratings'), r.get('uniqueid')) if r else None)
    return out


# ----------------------------------------------------- audio from the player ---
_ACODEC = {'ac3': 'Dolby Digital', 'eac3': 'Dolby Digital+', 'eac3_ddp_atmos': 'Dolby Digital+',
           'truehd': 'Dolby TrueHD', 'truehd_atmos': 'Dolby TrueHD', 'dtshd_ma': 'DTS-HD MA',
           'dtshd_ma_x': 'DTS-HD MA', 'dtshd_ma_x_imax': 'DTS-HD MA', 'dtshd_hra': 'DTS-HD HRA',
           'dts': 'DTS', 'dca': 'DTS', 'aac': 'AAC', 'flac': 'FLAC', 'opus': 'Opus', 'mp3': 'MP3',
           'pcm': 'PCM', 'pcm_bluray': 'PCM', 'vorbis': 'Vorbis'}
_ALAYOUT = {1: '1.0', 2: '2.0', 3: '2.1', 4: '4.0', 5: '5.0', 6: '5.1', 7: '6.1', 8: '7.1', 9: '8.1', 10: '9.1'}


def audio_group():
    """The "audio" group; the app draws the audio codec labels from it (row audio.32045)."""
    codec = (xbmc.getInfoLabel('VideoPlayer.AudioCodec') or '').strip().lower()
    if not codec:
        return None
    try:
        ch = int(xbmc.getInfoLabel('VideoPlayer.AudioChannels') or 0)
    except ValueError:
        ch = 0
    layout = _ALAYOUT.get(ch, '')
    name = _ACODEC.get(codec, codec.upper())
    mark = ''
    if 'atmos' in codec:
        mark = 'Atmos'
    elif codec in ('dtshd_ma_x', 'dtshd_ma_x_imax'):
        mark = 'DTS:X'
    rows = [{'id': 'audio.32045', 'label': lib.T('Kodek'), 'value': (name + ' ' + layout).strip(), 'detail': mark}]
    lang = (xbmc.getInfoLabel('VideoPlayer.AudioLanguage') or '').strip()
    if lang:
        rows.append({'id': 'language', 'label': lib.T('Nyelv'), 'value': lang, 'detail': ''})
    rate = (xbmc.getInfoLabel('Player.Process(audiosamplerate)') or '').strip()
    if rate:
        rows.append({'id': 'samplerate', 'label': lib.T('Mintavétel'), 'value': rate, 'detail': ''})
    bits = (xbmc.getInfoLabel('Player.Process(audiobitspersample)') or '').strip()
    if bits:
        rows.append({'id': 'bits', 'label': lib.T('Bitmélység'), 'value': bits, 'detail': ''})
    return {'id': 'audio', 'title': lib.T('Hang'), 'rows': rows}
