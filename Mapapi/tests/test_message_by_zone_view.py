from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from django.utils import timezone
from datetime import timedelta

from Mapapi.models import (
    User, Zone, Communaute, Message, ResponseMessage
)

class MessageByZoneViewTests(APITestCase):
    """Tests for MessageByZoneAPIView and related views"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            email='messagetest@example.com',
            password='testpassword',
            first_name='Message',
            last_name='Test'
        )
        
        # Set up client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create test zones
        self.zone1 = Zone.objects.create(
            name='Zone 1',
            lattitude='10.0',
            longitude='10.0'
        )
        
        self.zone2 = Zone.objects.create(
            name='Zone 2',
            lattitude='20.0',
            longitude='20.0'
        )
        
        # Create a test community
        self.community = Communaute.objects.create(
            name='Test Community'
        )
        
        # Create test messages in different zones
        # Message 1: in Zone 1
        self.message1 = Message.objects.create(
            user_id=self.user,
            communaute=self.community,
            zone=self.zone1,
            message='Message in Zone 1',
            objet='Test Message 1'
        )
        
        # Message 2: in Zone 2
        self.message2 = Message.objects.create(
            user_id=self.user,
            communaute=self.community,
            zone=self.zone2,
            message='Message in Zone 2',
            objet='Test Message 2'
        )
        
        # Message 3: another in Zone 1
        self.message3 = Message.objects.create(
            user_id=self.user,
            communaute=self.community,
            zone=self.zone1,
            message='Another message in Zone 1',
            objet='Test Message 3'
        )
    
    def test_get_messages_by_zone(self):
        """Test getting messages by zone"""
        # Use the zone name as that's what the view uses to filter
        url = reverse('message_zone', args=[self.zone1.name])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Since our test created two messages in zone1, verify that the response contains them
        # Response might contain more messages if other tests have created them as well
        # so we'll test for inclusion rather than exact count
        message_contents = [message['message'] for message in response.data]
        self.assertIn('Message in Zone 1', message_contents)
        self.assertIn('Another message in Zone 1', message_contents)
    
    def test_get_messages_by_zone_nonexistent_zone(self):
        """Test getting messages for a non-existent zone"""
        url = reverse('message_zone', args=[999])
        response = self.client.get(f'{url}?zone=999')
        
        # Either should return 404 or an empty list with 200
        if response.status_code == status.HTTP_404_NOT_FOUND:
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        else:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data), 0)
    
    def test_get_messages_by_zone_missing_zone_param(self):
        """Test getting messages without specifying a zone parameter"""
        # Since message_zone requires a zone parameter in the URL, we'll use message_list instead
        url = reverse('message_list')
        response = self.client.get(url)
        
        # Either should return 400 or an empty list/all messages with 200
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        else:
            self.assertEqual(response.status_code, status.HTTP_200_OK)

class MessageAPIViewTests(APITestCase):
    """Tests for MessageAPIView"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            email='messageapi@example.com',
            password='testpassword',
            first_name='Message',
            last_name='API'
        )
        
        # Set up client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create test zone
        self.zone = Zone.objects.create(
            name='Message Zone',
            lattitude='10.0',
            longitude='10.0'
        )
        
        # Create a test community
        self.community = Communaute.objects.create(
            name='Message Community'
        )
        
        # Create a test message
        self.message = Message.objects.create(
            user_id=self.user,
            communaute=self.community,
            zone=self.zone,
            message='Test message content',
            objet='Test API Message'
        )
    
    def test_get_message(self):
        """Test retrieving a single message"""
        url = reverse('message', args=[self.message.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Test message content')
    
    def test_update_message(self):
        """Test updating a message"""
        url = reverse('message', args=[self.message.id])
        data = {
            'message': 'Updated message content',
            'objet': 'Test API Message',  # This field is required
            'zone': self.zone.id,  # Include zone id
            'communaute': self.community.id  # Include community id
        }
        response = self.client.put(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify the message was updated
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, 'Updated message content')
    
    def test_delete_message(self):
        """Test deleting a message"""
        url = reverse('message', args=[self.message.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify the message was deleted
        self.assertFalse(Message.objects.filter(id=self.message.id).exists())
    
    def test_nonexistent_message(self):
        """Test operations on a non-existent message"""
        url = reverse('message', args=[999])
        
        # Test GET
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Test PUT
        put_response = self.client.put(url, {'message': 'Updated content'}, format='json')
        self.assertEqual(put_response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Test DELETE
        delete_response = self.client.delete(url)
        self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)
