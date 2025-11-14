import sqlite3
import requests
from flask import Flask, jsonify

app = Flask(__name__)

API_KEY = "981ad154432a25b08b52952e4462dbfde444d30f5972547dd15e7eef8e34fb3d" # 공공데이터 일반 인증키

# DB 경로 (SQLite 로 만든거)
DB_PATH = "air_quality.db"   

@app.route('/save')
def save_data():
    # 공공데이터 API 요청 주소 구성
    url = (
        "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/"
        "getCtprvnRltmMesureDnsty"
        f"?serviceKey={API_KEY}"
        "&returnType=json"
        "&sidoName=인천"
        "&numOfRows=100"
    )

    # API 요청 및 JSON 파싱
    response = requests.get(url)
    data = response.json()

    # 필요한 실제 측정값 리스트
    items = data['response']['body']['items']

    # SQLite DB 연결
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 미세먼지 수치가 없는 경우가 있어서 정리용 함수 작성
    def clean(value):
        # 값이 비어있거나 "-"처럼 수치가 아닌 경우 None 처리
        if value is None or value == "-" or value == "":
            return None
        try:
            return int(value)   # 정상 숫자면 정수로 변환
        except:
            return None         # 변환 실패도 None

    # 각 측정 데이터를 DB에 저장
    for item in items:
        station = item.get('stationName')
        sido = item.get('sidoName')
        time = item.get('dataTime')

        # 측정값 중 일부는 빠져 있는 경우가 있어 .get 사용
        pm10 = clean(item.get('pm10Value'))
        pm25 = clean(item.get('pm25Value'))

        # SQLite 테이블에 삽입
        cur.execute("""
            INSERT INTO air_quality (station, sido, dataTime, pm10, pm25)
            VALUES (?, ?, ?, ?, ?)
        """, (station, sido, time, pm10, pm25))

    # 변경사항 저장 후 종료
    conn.commit()
    conn.close()

    # 저장된 개수 확인용 응답
    return jsonify({"saved": len(items)})

if __name__ == '__main__':
    app.run(debug=True)
