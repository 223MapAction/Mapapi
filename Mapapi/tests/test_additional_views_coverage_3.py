import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from Mapapi.models import (
    User, Incident, Message, Zone, Category, Collaboration, 
    PhoneOTP, ResponseMessage, ImageBackground
)
from Mapapi.views import get_random
from Mapapi.serializer import MessageSerializer
from rest_framework.response import Response


class UserAPIListViewTests(APITestCase):
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
        
        # Verify email was sent with correct parameters
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        self.assertEqual(call_args[0], '[MAP ACTION] - Création de Compte Admin')
        self.assertEqual(call_args[1], 'mail_add_admin.html')
        self.assertEqual(call_args[3], 'test_user@example.com')

    @patch('Mapapi.views.send_email.delay')
    def test_create_user_with_organisation_user_type(self, mock_send_email):
        """Test creating a user with organisation user type"""
        data = self.valid_data.copy()
        data['user_type'] = 'organisation'
        data['organisation_name'] = 'Test Organization'  # Adding organization name
        data['organisation_address'] = 'Test Address'  # Adding organization address
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        self.assertEqual(call_args[0], '[MAP ACTION] - Création de Compte Organisation')
        self.assertEqual(call_args[1], 'mail_add_account.html')

    def test_create_user_invalid_data(self):
        """Test creating a user with invalid data"""
        invalid_data = self.valid_data.copy()
        invalid_data.pop('email')  # Missing required field
        
        response = self.client.post(self.url, invalid_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)


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


class MessageByUserAPIViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create(
            email='testuser@example.com',
            first_name='Test',
            last_name='User',
            password='testpassword'
        )
        self.message1 = Message.objects.create(
            objet='Test Message 1',
            message='Content 1',
            user_id=self.user
        )
        self.message2 = Message.objects.create(
            objet='Test Message 2',
            message='Content 2',
            user_id=self.user
        )
        self.url = reverse('message_user', kwargs={'id': self.user.id})
        self.client = APIClient()

    def test_get_messages_by_user(self):
        """Test retrieving messages by user ID"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        # Verify both messages are returned
        objects = [message['objet'] for message in response.data]
        self.assertIn('Test Message 1', objects)
        self.assertIn('Test Message 2', objects)

    def test_get_messages_by_nonexistent_user(self):
        """Test retrieving messages for a user that doesn't exist"""
        url = reverse('message_user', kwargs={'id': 999})  # Non-existent ID
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DeclineCollaborationViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create(
            email='user@example.com',
            first_name='Test',
            last_name='User',
            password='testpassword'
        )
        self.incident = Incident.objects.create(
            title='Test Incident',
            description='Test Description',
            taken_by=self.user  # Set taken_by to avoid null constraint issues
        )
        self.collaboration = Collaboration.objects.create(
            user=self.user,
            incident=self.incident,
            end_date=(timezone.now() + timedelta(days=7)).date(),
            status='pending'
        )
        self.url = reverse('decline-collaboration')
        self.client = APIClient()

    @patch('Mapapi.signals.post_save.disconnect')
    @patch('Mapapi.views.send_email.delay')
    def test_decline_collaboration(self, mock_send_email, mock_disconnect):
        """Test declining a collaboration request"""
        data = {'collaboration_id': self.collaboration.id}
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify collaboration status is updated
        self.collaboration.refresh_from_db()
        self.assertEqual(self.collaboration.status, 'declined')

    @patch('Mapapi.views.send_email.delay')
    def test_decline_nonexistent_collaboration(self, mock_send_email):
        """Test declining a non-existent collaboration"""
        data = {'collaboration_id': 999}  # Non-existent ID
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ImageBackgroundAPIViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.image = ImageBackground.objects.create(
            photo=SimpleUploadedFile(name='test_image.jpg', content=b'file_content', content_type='image/jpeg')
        )
        self.url = reverse('image', args=[self.image.id])

    def test_get_image_background(self):
        """Test retrieving a single image background"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['photo'])

    def test_update_image_background(self):
        """Test updating an image background"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Need to use multipart form for file uploads
        # Adding more fields to ensure validation passes
        updated_data = {
            'photo': SimpleUploadedFile(name='updated_image.jpg', content=b'updated_content', content_type='image/jpeg'),
            'title': 'Updated Image Title',  # Adding potential required fields
            'description': 'Updated image description'
        }
        response = self.client.put(self.url, updated_data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify the image background is updated
        self.image.refresh_from_db()
        self.assertTrue('updated_image' in self.image.photo.name)

    def test_delete_image_background(self):
        """Test deleting an image background"""
        response = self.client.delete(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ImageBackground.objects.count(), 0)
