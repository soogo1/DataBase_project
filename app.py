import sqlite3
import requests
from flask import Flask, jsonify

app = Flask(__name__)

API_KEY = "981ad154432a25b08b52952e4462dbfde444d30f5972547dd15e7eef8e34fb3d" # 신청해서 받은 일반 인증키

# DB 경로 (SQLite 로 만든거)
DB_PATH = "air_quality.db"   

# 전국 시·도 목록
ALL_SIDO = [
    "서울", "인천", "경기", "부산", "대구", "광주", "대전", "울산", "세종",
    "강원", "충남", "충북", "전남", "전북", "경남", "경북", "제주"
]

@app.route('/save_all')
def save_all():
    total_saved = 0  # 총 저장 개수 표시를 위한 변수임

    for sido in ALL_SIDO:
        # 시·도별 API 주소 구성
        url = (
            "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/"
            "getCtprvnRltmMesureDnsty"
            f"?serviceKey={API_KEY}"
            "&returnType=json"
            f"&sidoName={sido}"
            "&numOfRows=100"
        )

        # 요청 및 JSON 파싱
        response = requests.get(url)
        data = response.json()
        items = data['response']['body']['items']

        # DB 연결
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 값 정리 함수
        def clean(v):
            if v is None or v == "-" or v == "":
                return None
            try:
                return int(v)
            except:
                return None

        # 데이터 저장
        for item in items:
            station = item.get('stationName')
            sido_name = item.get('sidoName')
            time = item.get('dataTime')
            pm10 = clean(item.get('pm10Value'))
            pm25 = clean(item.get('pm25Value'))

            cur.execute("""
                INSERT INTO air_quality (station, sido, dataTime, pm10, pm25)
                VALUES (?, ?, ?, ?, ?)
            """, (station, sido_name, time, pm10, pm25))

        conn.commit()
        conn.close()

        # 몇 개 저장됐는지 합산 홈페이지에서 보여주기
        total_saved += len(items)

    return jsonify({
        "saved_total": total_saved,
        "regions": len(ALL_SIDO)
    })


if __name__ == '__main__':
    app.run(debug=True)
