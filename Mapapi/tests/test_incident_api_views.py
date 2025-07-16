from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from Mapapi.models import Incident, Zone, Category, Indicateur
from django.utils import timezone

User = get_user_model()

class IncidentAPIViewsTests(TestCase):
    """Tests for incident API views to improve coverage"""

    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpassword'
        )
        
        # Create zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            lattitude='10.0',
            longitude='10.0'
        )
        
        # Create category
        self.category = Category.objects.create(
            name='Test Category',
            description='Test Description'
        )
        
        # Create indicateur
        self.indicateur = Indicateur.objects.create(
            name='Test Indicateur'
        )
        
        # Create incident
        self.incident = Incident.objects.create(
            title='Test Incident',
            zone=str(self.zone.name),
            description='Test Description',
            user_id=self.user,
            lattitude='10.0',
            longitude='10.0',
            etat='declared',
            category_id=self.category,
            indicateur_id=self.indicateur
        )
        
        # Set up client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    def test_incident_post(self):
        """Test creating a new incident"""
        url = reverse('incident')
        data = {
            'title': 'New Incident',
            'zone': str(self.zone.name),
            'description': 'New Description',
            'lattitude': '20.0',
            'longitude': '20.0',
            'etat': 'declared',
            'category_id': self.category.id,
            'indicateur_id': self.indicateur.id
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Incident.objects.count(), 2)  # Original + new one
    
    def test_incident_post_missing_zone(self):
        """Test creating incident with missing zone"""
        url = reverse('incident')
        data = {
            'title': 'New Incident',
            'description': 'New Description',
            'lattitude': '20.0',
            'longitude': '20.0',
            'etat': 'declared',
            'category_id': self.category.id,
            'indicateur_id': self.indicateur.id
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('zone', response.data)
    
    def test_incident_get_by_id(self):
        """Test retrieving an incident by ID"""
        url = reverse('incident_rud', args=[self.incident.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Incident')
    
    def test_incident_update(self):
        """Test updating an incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        data = {
            'title': 'Updated Incident',
            'description': 'Updated Description',
            'zone': str(self.zone.name),
            'lattitude': '10.0',
            'longitude': '10.0',
            'etat': 'declared',
            'category_id': self.category.id,
            'indicateur_id': self.indicateur.id
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Incident')
        self.assertEqual(response.data['description'], 'Updated Description')
    
    def test_incident_delete(self):
        """Test deleting an incident"""
        url = reverse('incident_rud', args=[self.incident.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Incident.objects.count(), 0)
    
    def test_incident_by_month(self):
        """Test incident by month endpoint"""
        url = reverse('incidentByMonth')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
    def test_incident_resolved(self):
        """Test incident resolved endpoint"""
        # Create a resolved incident
        resolved_incident = Incident.objects.create(
            title='Resolved Incident',
            zone=str(self.zone.name),
            description='Resolved Description',
            user_id=self.user,
            lattitude='15.0',
            longitude='15.0',
            etat='resolved',
            category_id=self.category,
            indicateur_id=self.indicateur
        )
        
        url = reverse('incidentResolved')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Response is paginated
        self.assertIn('results', response.data)
        
        # Should have at least one resolved incident
        found_resolved = False
        for incident in response.data['results']:
            if incident['title'] == 'Resolved Incident':
                found_resolved = True
                break
        self.assertTrue(found_resolved)
    
    def test_incident_not_resolved(self):
        """Test incident not resolved endpoint"""
        url = reverse('incidentNotResolved')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Response is paginated
        self.assertIn('results', response.data)

        # Should have our test incident which is not resolved
        found_not_resolved = False
        for incident in response.data['results']:
            if incident['title'] == 'Test Incident':
                found_not_resolved = True
                break
        self.assertTrue(found_not_resolved)
