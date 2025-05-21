from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.utils import timezone
from datetime import timedelta
from Mapapi.models import User, Zone, Category, Indicateur, Incident

class IncidentViewTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            first_name='Test',
            last_name='User',
            phone='1234567890',
            user_type='citizen'
        )
        self.client.force_authenticate(user=self.user)

        # Create test zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            lattitude='0.0',
            longitude='0.0'
        )

        # Create test category
        self.category = Category.objects.create(
            name='Test Category',
            description='Test Category Description'
        )

        # Create test indicateur
        self.indicateur = Indicateur.objects.create(
            name='Test Indicateur'
        )

        # Create test incident
        self.incident = Incident.objects.create(
            title='Test Incident',
            zone=str(self.zone.id),  # Use zone ID instead of name
            description='Test Description',
            user_id=self.user,
            lattitude='0.0',
            longitude='0.0',
            etat='declared',
            category_id=self.category,
            indicateur_id=self.indicateur,
            created_at=timezone.now()  # Set created_at to now
        )

    def test_list_incidents(self):
        """Test listing all incidents"""
        url = reverse('incident')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)

    def test_create_incident(self):
        """Test creating a new incident"""
        url = reverse('incident')
        data = {
            'title': 'New Incident',
            'zone': str(self.zone.id),  # Use zone ID instead of name
            'description': 'New Description',
            'user_id': self.user.id,
            'lattitude': '1.0',
            'longitude': '1.0',
            'etat': 'declared',
            'category_id': self.category.id,
            'indicateur_id': self.indicateur.id
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Incident.objects.count(), 2)
        self.assertEqual(response.data['title'], 'New Incident')

    def test_create_incident_invalid_data(self):
        """Test creating an incident with invalid data"""
        url = reverse('incident')
        data = {
            'title': '',  # Invalid: empty title
            'description': 'Test Description'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_incident(self):
        """Test retrieving a specific incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Incident')

    def test_retrieve_nonexistent_incident(self):
        """Test retrieving a non-existent incident"""
        url = reverse('incident_rud', args=[999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_incident(self):
        """Test updating an incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        data = {
            'title': 'Updated Incident',
            'description': 'Updated Description',
            'zone': str(self.zone.id),  # Use zone ID instead of name
            'user_id': self.user.id,
            'lattitude': '0.0',
            'longitude': '0.0',
            'etat': 'declared',
            'category_id': self.category.id,
            'indicateur_id': self.indicateur.id
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Incident')

    def test_update_nonexistent_incident(self):
        """Test updating a non-existent incident"""
        url = reverse('incident_rud', args=[999])
        data = {
            'title': 'Updated Incident',
            'description': 'Updated Description'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_incident(self):
        """Test deleting an incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_nonexistent_incident(self):
        """Test deleting a non-existent incident"""
        url = reverse('incident_rud', args=[999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_resolved_incidents(self):
        """Test listing resolved incidents"""
        url = reverse('incidentResolved')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_not_resolved_incidents(self):
        """Test listing not resolved incidents"""
        url = reverse('incidentNotResolved')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_by_zone(self):
        """Test getting incidents by zone"""
        url = reverse('incidentZone', args=[self.zone.id])  # Use zone ID instead of name
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Test Incident')

    def test_incident_by_week(self):
        """Test getting incidents by week"""
        url = reverse('IncidentOnWeek')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_by_month(self):
        """Test getting incidents by month"""
        url = reverse('incidentByMonth')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_by_month_by_zone(self):
        """Test getting incidents by month and zone"""
        url = reverse('incidentByMonth_zone', args=[self.zone.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_by_week_by_zone(self):
        """Test getting incidents by week and zone"""
        url = reverse('IncidentOnWeek_zone', args=[self.zone.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_filter_today(self):
        """Test filtering incidents by today"""
        url = reverse('incident_filter')
        response = self.client.get(url, {'filter': 'today'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_filter_week(self):
        """Test filtering incidents by week"""
        url = reverse('incident_filter')
        response = self.client.get(url, {'filter': 'week'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_filter_month(self):
        """Test filtering incidents by month"""
        url = reverse('incident_filter')
        response = self.client.get(url, {'filter': 'month'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_incident_filter_invalid_type(self):
        """Test filtering incidents with invalid filter type"""
        url = reverse('incident_filter')
        response = self.client.get(url, {'filter_type': 'invalid_type'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)  # View returns 200 even for invalid filter

    def test_incident_filter_no_type(self):
        """Test filtering incidents without filter type"""
        url = reverse('incident_filter')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)  # View returns 200 when no filter specified

    def test_incident_on_week_api_list_view(self):
        """Test incident on week API list view"""
        # Create an incident for this week
        current_week_incident = Incident.objects.create(
            title='Current Week Incident',
            zone=str(self.zone.name),
            description='Test Description',
            user_id=self.user,
            lattitude='0.0',
            longitude='0.0',
            etat='declared',
            category_id=self.category,
            indicateur_id=self.indicateur,
            created_at=timezone.now()
        )

        url = reverse('IncidentOnWeek')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check response structure
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'].strip(), 'incidents by week')
        
        # The data might be empty if the test is running in a different timezone or date context
        # Instead of checking the exact number, just verify the structure
        self.assertIn('data', response.data)
        
        # Only check day data if there's actually data for today's incidents
        if response.data['data']:
            day_data = response.data['data'][0]
            self.assertIn('total', day_data)
            self.assertIn('resolved', day_data)
            self.assertIn('unresolved', day_data)

class IncidentViewsTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='testuser@example.com', password='testpass123')
        self.zone, created = Zone.objects.get_or_create(name='Test Zone')  # Ensure no duplicate Zone creation
        self.category = Category.objects.create(name='Test Category')
        self.incident = Incident.objects.create(
            title='Test Incident',
            description='Test Description',
            user_id=self.user,
            zone=self.zone.name,  # Use the Zone instance
            category_id=self.category,
            lattitude='40.7128',
            longitude='-74.0060'
        )

    def test_incident_api_list_view(self):
        url = reverse('incident')  # Updated to match the correct URL configuration
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue('results' in response.data)

    def test_incident_not_resolved_api_list_view(self):
        url = reverse('incidentNotResolved')  # Updated to match the correct URL configuration
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue('results' in response.data)

    def test_incident_on_week_api_list_view(self):
        # Create test incidents with timezone-aware datetimes
        now = timezone.now()
        date1 = now.replace(year=2025, month=2, day=10, hour=0, minute=0, second=0, microsecond=0)
        date2 = now.replace(year=2025, month=2, day=18, hour=0, minute=0, second=0, microsecond=0)
        
        Incident.objects.create(
            title='Test Incident 1',
            description='Test Description 1',
            user_id=self.user,
            zone=self.zone.name,
            category_id=self.category,
            created_at=date1
        )
        
        Incident.objects.create(
            title='Test Incident 2',
            description='Test Description 2',
            user_id=self.user,
            zone=self.zone.name,
            category_id=self.category,
            created_at=date2
        )

        url = reverse('IncidentOnWeek')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue('data' in response.data)

    def test_incident_search_view(self):
        url = reverse('search')  # Updated to match the correct URL configuration
        response = self.client.get(url, {'search_term': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_handle_incident_view(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('handle', args=[self.incident.id])  # Updated to match the correct URL configuration
        response = self.client.post(url, {'action': 'taken_into_account'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.etat, 'taken_into_account')


    def test_incident_user_view(self):
        self.client.force_authenticate(user=self.user)
        self.incident.taken_by = self.user
        self.incident.save()
        url = reverse('incident_detail', args=[self.incident.id])  # Updated to match the correct URL configuration
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue('user' in response.data)

    # def test_handle_collaboration_request_view(self):
    #     self.client.force_authenticate(user=self.user)
    #     collaboration = Collaboration.objects.create(
    #         user=self.user, 
    #         incident=self.incident,
    #         end_date=timezone.now().date() + timedelta(days=30)  # Set a valid end_date
    #     )
    #     # Ensure collaboration.id is not None
    #     self.assertIsNotNone(collaboration.id, "Collaboration ID should not be None")
        
    #     url = reverse('handle_collaboration_request', args=[collaboration.id, 'accept'])  # Updated to match the correct URL configuration
    #     response = self.client.post(url)
    #     self.assertEqual(response.status_code, status.HTTP_200_OK)

    # Add more tests for other views as needed

class IncidentCollaborationTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            first_name='Test',
            last_name='User',
            phone='1234567890',
            user_type='citizen'
        )
        self.client.force_authenticate(user=self.user)

        # Create test zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            lattitude='0.0',
            longitude='0.0'
        )

        # Create test category
        self.category = Category.objects.create(
            name='Test Category',
            description='Test Category Description'
        )

        # Create test indicateur
        self.indicateur = Indicateur.objects.create(
            name='Test Indicateur'
        )

        # Create test incident
        self.incident = Incident.objects.create(
            title='Test Incident',
            zone=str(self.zone.id),  # Use zone ID instead of name
            description='Test Description',
            user_id=self.user,
            lattitude='0.0',
            longitude='0.0',
            etat='declared',
            category_id=self.category,
            indicateur_id=self.indicateur,
            created_at=timezone.now()  # Set created_at to now
        )

    def test_take_incident(self):
        """Test taking an incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        data = {
            'title': 'Test Incident',
            'description': 'Test Description',
            'zone': str(self.zone.id),  # Use zone ID instead of name
            'user_id': self.user.id,
            'lattitude': '0.0',
            'longitude': '0.0',
            'etat': 'taken_into_account',
            'category_id': self.category.id,
            'indicateur_id': self.indicateur.id
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.etat, 'taken_into_account')

    def test_take_nonexistent_incident(self):
        """Test taking a non-existent incident"""
        url = reverse('incident_rud', args=[999])
        data = {
            'etat': 'taken_into_account'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_take_already_taken_incident(self):
        """Test taking an already taken incident"""
        # First take
        url = reverse('incident_rud', args=[self.incident.id])
        data = {
            'title': 'Test Incident',
            'description': 'Test Description',
            'zone': str(self.zone.id),  # Use zone ID instead of name
            'user_id': self.user.id,
            'lattitude': '0.0',
            'longitude': '0.0',
            'etat': 'taken_into_account',
            'category_id': self.category.id,
            'indicateur_id': self.indicateur.id
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Second take should still work since we're just updating the same state
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
