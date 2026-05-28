# NaYoo Real Estate Backend

FastAPI + Supabase + SQLite ระบบคำนวณค่าใช้จ่ายโอน/ขายฝาก

## 🏗️ Architecture

- **Supabase** (free 500MB) → user data (agents, listings, calculations), master location, tax config
- **SQLite** (read-only ~200MB) → appraisal data (4 tables: land_deed, land_unit, condo, building_type)
  - Download จาก Github Release ตอน build phase
- **Tax Engine** (Python) → WF1 + WF2 calculations พร้อม MAX rule

## 🚀 Deploy ไป Render

### 1. Upload `appraisal.db` ไป Github Release

ก่อน deploy ต้อง upload `appraisal.db` (~200MB) ไป Github Release ก่อน:

```bash
# 1. สร้าง repo nayoo-backend บน Github (private ก็ได้)
# 2. Push code นี้ขึ้นไป
git init
git add .
git commit -m "Initial backend"
git remote add origin https://github.com/YOUR_USERNAME/nayoo-backend.git
git push -u origin main

# 3. สร้าง release + attach appraisal.db
#    ไปที่ Github repo → Releases → Draft a new release
#    - Tag: v1.0
#    - Title: "Appraisal Data v1 - ขอนแก่น"
#    - Attach file: appraisal.db
#    - Publish release

# 4. Copy URL ของ asset
#    Format: https://github.com/USERNAME/nayoo-backend/releases/download/v1.0/appraisal.db
```

### 2. สร้าง Render Web Service

1. ไป https://dashboard.render.com
2. **New +** → **Web Service** → connect Github repo
3. ตั้งค่า:
   - **Name:** `nayoo-backend`
   - **Region:** Singapore
   - **Plan:** Free
   - **Build Command:** (ใช้ตามใน render.yaml)
   - **Start Command:** (ใช้ตามใน render.yaml)

### 3. Environment Variables

ใน Render Dashboard → Environment → Add:

```
ENV                   = production
SUPABASE_URL          = https://jguvwkelowlsfkxzmspx.supabase.co
SUPABASE_ANON_KEY     = (จาก Supabase Settings → API)
SUPABASE_SERVICE_KEY  = (จาก Supabase Settings → API - service_role)
SUPABASE_JWT_SECRET   = (จาก Supabase Settings → API → JWT Secret)
APPRAISAL_DB_URL      = https://github.com/USER/nayoo-backend/releases/download/v1.0/appraisal.db
APPRAISAL_DB_PATH     = ./data/appraisal.db
CORS_ORIGINS          = https://your-app.vercel.app,http://localhost:5173
```

### 4. Deploy → รอ ~5-10 นาที

Render จะ:
1. apt-get install WeasyPrint dependencies
2. pip install requirements
3. **Download appraisal.db จาก Github Release** (~30 วินาที สำหรับ 200MB)
4. Start gunicorn

### 5. ตั้ง UptimeRobot ป้องกัน sleep

- URL: `https://nayoo-backend.onrender.com/health`
- Interval: 5 นาที

## 📋 API Endpoints

### Public
- `GET /health` — UptimeRobot ping
- `GET /api/locations/{provinces|districts|sub_districts}` — Supabase
- `GET /api/appraisal/land_deed?province_id&district_id&deed_no` — SQLite
- `GET /api/appraisal/land_unit/provinces` — distinct provinces (dropdown)
- `GET /api/appraisal/land_unit/districts?province=X` — distinct districts
- `GET /api/appraisal/land_unit/branches?province=X` — distinct สำนักงานสาขา
- `GET /api/appraisal/land_unit/search?province&district&q` — search
- `GET /api/appraisal/condo/search?province_id&q` — search condos
- `GET /api/appraisal/condo/floors?province_id&building_name` — ดูชั้น
- `GET /api/appraisal/building_types?province_id` — 69 ประเภท
- `POST /api/calculations/transfer` — WF1
- `POST /api/calculations/leaseback` — WF2

### Authenticated (Bearer token)
- `POST /api/listings` — สร้าง
- `GET /api/listings` — รายการของตัวเอง
- `GET /api/listings/{id}` — รายละเอียด + calc
- `POST /api/listings/{id}/calculations` — บันทึก calc
- `GET /api/pdf/{id}/generate` — Download PDF

Swagger UI: `https://nayoo-backend.onrender.com/docs`

## 🧪 Test Locally

```bash
# 1. Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Copy appraisal.db จากที่ build แล้ว
cp /path/to/appraisal.db data/

# 3. .env
cp .env.example .env
# edit .env เติม credentials + APPRAISAL_DB_PATH=./data/appraisal.db

# 4. Run
uvicorn app.main:app --reload --port 8000

# 5. Test
open http://localhost:8000/docs
```
