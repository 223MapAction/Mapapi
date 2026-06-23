import math
from datetime import timedelta
from django.db.models import Q, Sum, F, Count, Avg, IntegerField
from django.db.models.functions import Cast
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone
from ..models import (
    Incident, Prediction, Collaboration,
    DECLARED, TAKEN, RESOLVED, TASK_DONE
)
from django.contrib.auth import get_user_model
User = get_user_model()

class ImpactCalculatorService:
    def __init__(self, user, query_params):
        self.user = user
        self.query_params = query_params

    def _get_date_filter(self):
        period = self.query_params.get('period')
        if period == '30d':
            return timezone.now() - timedelta(days=30)
        elif period == '90d':
            return timezone.now() - timedelta(days=90)
        elif period == 'year':
            return timezone.now() - timedelta(days=365)
        return None

    def get_base_queryset(self):
        qs = Incident.objects.all()

        # 1. Filtre par rôle (Périmètre)
        if not self.user.is_superuser:
            # Admin organisation / Agent bureau : incidents de son organisation
            if hasattr(self.user, 'organisation_member') and self.user.organisation_member:
                org = self.user.organisation_member
                org_members = org.members.all()
                # Les incidents liés à l'organisation : créés par, pris en charge par, ou collaboration
                qs = qs.filter(
                    Q(user_id__in=org_members) |
                    Q(taken_by__in=org_members) |
                    Q(collaboration__user__in=org_members, collaboration__status='accepted')
                ).distinct()
            else:
                return Incident.objects.none()

        # 2. Filtres par paramètres
        # Périmètre (résolus / en cours)
        scope = self.query_params.get('scope')
        if scope == 'resolved':
            qs = qs.filter(etat=RESOLVED)
        elif scope == 'ongoing':
            qs = qs.filter(etat=TAKEN, tasks__state=TASK_DONE).distinct()
        
        # Période
        date_from = self._get_date_filter()
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        
        # Catégorie
        category = self.query_params.get('category')
        if category:
            qs = qs.filter(Q(category_id__name__icontains=category) | Q(prediction__macro_category__icontains=category))
            
        # Recherche texte
        search = self.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(zone__icontains=search)
            )

        return qs

    def compute(self):
        base_qs = self.get_base_queryset()
        
        if not base_qs.exists():
            return self._empty_result()

        # Séparation des incidents
        # Incidents avec prédiction (analyse exploitable)
        incidents_with_analysis = base_qs.filter(prediction__isnull=False).distinct()
        
        # Le volume total (pour affichage de "n incidents sans analyse exploitable" et taux de résolution)
        total_incidents_count = base_qs.count()
        incidents_without_analysis = total_incidents_count - incidents_with_analysis.count()

        # Filtre selon les règles d'impact: 
        # Inclure : résolus, ou pris en compte avec tâche terminée
        # Exclure : incidents sans action (déclarés, ou pris en compte sans tâche)
        impact_incidents = incidents_with_analysis.filter(
            Q(etat=RESOLVED) |
            Q(etat=TAKEN, tasks__state=TASK_DONE) 
        ).distinct()

        # Obtenir les prédictions correspondantes
        predictions = Prediction.objects.filter(incident__in=impact_incidents)

        # 4.1 Bénéficiaires directs + ventilation hommes / femmes / enfants
        directs_agg = predictions.aggregate(
            total=Sum('total_population_exposed'),
            hommes=Sum('adult_men_exposed'),
            femmes=Sum('adult_women_exposed'),
            enfants=Sum('children_exposed'),
        )
        beneficiaires_directs = {
            "total": directs_agg['total'] or 0,
            "hommes": directs_agg['hommes'] or 0,
            "femmes": directs_agg['femmes'] or 0,
            "enfants": directs_agg['enfants'] or 0,
        }

        # 4.2 Bénéficiaires indirects (via json field potential_risk -> stats -> total_pop)
        # Extraction du champ JSON imbriqué et somme côté SQL.
        indirects_agg = predictions.annotate(
            indirect_pop=Cast(
                KeyTextTransform('total_pop', KeyTextTransform('stats', 'potential_risk')),
                IntegerField(),
            )
        ).aggregate(total=Sum('indirect_pop'))
        beneficiaires_indirects = {
            "total": indirects_agg['total'] or 0,
        }

        # 4.3 Infrastructures : total + détail par type
        infra_fields = ['schools', 'health_centers', 'maternities', 'nurseries', 'markets', 'water_points', 'main_roads_bridges', 'residential_buildings']
        infra_agg = predictions.aggregate(**{f: Sum(f) for f in infra_fields})
        infrastructures_detail = {f: (infra_agg[f] or 0) for f in infra_fields}
        infrastructures_total = sum(infrastructures_detail.values())

        # 4.4 Superficie impact : somme(π·r²) calculée en SQL (somme des r²) puis × π.
        radius_agg = predictions.filter(impact_radius_meters__gt=0).aggregate(
            total_r2=Sum(F('impact_radius_meters') * F('impact_radius_meters'))
        )
        superficie_m2 = math.pi * (radius_agg['total_r2'] or 0)
        superficie_ha = round(superficie_m2 / 10000, 2)

        # 4.5 Temps moyen de résolution & 4.6 Taux de résolution
        resolved_incidents = base_qs.filter(etat=RESOLVED)
        nb_resolus = resolved_incidents.count()
        taux_resolution = round((nb_resolus / total_incidents_count) * 100, 2) if total_incidents_count > 0 else 0

        durations = []
        for inc in resolved_incidents:
            if inc.resolution_end_date and inc.created_at:
                duration = (inc.resolution_end_date - inc.created_at.date()).days
                if duration >= 0:
                    durations.append(duration)
        temps_moyen_resolution = sum(durations) / len(durations) if durations else 0

        # Indicateurs Super Admin
        mobilisation = None
        contribution_citoyenne = None

        if self.user.is_superuser:
            # Optimisation des requêtes
            impact_incidents_opt = impact_incidents.select_related('taken_by__organisation_member', 'user_id').prefetch_related(
                'collaboration_set__user__organisation_member',
                'tasks__assigned_to'
            )

            # 4.7 Mobilisation
            org_names = set()
            field_agents = set()
            
            for inc in impact_incidents_opt:
                if inc.taken_by and getattr(inc.taken_by, 'organisation_member', None):
                    org_names.add(inc.taken_by.organisation_member.name)
                
                collabs = inc.collaboration_set.filter(status='accepted')
                for c in collabs:
                    if getattr(c.user, 'organisation_member', None):
                        org_names.add(c.user.organisation_member.name)
            
                for t in inc.tasks.all():
                    if t.assigned_to and getattr(t.assigned_to, 'org_role', None) == 'field_agent':
                        field_agents.add(t.assigned_to.id)
                
                if inc.user_id and getattr(inc.user_id, 'org_role', None) == 'field_agent':
                    field_agents.add(inc.user_id.id)
                    
            nb_collaborations = Collaboration.objects.filter(incident__in=impact_incidents).count()

            mobilisation = {
                "organisations_distinctes": len(org_names),
                "agents_terrain": len(field_agents),
                "collaborations": nb_collaborations
            }

            # 4.8 Contribution citoyenne
            # Créateur n'est pas un agent (ie. None ou autre rôle, mais dans ce contexte on exclut les field_agents)
            signalements_citoyens = base_qs.exclude(user_id__org_role='field_agent')
            nb_recus = signalements_citoyens.count()
            nb_verifies = signalements_citoyens.filter(prediction__isnull=False).count()
            nb_actions = signalements_citoyens.filter(prediction__isnull=False).exclude(etat=DECLARED).count()

            contribution_citoyenne = {
                "signalements_recus": nb_recus,
                "signalements_verifies": nb_verifies,
                "transformes_actions": nb_actions
            }

        return {
            "beneficiaires_directs": beneficiaires_directs,
            "beneficiaires_indirects": beneficiaires_indirects,
            "infrastructures_total": infrastructures_total,
            "infrastructures_detail": infrastructures_detail,
            "superficie_ha": superficie_ha,
            "temps_moyen_resolution": temps_moyen_resolution,
            "taux_resolution": taux_resolution,
            "incidents_sans_analyse": incidents_without_analysis,
            "mobilisation": mobilisation,
            "contribution_citoyenne": contribution_citoyenne
        }

    def _empty_result(self):
        infra_fields = ['schools', 'health_centers', 'maternities', 'nurseries', 'markets', 'water_points', 'main_roads_bridges', 'residential_buildings']
        return {
            "beneficiaires_directs": {"total": 0, "hommes": 0, "femmes": 0, "enfants": 0},
            "beneficiaires_indirects": {"total": 0},
            "infrastructures_total": 0,
            "infrastructures_detail": {f: 0 for f in infra_fields},
            "superficie_ha": 0,
            "temps_moyen_resolution": 0,
            "taux_resolution": 0,
            "incidents_sans_analyse": 0,
            "mobilisation": {
                "organisations_distinctes": 0,
                "agents_terrain": 0,
                "collaborations": 0
            } if self.user.is_superuser else None,
            "contribution_citoyenne": {
                "signalements_recus": 0,
                "signalements_verifies": 0,
                "transformes_actions": 0
            } if self.user.is_superuser else None
        }
