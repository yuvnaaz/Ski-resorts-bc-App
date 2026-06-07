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


@app.route("/api/planner/profiles/<name>", methods=["DELETE"])
def delete_planner_profile(name):
    deleted = planner.delete_profile(name)
    if not deleted:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify({"status": "success", "message": f"Profile '{name}' deleted"})


@app.route("/api/planner/favorites", methods=["GET", "POST"])
def planner_favorites():
    if request.method == "GET":
        favs = planner.list_favorites()
        resorts = aggregator.collect(refresh=False)
        resorts_dict = {r.id: asdict(r) for r in resorts}
        populated = []
        for f in favs:
            resort_id = f.get("resort_id")
            populated.append({
                "resort_id": resort_id,
                "note": f.get("note", ""),
                "updated_at": f.get("updated_at", ""),
                "resort": resorts_dict.get(resort_id)
            })
        return jsonify(populated)
    payload = request.get_json(silent=True) or {}
    resort_id = (payload.get("resort_id") or "").strip()
    note = (payload.get("note") or "").strip()
    if not resort_id:
        return jsonify({"error": "resort_id is required"}), 400
    saved = planner.save_favorite(resort_id=resort_id, note=note)
    return jsonify(saved)


@app.route("/api/planner/favorites/<resort_id>", methods=["DELETE"])
def delete_planner_favorite(resort_id):
    deleted = planner.delete_favorite(resort_id)
    if not deleted:
        return jsonify({"error": "Favorite not found"}), 404
    return jsonify({"status": "success", "message": f"Favorite '{resort_id}' deleted"})


if __name__ == "__main__":
    app.run(debug=True)
