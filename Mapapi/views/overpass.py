"""Overpass API integration (amenities lookup)."""
import os
import json

import httpx
import overpy

from django.core.cache import cache
from django.http import JsonResponse

from rest_framework import status, generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, inline_serializer
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


class OverpassApiIntegration(generics.CreateAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer
    @extend_schema(
        tags=['Référentiel & Statistiques'],
        operation_id='overpass_amenities_nearby',
        summary="Lister les commodités proches (Overpass/OSM)",
        description="Interroge l'API Overpass (OpenStreetMap) pour les commodités (pharmacie, mosquée, école, "
        "restaurant, bar, prison, rivière, marigot, clinique) dans un rayon de 500 m autour des coordonnées "
        "fournies, puis renvoie une liste d'objets `{amenity, name}`. Les résultats sont mis en cache. Endpoint public.",
        request=None,
        parameters=[
            OpenApiParameter('latitude', OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True, description="Latitude du point de recherche."),
            OpenApiParameter('longitude', OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True, description="Longitude du point de recherche."),
        ],
        responses={
            200: inline_serializer(
                name='OverpassAmenity',
                fields={'amenity': serializers.CharField(), 'name': serializers.CharField()},
                many=True,
            ),
            400: OpenApiResponse(description="Paramètres latitude/longitude manquants ou non numériques."),
            503: OpenApiResponse(description="Service Overpass indisponible : {\"detail\": \"...\", \"error\": \"...\"}."),
        },
    )
    def get(self, request, *args, **kwargs):
        lat = request.GET.get("latitude")
        lon = request.GET.get("longitude")

        if lat is None or lon is None:
            raise ValidationError("Les paramètres latitude et longitude sont requis.")

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            raise ValidationError("Les paramètres latitude et longitude doivent être des nombres.")

        cache_key = f"overpass:amenities:v1:{lat_f:.5f}:{lon_f:.5f}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached, safe=False)

        query = f"""
        [out:json];
        (
            node["amenity"="pharmacy"](around:500, {lat_f}, {lon_f});
            node["amenity"="mosque"](around:500, {lat_f}, {lon_f});
            node["amenity"="school"](around:500, {lat_f}, {lon_f});
            node["amenity"="restaurant"](around:500, {lat_f}, {lon_f});
            node["amenity"="bar"](around:500, {lat_f}, {lon_f});
            node["amenity"="prison"](around:500, {lat_f}, {lon_f});
            node["amenity"="river"](around:500, {lat_f}, {lon_f});
            node["amenity"="marigot"](around:500, {lat_f}, {lon_f});
            node["amenity"="clinic"](around:500, {lat_f}, {lon_f});
        );
        out body;
        >;
        out skel qt;
        """

        try:
            r = httpx.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            r.raise_for_status()
            payload = r.json()
        except httpx.HTTPError as e:
            logger.exception("Overpass request failed")
            return Response({"detail": "Overpass unavailable", "error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        elements = payload.get("elements", []) if isinstance(payload, dict) else []
        results_list = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            tags = el.get("tags") or {}
            if not isinstance(tags, dict):
                tags = {}
            results_list.append(
                {
                    "amenity": tags.get("amenity", ""),
                    "name": tags.get("name", ""),
                }
            )

        cache.set(cache_key, results_list, timeout=int(os.environ.get("OVERPASS_CACHE_TTL_SECONDS", "3600")))
        return JsonResponse(results_list, safe=False)
