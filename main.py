import os
from flask import Flask, request, jsonify
from hyundai_kia_connect_api import VehicleManager, ClimateRequestOptions
from hyundai_kia_connect_api.exceptions import AuthenticationError

app = Flask(__name__)

# =========================
# Environment Variables
# =========================
USERNAME = os.environ.get("KIA_USERNAME")
PASSWORD = os.environ.get("KIA_PASSWORD")
PIN = os.environ.get("KIA_PIN")
SECRET_KEY = os.environ.get("SECRET_KEY")
VEHICLE_ID = os.environ.get("VEHICLE_ID")  # Số VIN 17 ký tự (Nếu có)

missing = []
if not USERNAME: missing.append("KIA_USERNAME")
if not PASSWORD: missing.append("KIA_PASSWORD")
if not PIN: missing.append("KIA_PIN")
if not SECRET_KEY: missing.append("SECRET_KEY")

if missing:
    raise ValueError(f"Missing environment variables: {', '.join(missing)}")

# =========================
# Vehicle Manager
# =========================
vehicle_manager = VehicleManager(
    region=3,       # North America (Mặc định cho Sportage 2026 X-Pro Prestige)
    brand=1,        # KIA
    username=USERNAME,
    password=PASSWORD,
    pin=str(PIN)
)

# =========================
# Helper Functions
# =========================
def authorize_request():
    # Chấp nhận cả việc gửi mã khóa qua Headers (Authorization) hoặc qua Body (JSON)
    auth_header = request.headers.get("Authorization")
    if auth_header == SECRET_KEY:
        return True
        
    if request.is_json:
        body_secret = request.json.get("secret_key") or request.json.get("SECRET_KEY")
        if body_secret == SECRET_KEY:
            return True
            
    return False

def ensure_authenticated():
    """ Attempt to refresh Kia token. """
    try:
        vehicle_manager.check_and_refresh_token()
    except AuthenticationError as e:
        raise AuthenticationError(
            "Kia authentication failed. Open the Kia app and complete 2FA, then retry."
        ) from e

def refresh_and_sync():
    """ Refresh token and sync vehicle state """
    ensure_authenticated()
    # Đồng bộ hóa dữ liệu xe từ máy chủ Kia
    vehicle_manager.update_all_vehicles_with_cached_state()

def get_vehicle_id():
    """ Trích xuất số VIN/ID xe chính xác cho các dòng xe đời mới 2026 """
    if VEHICLE_ID:
        return VEHICLE_ID
        
    vehicles = vehicle_manager.vehicles
    if not vehicles:
        raise ValueError("No vehicles found on the Kia account.")
        
    # Thư viện đời mới dùng chính số VIN làm Khóa (Key) của danh mục xe
    first_vehicle_vin = next(iter(vehicles.keys()))
    return first_vehicle_vin

# =========================
# Logging
# =========================
@app.before_request
def log_request_info():
    print(f"Incoming request: {request.method} {request.path}")

# =========================
# Routes
# =========================
@app.route("/", methods=["GET", "POST"])
def root():
    return jsonify({
        "status": "OK",
        "service": "Kia Vehicle Control API"
    }), 200

@app.route("/auth_status", methods=["GET", "POST"])
def auth_status():
    if not authorize_request():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        ensure_authenticated()
        return jsonify({"status": "authenticated"}), 200
    except AuthenticationError as e:
        return jsonify({
            "status": "authentication_failed",
            "message": str(e)
        }), 401

@app.route("/list_vehicles", methods=["GET", "POST"])
def list_vehicles():
    if not authorize_request():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        refresh_and_sync()
        vehicles = vehicle_manager.vehicles
        if not vehicles:
            return jsonify({"error": "No vehicles found"}), 404
            
        # Sửa lỗi bóc tách thuộc tính an toàn bằng hàm getattr để tránh lỗi sập 500
        vehicle_list = []
        for vin, v in vehicles.items():
            vehicle_list.append({
                "name": getattr(v, 'name', 'Kia Sportage'),
                "id": vin,  # Sử dụng luôn số VIN định danh làm ID
                "model": getattr(v, 'model', 'Sportage'),
                "year": getattr(v, 'year', 2026)
            })
            
        return jsonify({
            "status": "success",
            "vehicles": vehicle_list
        }), 200
    except AuthenticationError as e:
        return jsonify({
            "error": "Authentication failed",
            "details": str(e),
            "action": "Open Kia app and complete 2FA"
        }), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/start_climate", methods=["POST"])
def start_climate():
    if not authorize_request():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        refresh_and_sync()
        vehicle_id = get_vehicle_id()
        
        # Cấu hình nổ máy kèm bật điều hòa (72 độ F tương đương khoảng 22 độ C)
        climate_options = ClimateRequestOptions(
            set_temp=72,
            duration=10
        )
        # Thực thi lệnh từ thư viện gốc Kia Connect
        vehicle_manager.start_climate(vehicle_id, climate_options)
        return jsonify({
            "status": "climate_started",
            "vehicle_id": vehicle_id
        }), 200
    except AuthenticationError as e:
        return jsonify({
            "error": "Authentication failed",
            "details": str(e)
        }), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stop_climate", methods=["POST"])
def stop_climate():
    if not authorize_request():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        refresh_and_sync()
        vehicle_id = get_vehicle_id()
        vehicle_manager.stop_climate(vehicle_id)
        return jsonify({
            "status": "climate_stopped",
            "vehicle_id": vehicle_id
        }), 200
    except AuthenticationError as e:
        return jsonify({"error": "Authentication failed", "details": str(e)}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/unlock_car", methods=["POST"])
def unlock_car():
    if not authorize_request():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        refresh_and_sync()
        vehicle_id = get_vehicle_id()
        vehicle_manager.unlock(vehicle_id)
        return jsonify({
            "status": "car_unlocked",
            "vehicle_id": vehicle_id
        }), 200
    except AuthenticationError as e:
        return jsonify({"error": "Authentication failed", "details": str(e)}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/lock_car", methods=["POST"])
def lock_car():
    if not authorize_request():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        refresh_and_sync()
        vehicle_id = get_vehicle_id()
        vehicle_manager.lock(vehicle_id)
        return jsonify({
            "status": "car_locked",
            "vehicle_id": vehicle_id
        }), 200
    except AuthenticationError as e:
        return jsonify({"error": "Authentication failed", "details": str(e)}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# App Entry
# =========================
if __name__ == "__main__":
    print("Starting Kia Vehicle Control API...")
    app.run(host="0.0.0.0", port=8080)
