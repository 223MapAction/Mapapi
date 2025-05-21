from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from Mapapi.models import User, Incident, Zone, Category
from django.utils import timezone
from datetime import timedelta

class IncidentManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create test user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone='1234567890',
            user_type='citizen'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create test zone and category
        self.zone = Zone.objects.create(name='Test Zone')
        self.category = Category.objects.create(name='Test Category')
        
        # Create test incident
        self.incident = Incident.objects.create(
            title='Test Incident',
            description='Test Description',
            zone=self.zone.name,
            user_id=self.user,
            category_id=self.category,
            etat='declared',
            lattitude='40.7128',
            longitude='-74.0060'
        )

    def test_create_incident(self):
        """Test creating a new incident"""
        url = reverse('incident')
        data = {
            'title': 'New Incident',
            'description': 'New Description',
            'zone': self.zone.name,
            'user_id': self.user.id
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Incident.objects.count(), 2)  # Including setup incident
        self.assertEqual(Incident.objects.latest('id').title, 'New Incident')

    def test_list_incidents(self):
        """Test listing all incidents"""
        url = reverse('incident')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

    def test_get_incident_detail(self):
        """Test getting a specific incident's details"""
        url = reverse('incident_rud', args=[self.incident.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Incident')

    def test_update_incident(self):
        """Test updating an incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        data = {
            'title': 'Updated Incident',
            'description': 'Updated Description',
            'zone': self.zone.name,
            'user_id': self.user.id,
            'etat': 'declared'  # Include etat in update data
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.title, 'Updated Incident')
        self.assertEqual(self.incident.etat, 'declared')

    def test_delete_incident(self):
        """Test deleting an incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Incident.objects.count(), 0)

    def test_incident_by_zone(self):
        """Test getting incidents for a specific zone"""
        url = reverse('incidentZone', args=[self.zone.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_incident_not_resolved(self):
        """Test getting unresolved incidents"""
        url = reverse('incidentNotResolved')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertIsInstance(response.data['results'], list)

    def test_incident_by_month(self):
        """Test getting incidents by month"""
        url = reverse('incidentByMonth')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertIsInstance(response.data['data'], list)

    def test_incident_by_week(self):
        """Test getting incidents by week"""
        url = reverse('IncidentOnWeek')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'incidents by week ')
        self.assertIsInstance(response.data['data'], list)

    def test_incident_resolved(self):
        """Test getting resolved incidents"""
        # Create resolved incident
        Incident.objects.create(
            title='Test Incident Resolved',
            zone=self.zone.name,
            description='Test Description',
            user_id=self.user,
            etat='resolved'
        )
        
        url = reverse('incidentResolved')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertTrue(len(response.data['results']) > 0)
        self.assertEqual(response.data['results'][0]['etat'], 'resolved')

    def test_invalid_incident_creation(self):
        """Test creating an incident with invalid data"""
        url = reverse('incident')
        invalid_data = {
            # Missing all required fields
            'description': 'Test Description'
        }
        response = self.client.post(url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_nonexistent_incident(self):
        """Test updating a non-existent incident"""
        url = reverse('incident_rud', args=[99999])  # Non-existent ID
        data = {'title': 'Updated Title'}
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
