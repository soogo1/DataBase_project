import sqlite3
import requests
from flask import Flask, jsonify, render_template, request
from threading import Timer



app = Flask(__name__)

# 공공데이터홈페이지에서 신청해서 받은 인증키
API_KEY = "981ad154432a25b08b52952e4462dbfde444d30f5972547dd15e7eef8e34fb3d"

# SQLite DB 파일 경로
DB_PATH = "air_quality.db"

# 전국 시·도 목록
ALL_SIDO = [
    "서울", "인천", "경기", "부산", "대구", "광주", "대전", "울산", "세종",
    "강원", "충남", "충북", "전남", "전북", "경남", "경북", "제주"
]


def clean_value(v):
    """'-', None, '' 같은 값은 None 처리."""
    if v is None or v == "-" or v == "":
        return None
    try:
        return int(v)
    except:
        return None


def save_sido_data(sido):
    """특정 시·도의 미세먼지 데이터를 DB에 저장."""

    url = (
        "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/"
        "getCtprvnRltmMesureDnsty"
        f"?serviceKey={API_KEY}"
        "&returnType=json"
        f"&sidoName={sido}"
        "&numOfRows=100"
        "&ver=1.3"
    )

    response = requests.get(url)
    data = response.json()
    items = data['response']['body']['items']

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for item in items:
        station = item.get('stationName')
        sido_name = item.get('sidoName')
        time = item.get('dataTime')

        pm10 = clean_value(item.get('pm10Value'))

        # PM25 정보는 데이터에 없는것 같음
        # 한국 공공 데이터에는 자주 비어있다고 함
        # 근데 24시간 평균은 제공하길래 만들어봄
        pm25_raw = item.get('pm25Value')

        # 실시간 값이 없으면 24시간 평균 탐색
        if pm25_raw in [None, "-", ""]:
            pm25_raw = item.get('pm25Value24')

        # 그래도 없으면 24시간 평균 다른 이름 필드 탐색
        if pm25_raw in [None, "-", ""]:
            pm25_raw = item.get('pm25Value24h')

        pm25 = clean_value(pm25_raw)

        # DB 삽입
        cur.execute("""
            INSERT INTO air_quality (station, sido, dataTime, pm10, pm25)
            VALUES (?, ?, ?, ?, ?)
        """, (station, sido_name, time, pm10, pm25))

    conn.commit()
    conn.close()

    return len(items)

@app.route('/save_all') # 수집한 데이터를 DB에 저장하라 (과제 조건있었음)
def save_all():
    """전국 모든 시·도 데이터를 한 번에 가져와 저장하는 API."""
    total_saved = 0

    for sido in ALL_SIDO:
        count = save_sido_data(sido)
        total_saved += count

    return jsonify({
        "saved_total": total_saved,
        "regions": len(ALL_SIDO)
    })


def auto_update():
    """서버가 1시간마다 전국 데이터를 자동으로 업데이트하도록 설정."""
    print("[자동 업데이트] 전국 미세먼지 데이터 저장 시작")

    try:
        # 내부에서 save_all 실행 
        requests.get("http://127.0.0.1:5000/save_all")
        print("[자동 업데이트] 완료")
    except Exception as e:
        print("[자동 업데이트 오류]", e)

    t = Timer(3600, auto_update)
    t.daemon = True
    t.start()



 # 저장된 내용을 조회하는 기능을 구현하라 (과제 조건있었음)
 # 전체 데이터 조회하는게 양이 너무 많아서 너무 느림, 그래서 쪼개버림
 # url 칠때 /list?page=N 해가지고 페이지를 나눴음
@app.route("/list")  
def list_data():
    # 기본은 1페이지
    page = int(request.args.get("page", 1))
    per_page = 100  # 페이지당 100개
    offset = (page - 1) * per_page

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 한 페이지에 필요한 것보다 1개 더 읽어서, 다음 페이지가 있는지 판단
    cur.execute("""
        SELECT station, sido, dataTime, pm10, pm25
        FROM air_quality
        ORDER BY dataTime DESC
        LIMIT ? OFFSET ?
    """, (per_page + 1, offset))

    rows = cur.fetchall()
    conn.close()

    # 다음 페이지가 있는지 여부
    has_next = len(rows) > per_page
    # 실제로 화면에 보여줄 것은 per_page 개수까지만
    rows = rows[:per_page]

    return render_template(
        "list.html",
        rows=rows,
        page=page,
        has_next=has_next
    )


if __name__ == '__main__':
    # 서버 시작 시 자동 업데이트 기능 실행
    # auto_update()
    app.run(debug=True)
