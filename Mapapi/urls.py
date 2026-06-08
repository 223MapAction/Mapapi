from django.urls import path, include
from .views import *
from .views.task import (
    IncidentTaskListCreateView, IncidentTaskDetailView,
    IncidentTaskCompleteView, IncidentTaskFailView, IncidentTaskConfirmView,
)
from .views.partner_suggestion import (
    PartnerSuggestionListCreateView, PartnerSuggestionDetailView,
    PartnerSuggestionAcceptView, PartnerSuggestionRejectView,
    MyReceivedSuggestionsView, MySentSuggestionsView,
)
from .views.incident import (
    TakeInChargeView, CloseIncidentView, MyIncidentsView,
    OrgIncidentsView, AgentCodeLoginView, ToggleIncidentPublicView,
    TrashIncidentsView, RestoreIncidentView,
    IncidentAssignmentListCreateView, IncidentAssignmentDetailView,
    AgentAssignedIncidentsView, FieldReportListCreateView,
    BulkDeleteIncidentsView, BulkRestoreIncidentsView,
    BulkForceDeleteIncidentsView,
    IncidentPredictionView, RetryIncidentPredictionView,
    IncidentChatView, AgentPinLoginView, AgentChangePinView,
)
from .views.collaboration import (
    BulkCollaborationRequestView,
    CollaborationDetailView
)
from .views.organisation import (
    OrganisationMemberListView, OrganisationMemberCreateView,
    OrganisationMemberDetailView, OrganisationDetailView,
    FieldAgentCreateView, StaffAccountCreateView,
)
from .ivr_views import (
    TwilioIVRWebhook, SelectZoneView, SelectCategoryView,
    RecordDescriptionView, ProcessRecordingView, RecordingStatusView,
    IVRCallListView, IVRCallDetailView
)
from django.contrib.auth.views import (
    LoginView, LogoutView,
    PasswordChangeView, PasswordChangeDoneView,
    PasswordResetView as DjangoPasswordResetView,PasswordResetDoneView, PasswordResetConfirmView,PasswordResetCompleteView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from .views import PasswordResetView

urlpatterns = [
    path('tenant-config/', TenantConfigView.as_view(), name='tenant_config'),
    path('organisations/', OrganisationViewSet.as_view(), name='organisation-list-create'),
    path('organisations/<int:pk>/', OrganisationViewSet.as_view(), name='organisation-detail'),
    path('organisations/<int:pk>/detail/', OrganisationDetailView.as_view(), name='organisation-detail-enriched'),
    # --- Gestion des membres d'une organisation ---
    path('organisations/<int:pk>/members/', OrganisationMemberListView.as_view(), name='organisation-members-list'),
    path('organisations/<int:pk>/members/add/', OrganisationMemberCreateView.as_view(), name='organisation-members-add'),
    path('organisations/<int:pk>/members/<int:user_id>/', OrganisationMemberDetailView.as_view(), name='organisation-members-detail'),
    path('organisations/<int:pk>/agents/create/', FieldAgentCreateView.as_view(), name='organisation-field-agent-create'),
    path('organisations/<int:pk>/staff/create/', StaffAccountCreateView.as_view(), name='organisation-staff-create'),
    # URL PATTERNS for the documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('accounts/', include('allauth.urls')),
    # for token
    path('login/', TokenObtainPairView.as_view(), name='login'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('verify-token/', TokenVerifyView.as_view(), name='token_verify'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('get_csrf_token/', get_csrf_token, name="get_csrf_token"),
    path("gettoken_bymail/", GetTokenByMailView.as_view(), name="get_token_by_mail"),
    # path('login/', login),
    path('register/', UserRegisterView, name='register'),
    path('user/<int:id>/', user_api_view, name='user'),
    path('user/', UserAPIListView.as_view(), name='user_list'),
    path('user_retrieve/', UserRetrieveView.as_view(), name='user_retrieve'),
    # URL for views incidents
    path('incidentByZone/<int:zone>/', IncidentByZoneAPIView.as_view(), name='incidentZone'),
    path('incident/<int:id>', IncidentAPIView.as_view(), name='incident_rud'),
    path('incident/', IncidentAPIListView.as_view(), name='incident'),
    path('incidentResolved/', IncidentResolvedAPIListView.as_view(), name='incidentResolved'),
    path('incidentNotResolved/', IncidentNotResolvedAPIListView.as_view(), name='incidentNotResolved'),
    path('incidentByMonth/', IncidentByMonthAPIListView.as_view(), name='incidentByMonth'),
    path('incidentByMonth_zone/<zone>', IncidentByMonthByZoneAPIView.as_view(), name='incidentByMonth_zone'),
    path('IncidentOnWeek/', IncidentOnWeekAPIListView.as_view(), name='IncidentOnWeek'),
    path('IncidentOnWeek_zone/<zone>', IncidentByWeekByZoneAPIView.as_view(), name='IncidentOnWeek_zone'),
    path('incident-filter/', IncidentFilterView.as_view(), name='incident_filter'),
    path('my-incidents/', MyIncidentsView.as_view(), name='my-incidents'),
    path('org-incidents/', OrgIncidentsView.as_view(), name='org-incidents'),
    path('incidents/<int:incident_id>/prediction/', IncidentPredictionView.as_view(), name='incident-prediction'),
    path('incidents/<int:incident_id>/prediction/retry/', RetryIncidentPredictionView.as_view(), name='incident-prediction-retry'),
    path('incidents/<int:incident_id>/chat/', IncidentChatView.as_view(), name='incident-chat'),
    path('agent/assigned-incidents/', AgentAssignedIncidentsView.as_view(), name='agent-assigned-incidents'),
    path('field-reports/', FieldReportListCreateView.as_view(), name='field-reports'),
    path('agent-login/', AgentCodeLoginView.as_view(), name='agent-login'),
    path('agent-pin-login/', AgentPinLoginView.as_view(), name='agent-pin-login'),
    path('agent/change-pin/', AgentChangePinView.as_view(), name='agent-change-pin'),
    # URL for views Events
    path('Event/<int:id>', EvenementAPIView.as_view(), name='event'),
    path('Event/', EvenementAPIListView.as_view(), name='event'),
    # URL for views contact
    path('contact/<int:id>', ContactAPIView.as_view(), name='contact'),
    path('contact/', ContactAPIListView.as_view(), name='contact'),
    # URL for views community
    path('community/<int:id>', CommunauteAPIView.as_view(), name='community'),
    path('community/', CommunauteAPIListView.as_view(), name='community'),
    # URL for views rapport
    path('rapport/<int:id>', RapportAPIView.as_view(), name='rapport'),
    path('rapport/', RapportAPIListView.as_view(), name='rapport_list'),
    path('rapport_user/<int:id>', RapportByUserAPIView.as_view(), name='rapport_user'),
    path('rapport_zone/', RapportOnZoneAPIView.as_view(), name='rapport_zone'),
    # URL for views participate
    path('participate/<int:id>', ParticipateAPIView.as_view(), name='participate_rud'),
    path('participate/', ParticipateAPIListView.as_view(), name='participate'),
    # URL for views Elu
    path('elu/<int:id>', EluAPIListView.as_view(), name='elu_rud'),
    path('elu/', EluToZoneAPIListView.as_view(), name='elu_zone'),
    # URL for views citizen
    path('citizen/', CitizenAPIListView.as_view(), name='citizen'),
    # URL for views zone
    path('zone/<int:id>', ZoneAPIView.as_view(), name='zone'),
    path('zone/', ZoneAPIListView.as_view(), name='zone_list'),
    # URL for views message
    path('message/<int:id>', MessageAPIView.as_view(), name='message'),
    path('message/', MessageAPIListView.as_view(), name='message_list'),
    path('message/', MessageByComAPIView.as_view(), name='message_com'),
    path('message_user/<int:id>/', MessageByUserAPIView.as_view(), name='message_user'),
    path('message/<zone>', MessageByZoneAPIView.as_view(), name='message_zone'),
    path('response_msg/', ResponseMessageAPIListView.as_view(), name='response_msg'),
    path('response_msg/<int:id>', ResponseMessageAPIView.as_view(), name='response_msg'),
    # URL for views category
    path('category/<int:id>', CategoryAPIView.as_view(), name='category-detail'),
    path('category/', CategoryAPIListView.as_view(), name='category-list'),
    # URL for views indicator
    path('indicator/', IndicateurAPIListView.as_view(), name='indicator'),
    path('indicator/<int:id>', IndicateurAPIView.as_view(), name='indicator'),
    path('indicator_incident/', IndicateurOnIncidentAPIListView.as_view(), name='indicator_incident'),
    path('indicator_incident_zone/<zone>', IndicateurOnIncidentByZoneAPIView.as_view(), name='indicator_incident_zone'),
    path('indicator_incident_elu/<int:id>', IndicateurOnIncidentByEluAPIView.as_view(), name='indicator_incident_elu'),
    # URL for views imageBackground
    path('image/', ImageBackgroundAPIListView.as_view(), name='image'),
    path('image/<int:id>', ImageBackgroundAPIView.as_view(), name='image'),
    # URL for views password
    path('password/', PasswordResetRequestView.as_view(), name='passwordRequest'),
    path('password_reset/', PasswordResetView.as_view(), name='passwordReset'),
    path('change_password/', ChangePasswordView.as_view(), name='change_password'),
    path('updatePoint/', UpdatePointAPIListView.as_view(), name='updatePoint'),
    # Overpass URL
    path('overpass/', OverpassApiIntegration.as_view(), name="overpassapi"),
    # OTP URL
    path('verify_otp/', PhoneOTPView.as_view(), name="verify_otp"),
    # Collaboration URL
    path('collaboration/', CollaborationView.as_view(), name='collaboration'),
    path('collaboration/<int:pk>/', CollaborationDetailView.as_view(), name='collaboration-detail'),
    path('collaborations/bulk-request/', BulkCollaborationRequestView.as_view(), name='bulk-collaboration-request'),
    path('collaborations/dashboard/', CollaborationDashboardView.as_view(), name='collaboration-dashboard'),
    path('accept-collaboration/', AcceptCollaborationView.as_view(), name='accept-collaboration'),
    path('decline/', DeclineCollaborationView.as_view(), name='decline-collaboration'),
    path('collaborations/accept/', AcceptCollaborationView.as_view(), name='accept-collaboration'),
    path('collaboration/<int:collaboration_id>/<str:action>/', HandleCollaborationRequestView.as_view(), name="handle_collaboration_request"),
    path('discussion/<int:incident_id>/', DiscussionMessageView.as_view(), name='discussion'),

    # Search Incident
    path('Search/', IncidentSearchView.as_view(), name="search"),
    path('prediction/', PredictionView.as_view(), name="predicton"),
    path('histories/', history_list, name='history_list'),
    path('history/<int:id>', ChatHistoryViewByIncident.as_view(), name='history_by_id'),
    path('histories/add/', add_history, name='add_history'),
    # Prediction
    path('prediction/<int:id>/', PredictionViewByID.as_view(), name="predicton"),
    path('Incidentprediction/<int:id>/', PredictionViewByIncidentID.as_view(), name="prediction"),
    # Notification
    path('notifications/', NotificationViewSet.as_view({'get': 'list'}), name="notification"),
    path('hadleIncident/<int:incident_id>', HandleIncidentView.as_view(), name="handle"),
    path('user_action/', UserActionView.as_view({'get': 'list'}), name="user_action"),
    path('incidentDetail/<int:incident_id>', IncidentUserView.as_view(), name="incident_detail"),
    path('registerCitizen/', RegisterView.as_view(), name='registerCitizen'),
    path('verify-email/<uuid:token>/', VerifyEmailView.as_view(), name='verify-email'),
    path('set-password/', SetPasswordView.as_view(), name='set-password'),
    path('otpRequest/', RequestOTPView.as_view(), name='otp-request'),
    path('verifyOtp/', VerifyOTPView.as_view(), name='verify-otp'),
    
    path('ivr/webhook/', TwilioIVRWebhook.as_view(), name='ivr-webhook'),
    path('ivr/select-zone/', SelectZoneView.as_view(), name='ivr-select-zone'),
    path('ivr/select-category/', SelectCategoryView.as_view(), name='ivr-select-category'),
    path('ivr/record-description/', RecordDescriptionView.as_view(), name='ivr-record-description'),
    path('ivr/process-recording/', ProcessRecordingView.as_view(), name='ivr-process-recording'),
    path('ivr/recording-status/', RecordingStatusView.as_view(), name='ivr-recording-status'),
    path('ivr/calls/', IVRCallListView.as_view(), name='ivr-calls-list'),
    path('ivr/calls/<int:call_id>/', IVRCallDetailView.as_view(), name='ivr-call-detail'),

    # --- Tâches d'incident (CRUD + complete/fail) ---
    path('incidents/<int:incident_id>/tasks/', IncidentTaskListCreateView.as_view(), name='incident-task-list'),
    path('incidents/<int:incident_id>/tasks/<int:pk>/', IncidentTaskDetailView.as_view(), name='incident-task-detail'),
    path('incidents/<int:incident_id>/tasks/<int:pk>/complete/', IncidentTaskCompleteView.as_view(), name='incident-task-complete'),
    path('incidents/<int:incident_id>/tasks/<int:pk>/fail/', IncidentTaskFailView.as_view(), name='incident-task-fail'),
    path('incidents/<int:incident_id>/tasks/<int:pk>/confirm/', IncidentTaskConfirmView.as_view(), name='incident-task-confirm'),

    # --- Suggestions de partenaires (CRUD + accept/reject) ---
    path('incidents/<int:incident_id>/suggestions/', PartnerSuggestionListCreateView.as_view(), name='partner-suggestion-list'),
    path('incidents/<int:incident_id>/suggestions/<int:pk>/', PartnerSuggestionDetailView.as_view(), name='partner-suggestion-detail'),
    path('incidents/<int:incident_id>/suggestions/<int:pk>/accept/', PartnerSuggestionAcceptView.as_view(), name='partner-suggestion-accept'),
    path('incidents/<int:incident_id>/suggestions/<int:pk>/reject/', PartnerSuggestionRejectView.as_view(), name='partner-suggestion-reject'),
    path('my-suggestions/received/', MyReceivedSuggestionsView.as_view(), name='my-suggestions-received'),
    path('my-suggestions/sent/', MySentSuggestionsView.as_view(), name='my-suggestions-sent'),

    # --- Prise en charge et clôture d'incident ---
    path('incidents/<int:incident_id>/take_in_charge/', TakeInChargeView.as_view(), name='incident-take-in-charge'),
    path('incidents/<int:incident_id>/close/', CloseIncidentView.as_view(), name='incident-close'),
    path('incidents/<int:incident_id>/toggle-public/', ToggleIncidentPublicView.as_view(), name='incident-toggle-public'),
    path('incidents/<int:incident_id>/assignments/', IncidentAssignmentListCreateView.as_view(), name='incident-assignment-list'),
    path('incidents/<int:incident_id>/assignments/<int:pk>/', IncidentAssignmentDetailView.as_view(), name='incident-assignment-detail'),
    path('incidents/bulk-delete/', BulkDeleteIncidentsView.as_view(), name='incident-bulk-delete'),
    path('incidents/bulk-restore/', BulkRestoreIncidentsView.as_view(), name='incident-bulk-restore'),
    path('incidents/bulk-force-delete/', BulkForceDeleteIncidentsView.as_view(), name='incident-bulk-force-delete'),

    # --- Corbeille (Super Admin uniquement) ---
    path('incidents/trash/', TrashIncidentsView.as_view(), name='incident-trash'),
    path('incidents/<int:incident_id>/restore/', RestoreIncidentView.as_view(), name='incident-restore'),

]

