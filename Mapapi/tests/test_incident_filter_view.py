from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from django.utils import timezone
from datetime import timedelta
import json

from Mapapi.models import (
    User, Zone, Category, Incident
)

class IncidentFilterViewTests(APITestCase):
    """Tests for IncidentFilterView"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            email='incidentfilter@example.com',
            password='testpassword',
            first_name='Incident',
            last_name='Filter'
        )
        
        # Set up client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create test zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            lattitude='10.0',
            longitude='10.0'
        )
        
        # Create another zone for filtering tests
        self.zone2 = Zone.objects.create(
            name='Another Zone',
            lattitude='20.0',
            longitude='20.0'
        )
        
        # Create test category
        self.category = Category.objects.create(
            name='Test Category'
        )
        
        # Create another category for filtering tests
        self.category2 = Category.objects.create(
            name='Another Category'
        )
        
        # Create test incidents with different statuses, dates, categories, and zones
        # Incident 1: pending, recent, zone1, category1
        self.incident1 = Incident.objects.create(
            title='Incident 1',
            description='Pending incident in zone 1',
            zone=self.zone.name,  # Zone should be a string, not an object
            category_id=self.category,  # Use category_id, not category
            etat='pending'
            # created_at is auto_now_add, so we don't need to set it
        )
        
        # Incident 2: resolved, older, zone2, category1
        self.incident2 = Incident.objects.create(
            title='Incident 2',
            description='Resolved incident in zone 2',
            zone=self.zone2.name,
            category_id=self.category,
            etat='resolved'
        )
        
        # Incident 3: in_progress, recent, zone1, category2
        self.incident3 = Incident.objects.create(
            title='Incident 3',
            description='In progress incident in zone 1',
            zone=self.zone.name,
            category_id=self.category2,
            etat='in_progress'
        )
    
    def test_filter_by_today(self):
        """Test filtering incidents by today's date"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=today')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # All incidents created today should be returned
        # Since our test incidents are created during the test, they all have today's date
        self.assertGreaterEqual(len(response.data), 1)
    
    def test_filter_by_last_7_days(self):
        """Test filtering incidents by last 7 days"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=last_7_days')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # All incidents created in the last 7 days should be returned
        # Since our test incidents are created during the test, they all should be included
        self.assertGreaterEqual(len(response.data), 1)
    
    def test_filter_by_custom_range(self):
        """Test filtering incidents by custom date range"""
        url = reverse('incident_filter')
        custom_start = (timezone.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        custom_end = timezone.now().strftime('%Y-%m-%d')
        
        response = self.client.get(f'{url}?filter_type=custom_range&custom_start={custom_start}&custom_end={custom_end}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Since our test incidents are created during the test, they should be within this range
        self.assertGreaterEqual(len(response.data), 1)
    
    def test_filter_by_last_month(self):
        """Test filtering incidents by last month"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=last_month')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response should be a list (possibly empty)
        self.assertIsInstance(response.data, list)
    
    def test_filter_by_this_month(self):
        """Test filtering incidents by this month"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=this_month')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Since our test incidents are created during the test, they should be from this month
        self.assertGreaterEqual(len(response.data), 1)
    
    def test_filter_invalid_type(self):
        """Test filtering with an invalid filter type"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=invalid')
        
        # The view returns all incidents when an invalid filter is provided
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_filter_missing_parameters(self):
        """Test filtering without any filter_type parameter"""
        url = reverse('incident_filter')
        # No filter_type parameter
        response = self.client.get(url)
        
        # The view returns all incidents when no filter is provided
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # All incidents should be returned
        self.assertGreaterEqual(len(response.data), 1)
