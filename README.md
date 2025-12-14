# 대기질 기반 맞춤 운동 추천 웹 서비스

공공데이터포털의 실시간 대기질(Open API)과 운동 계획 CSV 데이터를 활용하여  
사용자의 지역 대기질 + 개인 특성(연령, BMI, 성별, 체력등급)에 맞춘 운동 루틴을 추천하는 웹 서비스입니다.

## 주요 기능

- 전국 시·도 및 측정소 선택 → 최신 대기질 정보 조회  
- 통합대기지수(KHAI)·미세먼지 등을 바탕으로 **실내 운동 / 실외 운동** 권장  
- 연령대, BMI 단계, 성별, 체력등급을 입력하면  
  - CSV에서 가져온 운동 DB를 이용해  
  - 난이도별로 준비운동 -> 본운동 -> 마무리운동 순서의 루틴을 추천

## 기술 스택

- 언어: Python 3  
- 웹 프레임워크: Flask (Jinja2 템플릿)  
- DBMS: SQLite  
- 주요 라이브러리: `flask`, `requests`, `sqlite3`

## 데이터베이스

- `air_quality`  
  - 공공데이터 Open API에서 가져온 실시간 대기질 저장  
  - 컬럼: 시·도, 측정소, 측정시간, PM10, PM2.5, O₃, NO₂, SO₂, CO, KHAI 등

- `exercise_plan`  
  - 운동 계획 CSV를 임포트한 기준 데이터  
  - 컬럼: 연령대, BMI 단계, 성별, 체력등급, 카테고리(준비/본/마무리), 난이도, 운동명

## 실행 방법

```bash
# 가상환경(선택 사항) 생성 및 활성화
python -m venv venv
venv\Scripts\activate

# 라이브러리 설치
pip install flask requests

# 서버 실행
python app.py
