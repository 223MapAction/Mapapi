from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
import json
from unittest.mock import patch, MagicMock

from Mapapi.models import (
    User, Zone, Category, Incident, PhoneOTP, Collaboration, ImageBackground
)
from Mapapi.serializer import MessageSerializer

class PhoneOTPViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('verify_otp')
        # Create a user for testing verification
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpassword',
            first_name='Test',
            last_name='User',
            phone='1234567890'
        )

    @patch('Mapapi.views.send_sms')
    def test_generate_otp(self, mock_send_sms):
        """Test generating OTP for a valid phone number"""
        # Configure mock to return True (successful sending)
        mock_send_sms.return_value = True
        
        data = {'phone_number': '1234567890'}
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue('otp_code' in response.data)
        
        # Verify OTP was created and SMS was sent
        self.assertTrue(PhoneOTP.objects.filter(phone_number='1234567890').exists())
        mock_send_sms.assert_called_once()

    def test_verify_otp_success(self):
        """Test verifying a valid OTP"""
        # Create an OTP record
        otp = '123456'
        phone_otp = PhoneOTP.objects.create(
            phone_number='1234567890',
            otp_code=otp
        )
        
        # Get the OTP record using the phone number
        response = self.client.get(
            f"{self.url}?phone_number=1234567890"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue('otp_code' in response.data)
        self.assertEqual(response.data['otp_code'], otp)

class OverpassApiIntegrationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('overpassapi')

    @patch('overpy.Overpass')
    def test_get_nearby_amenities(self, mock_overpass):
        """Test getting nearby amenities from Overpass API"""
        # Mock the Overpass API response
        mock_api = MagicMock()
        mock_overpass.return_value = mock_api
        
        # Create mock nodes with tags
        mock_node1 = MagicMock()
        mock_node1.tags = {'amenity': 'pharmacy', 'name': 'Test Pharmacy'}
        
        mock_node2 = MagicMock()
        mock_node2.tags = {'amenity': 'school', 'name': 'Test School'}
        
        # Set up the mock query result
        mock_result = MagicMock()
        mock_result.nodes = [mock_node1, mock_node2]
        mock_api.query.return_value = mock_result
        
        # Make the request
        response = self.client.get(f'{self.url}?latitude=10.0&longitude=10.0')
        
        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Parse the JSON response
        results = json.loads(response.content)
        
        # Verify the results
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['amenity'], 'pharmacy')
        self.assertEqual(results[0]['name'], 'Test Pharmacy')
        self.assertEqual(results[1]['amenity'], 'school')
        self.assertEqual(results[1]['name'], 'Test School')

class CollaborationViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        self.zone = Zone.objects.create(name='Test Zone')
        self.category = Category.objects.create(name='Test Category')
        self.incident = Incident.objects.create(
            title='Test Incident',
            description='Test Description',
            zone=self.zone.name,
            taken_by=self.user,
            category_id=self.category
        )
        self.collaboration_url = reverse('collaboration')
        self.decline_url = reverse('decline-collaboration')

    @patch('Mapapi.signals.post_save.disconnect')
    def test_create_collaboration(self, mock_disconnect):
        """Test creating a collaboration request"""
        data = {
            'user': self.user.id,
            'incident': self.incident.id,
            'end_date': (timezone.now() + timedelta(days=7)).date().isoformat(),
            'status': 'pending'
        }
        response = self.client.post(self.collaboration_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Collaboration.objects.count(), 1)

    @patch('Mapapi.signals.post_save.disconnect')
    @patch('Mapapi.views.send_email.delay')  # Mock the email sending to avoid Redis errors
    def test_decline_collaboration(self, mock_email, mock_disconnect):
        """Test declining a collaboration request"""
        # Create a collaboration first
        collaboration = Collaboration.objects.create(
            user=self.user,
            incident=self.incident,
            end_date=(timezone.now() + timedelta(days=7)).date(),
            status='pending'
        )
        
        data = {'collaboration_id': collaboration.id}
        response = self.client.post(self.decline_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify collaboration status is updated
        collaboration.refresh_from_db()
        self.assertEqual(collaboration.status, 'declined')

class IncidentSearchViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        self.category = Category.objects.create(name='Test Category')
        self.zone = Zone.objects.create(name='Test Zone')
        
        # Create incidents with different titles
        self.incident1 = Incident.objects.create(
            title='Emergency Flood',
            description='Flooding in area',
            zone=self.zone.name,
            category_id=self.category,
            user_id=self.user,
            taken_by=self.user
        )
        self.incident2 = Incident.objects.create(
            title='Fire Alert',
            description='Fire in building',
            zone=self.zone.name,
            category_id=self.category,
            user_id=self.user,
            taken_by=self.user
        )
        self.incident3 = Incident.objects.create(
            title='Traffic Accident',
            description='Major accident on highway',
            zone=self.zone.name,
            category_id=self.category,
            user_id=self.user,
            taken_by=self.user
        )
        self.url = reverse('search')

    def test_search_incidents_by_title(self):
        """Test searching incidents by title"""
        response = self.client.get(f"{self.url}?search_term=flood")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Emergency Flood')
        
        # Test another search term
        response = self.client.get(f"{self.url}?search_term=fire")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Fire Alert')

    def test_search_incidents_by_description(self):
        """Test searching incidents by description"""
        response = self.client.get(f"{self.url}?search_term=accident")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Traffic Accident')

class UserListAPIViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.zone = Zone.objects.create(name="Test Zone")
        self.url = reverse('user_list')
        self.valid_data = {
            'email': 'test_user@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '1234567890',
            'password': 'testpassword123',
            'zones': [self.zone.id],
            'user_type': 'admin'
        }

    @patch('Mapapi.views.send_email.delay')
    def test_create_user_with_zones(self, mock_send_email):
        """Test creating a user with zones"""
        response = self.client.post(self.url, self.valid_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        
        user = User.objects.get(email='test_user@example.com')
        self.assertEqual(user.zones.count(), 1)
        self.assertEqual(user.zones.first().id, self.zone.id)
