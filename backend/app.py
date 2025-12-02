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
        return float(v)       # 다양한 오염물질이 실수(소수점)일 수 있음
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

        # ★ 추가 오염물질 저장 (환경부 API에 포함됨)
        o3 = clean_value(item.get("o3Value"))
        no2 = clean_value(item.get("no2Value"))
        so2 = clean_value(item.get("so2Value"))
        co = clean_value(item.get("coValue"))
        khai = clean_value(item.get("khaiValue"))  # 통합대기지수

        # DB 삽입
        cur.execute("""
            INSERT INTO air_quality 
            (station, sido, dataTime, pm10, pm25, o3, no2, so2, co, khai)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (station, sido_name, time, pm10, pm25, o3, no2, so2, co, khai))

    conn.commit()
    conn.close()

    return len(items)


@app.route('/save_all')  # 수집한 데이터를 DB에 저장하라 (과제 조건있었음)
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
        SELECT station, sido, dataTime, pm10, pm25, o3, no2, so2, co, khai
        FROM air_quality
        ORDER BY dataTime DESC
        LIMIT ? OFFSET ?
    """, (per_page + 1, offset))

    rows = cur.fetchall()
    conn.close()

    # 다음 페이지가 있는지 여부
    has_next = len(rows) > per_page
    # 실제 화면에 보여줄 것은 per_page 개수까지만
    rows = rows[:per_page]

    return render_template(
        "list.html",
        rows=rows,
        page=page,
        has_next=has_next
    )

@app.route('/recommend_form')
def recommend_form():
    return render_template("recommend_form.html")

@app.route('/recommend')
def recommend():
    # 지역 + 측정소 + 사용자 특성
    sido = request.args.get("sido")
    station = request.args.get("station")
    age = request.args.get("age")
    bmi = request.args.get("bmi")
    gender = request.args.get("gender")
    fitness = request.args.get("fitness")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) 선택된 지역 + 측정소의 최신 대기질 1건
    cur.execute("""
        SELECT station, pm10, pm25, o3, no2, so2, co, khai, dataTime
        FROM air_quality
        WHERE sido = ?
          AND station = ?
        ORDER BY dataTime DESC
        LIMIT 1
    """, (sido, station))
    air = cur.fetchone()

    # 2) 운동 추천 
    cur.execute("""
        SELECT category, difficulty, exercise_name
        FROM exercise_plan
        WHERE age_group = ?
          AND bmi_level = ?
          AND gender = ?
          AND fitness_level = ?
        ORDER BY 
          difficulty ASC,
          CASE category
            WHEN '준비운동' THEN 1
            WHEN '본운동' THEN 2
            WHEN '마무리운동' THEN 3
            ELSE 4
          END
    """, (age, bmi, gender, fitness))

    rows = cur.fetchall()
    conn.close()

    return render_template(
        "recommend.html",
        sido=sido,
        station=station,
        air=air,
        rows=rows,
        age=age,
        bmi=bmi,
        gender=gender,
        fitness=fitness
    )


@app.route('/select_region')
def select_region():
    # 전국 시도 목록을 HTML로 보내줌
    sido_list = [
        "서울", "인천", "경기", "부산", "대구", "광주", "대전", "울산", "세종",
        "강원", "충남", "충북", "전남", "전북", "경남", "경북", "제주"
    ]
    return render_template("select_region.html", sido_list=sido_list)


@app.route('/air_quality')
def air_quality():
    sido = request.args.get("sido")
    # 선택된 측정소
    station = request.args.get("station")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) 해당 시/도의 측정소 목록 가져오기
    cur.execute("""
        SELECT DISTINCT station
        FROM air_quality
        WHERE sido = ?
        ORDER BY station
    """, (sido,))
    stations = [row[0] for row in cur.fetchall()]

    # 2) 선택된 측정소가 있으면 그 측정소의 최신 데이터 1건 조회
    data = None
    if station:
        cur.execute("""
            SELECT station, pm10, pm25, o3, no2, so2, co, khai, dataTime
            FROM air_quality
            WHERE sido = ?
              AND station = ?
            ORDER BY dataTime DESC
            LIMIT 1
        """, (sido, station))
        data = cur.fetchone()

    conn.close()

    return render_template(
        "air_quality.html",
        sido=sido,
        stations=stations,
        selected_station=station,
        data=data
    )




if __name__ == '__main__':
    # 서버 시작 시 자동 업데이트 기능 실행 / 뭔가 이거 있을때 마다 홈페이지 로딩이 안되서 주석처리
    # 실시간 데이터 받아오는건 나중에 해결해봐야될듯 , 무슨 문제가 있는것 같음
    # auto_update()
    app.run(debug=True)
