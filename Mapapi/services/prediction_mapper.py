"""Map a model-deploy JSON response onto a Prediction instance."""
from Mapapi.models import PredictionStatus


def fill_prediction_from_model_response(prediction, data):
    """Populate ``prediction`` with the structured response from the model service.

    ``data`` is the JSON payload returned by ``POST /api1/analyze/``.
    The prediction is saved at the end. The caller is responsible for any
    surrounding transaction logic.
    """
    data = data or {}
    ai_analysis = data.get("ai_analysis") or {}
    topography = data.get("topography") or {}
    satellite = data.get("satellite") or {}
    social_data = data.get("social_data") or {}
    human_impact = data.get("human_impact") or {}
    geocoding = data.get("geocoding") or {}

    prediction.macro_category = ai_analysis.get("macro_category", "") or ""
    prediction.sub_category = ai_analysis.get("sub_category", "") or ""
    prediction.description = ai_analysis.get("description", "") or ""
    prediction.source_size_meters = ai_analysis.get("source_size_meters")
    prediction.spread_vectors = ai_analysis.get("spread_vectors") or []

    prediction.impact_radius_meters = data.get("impact_radius_meters")
    prediction.radius_explanation = data.get("radius_explanation", "") or ""
    prediction.global_impact_score = data.get("global_impact_score")
    prediction.base_severity = data.get("base_severity")
    prediction.impact_tags = data.get("impact_tags") or []
    prediction.recommendation = data.get("recommendation", "") or ""

    prediction.latitude = data.get("latitude")
    prediction.longitude = data.get("longitude")

    prediction.city = geocoding.get("city", "") or ""
    prediction.region = geocoding.get("region", "") or ""
    prediction.country = geocoding.get("country", "") or ""
    prediction.display_name = geocoding.get("display_name", "") or ""

    prediction.social_vulnerability_score = data.get("social_vulnerability_score")
    prediction.is_social_probabilistic = bool(data.get("is_social_probabilistic", False))

    prediction.total_population_exposed = human_impact.get("total_population_exposed") or 0
    prediction.adult_men_exposed = human_impact.get("adult_men_exposed") or 0
    prediction.adult_women_exposed = human_impact.get("adult_women_exposed") or 0
    prediction.children_exposed = human_impact.get("children_exposed") or 0
    prediction.maternities_count = human_impact.get("maternities_count") or 0
    prediction.nurseries_count = human_impact.get("nurseries_count") or 0

    prediction.health_centers = social_data.get("health_centers") or 0
    prediction.maternities = social_data.get("maternities") or 0
    prediction.schools = social_data.get("schools") or 0
    prediction.nurseries = social_data.get("nurseries") or 0
    prediction.markets = social_data.get("markets") or 0
    prediction.water_points = social_data.get("water_points") or 0
    prediction.main_roads_bridges = social_data.get("main_roads_bridges") or 0
    prediction.residential_buildings = social_data.get("residential_buildings") or 0

    prediction.ai_analysis = ai_analysis
    prediction.topography = topography
    prediction.satellite = satellite
    prediction.social_data = social_data
    prediction.human_impact = human_impact
    prediction.geocoding = geocoding
    prediction.potential_risk = data.get("potential_risk")
    prediction.full_response = data

    # Legacy mirror fields for backward-compat with the old Prediction shape.
    if not prediction.incident_type:
        prediction.incident_type = prediction.macro_category or ""
    if not prediction.piste_solution:
        prediction.piste_solution = prediction.recommendation or ""
    if not prediction.analysis:
        prediction.analysis = prediction.description or ""

    if (
        prediction.macro_category == "Autre"
        and prediction.sub_category == "Incident non répertorié"
    ):
        prediction.status = PredictionStatus.COMPLETED_WITH_WARNING
    else:
        prediction.status = PredictionStatus.COMPLETED

    prediction.error_message = ""

    prediction.save()
    return prediction
