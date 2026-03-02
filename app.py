from dataclasses import asdict

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from planner_service import RidePlanner
from resorts_service import BCResortAggregator

app = Flask(__name__)
CORS(app)
aggregator = BCResortAggregator()
planner = RidePlanner()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/resorts")
@app.route("/resorts")
def get_resorts_data():
    refresh = request.args.get("refresh", "0") == "1"
    resorts = aggregator.collect(refresh=refresh)
    return jsonify([asdict(r) for r in resorts])


@app.route("/api/resorts/<resort_id>")
def get_resort_by_id(resort_id):
    refresh = request.args.get("refresh", "0") == "1"
    resort = aggregator.get_by_id(resort_id=resort_id, refresh=refresh)
    if resort is None:
        return jsonify({"error": "Resort not found"}), 404
    return jsonify(asdict(resort))


@app.route("/api/planner/recommend", methods=["POST"])
def planner_recommend():
    payload = request.get_json(silent=True) or {}
    refresh = bool(payload.get("refresh_resorts"))
    resorts = [asdict(r) for r in aggregator.collect(refresh=refresh)]
    result = planner.recommend(resorts=resorts, preferences=payload)
    return jsonify(result)


@app.route("/api/planner/profiles", methods=["GET", "POST"])
def planner_profiles():
    if request.method == "GET":
        return jsonify(planner.list_profiles())
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    preferences = payload.get("preferences") or {}
    if not name:
        return jsonify({"error": "Profile name is required"}), 400
    saved = planner.save_profile(name=name, preferences=preferences)
    return jsonify(saved)


@app.route("/api/planner/favorites", methods=["GET", "POST"])
def planner_favorites():
    if request.method == "GET":
        return jsonify(planner.list_favorites())
    payload = request.get_json(silent=True) or {}
    resort_id = (payload.get("resort_id") or "").strip()
    note = (payload.get("note") or "").strip()
    if not resort_id:
        return jsonify({"error": "resort_id is required"}), 400
    saved = planner.save_favorite(resort_id=resort_id, note=note)
    return jsonify(saved)


if __name__ == "__main__":
    app.run(debug=True)
