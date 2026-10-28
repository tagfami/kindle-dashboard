#!/usr/bin/env python3
"""Kindle Paperwhite（第7世代）縦置き用ダッシュボードを生成する。

天気: Open-Meteo / ニュース: NHKニュースRSS / 市況: Yahoo Finance
出力: docs/index.html（Kindleの体験版ブラウザで開くページ）

使い方:
  python3 generate.py            # 実データを取得して生成
  python3 generate.py --sample   # sample_data.json で生成（見た目の確認用）
標準ライブラリのみで動作します。
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

# ---- 設定 -------------------------------------------------------------
LOCATION_NAME = "西東京市"
LAT, LON = 35.7256, 139.5383
NEWS_RSS = "https://www3.nhk.or.jp/rss/news/cat0.xml"
NEWS_COUNT = 5
MARKETS = [  # (表示名, Yahoo Financeのシンボル, 単位, 小数桁)
    ("ドル円", "JPY=X", "円", 2),
    ("日経平均", "^N225", "円", 0),
    ("NYダウ", "^DJI", "ドル", 0),
]
REFRESH_SECONDS = 300  # Kindle側でページを読み直す間隔
JST = dt.timezone(dt.timedelta(hours=9))
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
UA = {"User-Agent": "Mozilla/5.0 (kindle-dashboard)"}

WEEK = "月火水木金土日"
WIND_DIRS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東",
             "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]


# ---- データ取得 -------------------------------------------------------
def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_weather():
    q = ("latitude={lat}&longitude={lon}&timezone=Asia%2FTokyo&wind_speed_unit=ms"
         "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
         "weather_code,wind_speed_10m,wind_direction_10m,is_day"
         "&hourly=temperature_2m,precipitation_probability,weather_code,is_day"
         "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
         "precipitation_probability_max&forecast_days=5").format(lat=LAT, lon=LON)
    return json.loads(http_get("https://api.open-meteo.com/v1/forecast?" + q))


def fetch_news():
    root = ET.fromstring(http_get(NEWS_RSS))
    titles = [i.findtext("title", "").strip() for i in root.iter("item")]
    return [t for t in titles if t][:NEWS_COUNT]


def fetch_markets():
    out = []
    for name, sym, unit, digits in MARKETS:
        try:
            url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
                   + urllib.request.quote(sym) + "?range=1d&interval=5m")
            meta = json.loads(http_get(url))["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            out.append({"name": name, "price": price, "prev": prev, "unit": unit,
                        "digits": digits, "time": meta.get("regularMarketTime")})
        except Exception as e:  # 1銘柄の失敗で全体を止めない
            print("market error", sym, e, file=sys.stderr)
    return out


def load_data(sample):
    if sample:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data.json")
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        d["now"] = dt.datetime.fromisoformat(d["now"]).replace(tzinfo=JST)
        return d
    d = {"now": dt.datetime.now(JST), "weather": None, "news": [], "markets": []}
    for key, fn in (("weather", fetch_weather), ("news", fetch_news), ("markets", fetch_markets)):
        try:
            d[key] = fn()
        except Exception as e:
            print(key, "error", e, file=sys.stderr)
    return d


# ---- 天気コード → 表示 -------------------------------------------------
def wmo(code):
    """WMO天気コードを (日本語, アイコン種別) に変換"""
    c = int(code)
    if c == 0: return "快晴", "sun"
    if c == 1: return "晴れ", "sun"
    if c == 2: return "晴れ時々曇り", "partly"
    if c == 3: return "曇り", "cloud"
    if c in (45, 48): return "霧", "fog"
    if c in (51, 53, 55, 56, 57): return "霧雨", "drizzle"
    if c in (61, 66): return "小雨", "drizzle"
    if c in (63, 80, 81): return "雨", "rain"
    if c in (65, 67, 82): return "大雨", "rain"
    if c in (71, 73, 75, 77, 85, 86): return "雪", "snow"
    if c in (95, 96, 99): return "雷雨", "thunder"
    return "—", "cloud"


CLOUD = '<path d="M17 38h28a9 9 0 0 0 0-18 13 13 0 0 0-25-3 10.5 10.5 0 0 0-3 21z"/>'


def icon(kind, size, night=False):
    """e-ink向けの線画アイコン（インラインSVG）"""
    sun_rays = "".join(
        '<line x1="{:.1f}" y1="{:.1f}" x2="{:.1f}" y2="{:.1f}"/>'.format(*p) for p in [
            (32, 6, 32, 12), (32, 52, 32, 58), (6, 32, 12, 32), (52, 32, 58, 32),
            (13.6, 13.6, 17.9, 17.9), (46.1, 46.1, 50.4, 50.4),
            (13.6, 50.4, 17.9, 46.1), (46.1, 17.9, 50.4, 13.6)])
    moon = '<path d="M38 10a20 20 0 1 0 16 30 16 16 0 0 1-16-30z"/>'
    if kind == "sun":
        body = moon if night else '<circle cx="32" cy="32" r="11"/>' + sun_rays
    elif kind == "partly":
        if night:
            small = '<path d="M26 6a12 12 0 1 0 12 17 9 9 0 0 1-12-17z"/>'
        else:
            small = ('<circle cx="22" cy="20" r="8"/><line x1="22" y1="4" x2="22" y2="8"/>'
                     '<line x1="6" y1="20" x2="10" y2="20"/><line x1="10.7" y1="8.7" x2="13.5" y2="11.5"/>'
                     '<line x1="33.3" y1="8.7" x2="30.5" y2="11.5"/>')
        body = small + '<g transform="translate(6,12)" fill="#fff">' + CLOUD + '</g>'
    elif kind == "cloud":
        body = '<g transform="translate(0,6)">' + CLOUD + '</g>'
    elif kind == "fog":
        body = ('<g transform="translate(0,-4)">' + CLOUD + '</g>'
                '<line x1="12" y1="44" x2="52" y2="44"/><line x1="16" y1="52" x2="48" y2="52"/>')
    elif kind in ("rain", "drizzle"):
        n = 3 if kind == "rain" else 2
        drops = "".join('<line x1="{0}" y1="46" x2="{1}" y2="56"/>'.format(22 + i * 10, 19 + i * 10)
                        for i in range(n))
        body = '<g transform="translate(0,-2)">' + CLOUD + '</g>' + drops
    elif kind == "snow":
        flakes = "".join('<circle cx="{}" cy="{}" r="2.2" fill="#000"/>'.format(x, y)
                         for x, y in [(22, 48), (32, 54), (42, 48)])
        body = '<g transform="translate(0,-2)">' + CLOUD + '</g>' + flakes
    else:  # thunder
        body = ('<g transform="translate(0,-2)">' + CLOUD + '</g>'
                '<path d="M33 40l-6 10h7l-4 10" />')
    return ('<svg width="{s}" height="{s}" viewBox="0 0 64 64" fill="none" stroke="#000" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round">{b}</svg>'
            ).format(s=size, b=body)


UMBRELLA = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#000" '
            'stroke-width="2.4" stroke-linecap="round"><path d="M3 12a9 9 0 0 1 18 0z" fill="#000"/>'
            '<path d="M12 12v7a2 2 0 0 0 4 0"/></svg>')


# ---- HTML組み立て -------------------------------------------------------
def esc(s):
    return html.escape(str(s))


def fmt_num(v, digits):
    return "{:,.{d}f}".format(v, d=digits)


def section_current(w):
    if not w:
        return '<div class="nodata">天気データを取得できませんでした</div>'
    c, d = w["current"], w["daily"]
    label, kind = wmo(c["weather_code"])
    wind_dir = WIND_DIRS[int((c["wind_direction_10m"] + 11.25) % 360 // 22.5)]
    pop = d["precipitation_probability_max"][0]
    return """
<div class="tag">屋外・{loc}</div>
<table class="cur"><tr>
 <td class="cur-ic">{ic}</td>
 <td><div class="cur-temp">{t:.1f}<span class="u">℃</span></div><div class="cur-label">{label}</div></td>
</tr></table>
<table class="cur-sub">
 <tr><td><span class="k">最高</span>{hi:.0f}°</td><td><span class="k">最低</span>{lo:.0f}°</td><td><span class="k">降水</span>{pop}%</td></tr>
 <tr><td><span class="k">体感</span>{feel:.0f}°</td><td><span class="k">湿度</span>{hum:.0f}%</td><td><span class="k">風</span>{wd} {ws:.0f}m/s</td></tr>
</table>""".format(
        loc=esc(LOCATION_NAME), ic=icon(kind, 96, night=not c.get("is_day", 1)),
        t=c["temperature_2m"], label=esc(label), hi=d["temperature_2m_max"][0],
        lo=d["temperature_2m_min"][0], pop="—" if pop is None else int(pop),
        feel=c["apparent_temperature"], hum=c["relative_humidity_2m"], wd=wd_safe(wind_dir),
        ws=c["wind_speed_10m"])


def wd_safe(s):
    return esc(s)


def section_hourly(w, now):
    if not w:
        return ""
    h = w["hourly"]
    times = [dt.datetime.fromisoformat(t).replace(tzinfo=JST) for t in h["time"]]
    start = (now + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    while start.hour % 3:
        start += dt.timedelta(hours=1)
    cells = []
    for k in range(6):
        target = start + dt.timedelta(hours=3 * k)
        if target not in times:
            break
        i = times.index(target)
        _, kind = wmo(h["weather_code"][i])
        pop = h["precipitation_probability"][i]
        cells.append('<td><div class="h-time">{hr}時</div>{ic}<div class="h-temp">{t:.0f}°</div>'
                     '<div class="h-pop">{u}{p}%</div></td>'.format(
                         hr=target.hour, ic=icon(kind, 64, night=not h["is_day"][i]),
                         t=h["temperature_2m"][i], u=UMBRELLA, p=0 if pop is None else int(pop)))
    return '<table class="hourly"><tr>' + "".join(cells) + "</tr></table>"


def section_daily(w, now):
    if not w:
        return ""
    d = w["daily"]
    rows = []
    for i, day in enumerate(d["time"]):
        date = dt.date.fromisoformat(day)
        if date <= now.date():
            continue
        if len(rows) == 3:
            break
        _, kind = wmo(d["weather_code"][i])
        pop = d["precipitation_probability_max"][i]
        rows.append('<tr><td class="d-date">{m}/{dd}<span class="wk">({wk})</span></td><td class="d-ic">{ic}</td>'
                    '<td class="d-temp">{hi:.0f}° / {lo:.0f}°</td><td class="d-pop">{u}{p}%</td></tr>'.format(
                        m=date.month, dd=date.day, wk=WEEK[date.weekday()], ic=icon(kind, 44),
                        hi=d["temperature_2m_max"][i], lo=d["temperature_2m_min"][i], u=UMBRELLA,
                        p="—" if pop is None else int(pop)))
    return ('<div class="h2">この先の天気</div><table class="daily">' + "".join(rows) + "</table>")


def section_markets(ms):
    if not ms:
        return '<div class="h2">マーケット</div><div class="nodata">市況データを取得できませんでした</div>'
    times = [m["time"] for m in ms if m.get("time")]
    stamp = ""
    if times:
        t = dt.datetime.fromtimestamp(max(times), JST)
        stamp = '<span class="h2-sub">{}/{} {:%H:%M}</span>'.format(t.month, t.day, t)
    rows = []
    for m in ms:
        diff = pct = None
        if m.get("prev"):
            diff = m["price"] - m["prev"]
            pct = diff / m["prev"] * 100
        if diff is None:
            chg = ""
        else:
            arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "±")
            chg = '{a}{d}<div class="pct">{p:+.2f}%</div>'.format(
                a=arrow, d=fmt_num(abs(diff), m["digits"] if m["digits"] else 0), p=pct)
        rows.append('<tr><td class="m-name">{n}</td><td class="m-price">{v}<span class="m-unit">{u}</span></td>'
                    '<td class="m-chg">{c}</td></tr>'.format(
                        n=esc(m["name"]), v=fmt_num(m["price"], m["digits"]), u=esc(m["unit"]), c=chg))
    return '<div class="h2">マーケット{}</div><table class="markets">{}</table>'.format(stamp, "".join(rows))


def section_news(news):
    if not news:
        return '<div class="h2">主要ニュース</div><div class="nodata">ニュースを取得できませんでした</div>'
    items = "".join('<li>{}</li>'.format(esc(t)) for t in news[:NEWS_COUNT])
    return '<div class="h2">主要ニュース<span class="h2-sub">NHKニュース</span></div><ul class="news">{}</ul>'.format(items)


CSS = """
*{margin:0;padding:0;box-sizing:border-box;-webkit-box-sizing:border-box}
html,body{background:#fff;color:#000;overflow:hidden;width:100%;height:100%}
body{font-family:"Noto Sans CJK JP","Noto Sans JP","Hiragino Sans","Hiragino Kaku Gothic ProN",sans-serif}
#board{position:absolute;left:0;top:0;width:1072px;height:1240px;background:#fff;padding:20px 28px 0;
 -webkit-transform-origin:0 0;transform-origin:0 0}
table{border-collapse:collapse}
.top{width:100%}
.top td{vertical-align:top}
.top-l{width:470px;border-right:3px solid #000}
.date{font-size:36px;font-weight:bold}
.clock{font-size:168px;font-weight:bold;line-height:1;letter-spacing:-4px;margin-top:4px}
.top-r{padding-left:28px}
.tag{display:inline-block;background:#000;color:#fff;font-size:24px;font-weight:bold;padding:3px 12px;letter-spacing:2px}
.cur{margin-top:6px}
.cur-ic{width:104px;vertical-align:middle}
.cur-temp{font-size:80px;font-weight:bold;line-height:1}
.cur-temp .u{font-size:36px;margin-left:4px}
.cur-label{font-size:34px;font-weight:bold;margin-top:2px}
.cur-sub{margin-top:6px;font-size:26px}
.cur-sub td{padding:1px 22px 1px 0;white-space:nowrap}
.k{font-size:21px;margin-right:5px}
.hourly{width:100%;margin-top:16px;border-top:3px solid #000;border-bottom:3px solid #000}
.hourly td{width:16.66%;text-align:center;padding:8px 0;border-left:1px solid #000}
.hourly td:first-child{border-left:none}
.h-time{font-size:30px;font-weight:bold}
.h-temp{font-size:42px;font-weight:bold;line-height:1.1}
.h-pop{font-size:25px}
.h-pop svg,.d-pop svg{margin:0 4px -1px 0}
.h2{font-size:32px;font-weight:bold;border-bottom:3px solid #000;padding-bottom:4px;margin-top:16px;white-space:nowrap}
.h2-sub{font-size:20px;font-weight:normal;margin-left:14px}
.mid{width:100%}
.mid td{vertical-align:top}
.mid-l{width:500px;padding-right:28px}
.daily,.markets{width:100%}
.daily td,.markets td{border-bottom:1px solid #000;padding:5px 0;font-size:30px;vertical-align:middle;height:64px;white-space:nowrap}
.d-date{font-weight:bold;width:150px;white-space:nowrap}
.wk{font-size:22px}
.d-ic{width:56px}
.d-ic svg{display:block}
.d-temp{font-weight:bold}
.d-pop{text-align:right;font-size:26px}
.news{list-style:none}
.news li{font-size:30px;line-height:1.35;padding:8px 0 8px 26px;border-bottom:1px solid #000;
 position:relative;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.news li:before{content:"";position:absolute;left:2px;top:24px;width:12px;height:12px;background:#000}
.m-name{font-size:24px;width:112px;padding-right:10px;white-space:nowrap}
.markets td.m-price{font-size:34px;font-weight:bold;white-space:nowrap;padding-left:12px}
.m-unit{font-size:19px;font-weight:normal;margin-left:2px}
.m-chg{text-align:right;font-size:25px;font-weight:bold;line-height:1.1;white-space:nowrap}
.pct{font-size:18px;font-weight:normal}
.foot{position:absolute;left:28px;right:28px;bottom:10px;font-size:19px;border-top:2px solid #000;padding-top:5px}
.foot .r{float:right}
.nodata{font-size:28px;padding:10px 0}
"""

JS = """
(function(){
 var W=1072,H=1240,WEEK='日月火水木金土';
 function pad(n){return n<10?'0'+n:''+n;}
 function tick(){
  var d=new Date(new Date().getTime()+9*3600000);
  document.getElementById('clock').innerHTML=d.getUTCHours()+':'+pad(d.getUTCMinutes());
  document.getElementById('date').innerHTML=d.getUTCFullYear()+'年'+(d.getUTCMonth()+1)+'月'+d.getUTCDate()+'日（'+WEEK.charAt(d.getUTCDay())+'）';
 }
 function fit(){
  var w=window.innerWidth||document.documentElement.clientWidth,h=window.innerHeight||document.documentElement.clientHeight;
  var s=Math.min(w/W,h/H);
  var t='scale('+s+')';
  var b=document.getElementById('board').style;
  b.webkitTransform=t;b.transform=t;
 }
 fit();window.onresize=fit;
 try{tick();setInterval(tick,30000);}catch(e){}
})();
"""


def build_html(d):
    now = d["now"]
    w = d.get("weather")
    date_str = "{}年{}月{}日（{}）".format(now.year, now.month, now.day, WEEK[now.weekday()])
    body = """
<div id="board">
 <table class="top"><tr>
  <td class="top-l"><div class="date" id="date">{date}</div><div class="clock" id="clock">{clock}</div></td>
  <td class="top-r">{current}</td>
 </tr></table>
 {hourly}
 <table class="mid"><tr><td class="mid-l">{daily}</td><td class="mid-r">{markets}</td></tr></table>
 {news}
 <div class="foot"><span>更新 {upd}</span><span class="r">天気: Open-Meteo ／ ニュース: NHK ／ 市況: Yahoo Finance</span></div>
</div>""".format(date=date_str, clock="{}:{:02d}".format(now.hour, now.minute),
                 current=section_current(w), hourly=section_hourly(w, now),
                 daily=section_daily(w, now), markets=section_markets(d.get("markets")),
                 news=section_news(d.get("news")),
                 upd="{}/{} {:%H:%M}".format(now.month, now.day, now))
    return """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kindle Dashboard</title><style>{css}</style></head>
<body>{body}<script>{js}</script></body></html>""".format(
        refresh=REFRESH_SECONDS, css=CSS, body=body, js=JS)


def main():
    sample = "--sample" in sys.argv
    d = load_data(sample)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_html(d))
    print("generated", os.path.join(OUT_DIR, "index.html"))


if __name__ == "__main__":
    main()
