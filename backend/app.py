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

    # 1) API 호출
    try:
        response = requests.get(url, timeout=5)
    except Exception as e:
        print(f"[{sido}] API 요청 실패:", e)
        return 0

    # 2) HTTP 상태 코드 확인
    if response.status_code != 200:
        print(f"[{sido}] API 응답 코드 이상:", response.status_code)
        return 0

    # 3) JSON 파싱 예외 처리
    try:
        data = response.json()
    except ValueError:
        print(f"[{sido}] JSON 파싱 실패, 처음 200글자:", response.text[:200])
        return 0

    # 실제 측정 데이터 없으면 종료
    if "response" not in data or "body" not in data["response"]:
        print(f"[{sido}] 응답 구조 이상:", data)
        return 0

    items = data["response"]["body"]["items"]
    # ---- 여기서부터는 기존 코드 그대로 ----
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for item in items:
        station = item.get('stationName')
        sido_name = item.get('sidoName')
        time = item.get('dataTime')

        pm10 = clean_value(item.get('pm10Value'))

        pm25_raw = item.get('pm25Value')
        if pm25_raw in [None, "-", ""]:
            pm25_raw = item.get('pm25Value24')
        if pm25_raw in [None, "-", ""]:
            pm25_raw = item.get('pm25Value24h')

        pm25 = clean_value(pm25_raw)

        o3 = clean_value(item.get("o3Value"))
        no2 = clean_value(item.get("no2Value"))
        so2 = clean_value(item.get("so2Value"))
        co = clean_value(item.get("coValue"))
        khai = clean_value(item.get("khaiValue"))

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
    print("[자동 업데이트] 전국 미세먼지 데이터 저장 시작 (v2)")

    try:
        total_saved = 0
        for sido in ALL_SIDO:
            total_saved += save_sido_data(sido)

        print(f"[자동 업데이트] 완료: 총 {total_saved}개 저장")
    except Exception as e:
        print("[자동 업데이트 오류]", e)

    # 3600초(1시간) 마다 반복
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

def decide_place(air):
    """대기질 정보를 보고 실내/실외 운동 권장 문구를 만든다."""
    if not air:
        return ("정보 부족", "대기질 데이터를 찾을 수 없어, 안전하게 실내 운동을 권장합니다.")

    # air = (station, pm10, pm25, o3, no2, so2, co, khai, dataTime)
    pm10 = air[1]
    pm25 = air[2]
    khai = air[7]

    # 우선순위: 통합대기지수(KHAI) > PM2.5 > PM10
    score = None
    if khai is not None:
        score = khai
    elif pm25 is not None:
        score = pm25
    elif pm10 is not None:
        score = pm10

    if score is None:
        return ("정보 부족", "측정값이 부족해 실내/외를 판단하기 어려우므로, 실내 운동을 권장합니다.")

    # KHAI 기준: 0~50 좋음, 51~100 보통, 101~250 나쁨, 251이상 매우나쁨
    # 내가 임의로 설정 계산한 측정 기준 
    if score <= 50:
        return ("실외 운동 최적",
                "대기질이 매우 좋아서 실외 러닝, 자전거 등 야외 운동을 적극 추천합니다.")
    elif score <= 100:
        return ("실외 운동 가능",
                "야외 운동이 가능하지만, 장시간 활동 시에는 마스크 착용을 권장합니다.")
    elif score <= 150:
        return ("실내 운동 권장",
                "대기질이 다소 나빠 실외 장시간 운동은 피하고, 실내 스트레칭·맨몸운동을 추천합니다.")
    else:
        return ("실내 운동만 권장",
                "대기질이 매우 나빠 야외 운동은 피하고, 실내에서 가벼운 운동만 하는 것을 권장합니다.")


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

    place_title, place_comment = decide_place(air)


    # 2) 운동 추천 (1차: 모든 조건 정확히 일치)
    #    템플릿에서 (cat, diff, name) 으로 받으니까
    #    SELECT 순서를 category, difficulty, exercise_name 으로 맞춤
    cur.execute("""
        SELECT 
            category,          -- 카테고리(준비/본/마무리)
            difficulty,        -- 난이도
            exercise_name      -- 운동명
        FROM exercise_plan
        WHERE TRIM(age_group)     = TRIM(?)
          AND TRIM(bmi_level)     = TRIM(?)
          AND TRIM(gender)        = TRIM(?)
          AND TRIM(fitness_level) = TRIM(?)
        ORDER BY
          difficulty ASC,
          CASE TRIM(category)
            WHEN '준비운동'   THEN 1
            WHEN '본운동'     THEN 2
            WHEN '마무리운동' THEN 3
            ELSE 4
          END
    """, (age, bmi, gender, fitness))
    rows = cur.fetchall()

    if not rows:
        cur.execute("""
            SELECT 
                category,
                difficulty,
                exercise_name
            FROM exercise_plan
            WHERE TRIM(age_group) = TRIM(?)
              AND TRIM(bmi_level) = TRIM(?)
              AND TRIM(gender)    = TRIM(?)
            ORDER BY
              difficulty ASC,
              CASE TRIM(category)
                WHEN '준비운동'   THEN 1
                WHEN '본운동'     THEN 2
                WHEN '마무리운동' THEN 3
                ELSE 4
              END
        """, (age, bmi, gender))
        rows = cur.fetchall()

    conn.close()

    return render_template(
        "recommend.html",
        sido=sido,
        station=station,
        air=air,
        exercises=rows,   # 템플릿 변수 이름을 exercises로 맞춤 / 이게 문제였음
        age=age,
        bmi=bmi,
        gender=gender,
        fitness=fitness,
        place_title=place_title,
        place_comment = place_comment
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
    # 서버 시작 시 최초 1회만 자동 업데이트 실행
    auto_update()
    # reloader 끄기 (두 번 실행 방지)
    app.run(debug=True, use_reloader=False)
