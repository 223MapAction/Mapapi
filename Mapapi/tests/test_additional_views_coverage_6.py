from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from Mapapi.models import User, Zone, Message, ResponseMessage, Participate, Evenement
from django.contrib.auth import authenticate
from unittest.mock import patch, MagicMock
import json
import os
from datetime import datetime


class ParticipateAPIViewTests(APITestCase):
    """Tests for the ParticipateAPIView"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            email='test@example.com', 
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        
        # Create a test event
        self.event = Evenement.objects.create(
            title='Test Event',
            description='Test Description',
            zone='Test Zone',
            lieu='Test Location',
            date=datetime.now()
        )
        
        # Create a test participation
        self.participate = Participate.objects.create(
            evenement_id=self.event,
            user_id=self.user
        )
        
        self.url = reverse('participate_rud', args=[self.participate.id])
        self.client.force_authenticate(user=self.user)
    
    def test_get_participate(self):
        """Test retrieving a participation"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_update_participate(self):
        """Test updating a participation"""
        # Create a new event for updating
        new_event = Evenement.objects.create(
            title='New Event',
            description='New Description',
            zone='New Zone',
            lieu='New Location',
            date=datetime.now()
        )
        
        data = {
            'evenement_id': new_event.id,
            'user_id': self.user.id
        }
        
        response = self.client.put(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.participate.refresh_from_db()
        self.assertEqual(self.participate.evenement_id.id, new_event.id)
    
    def test_delete_participate(self):
        """Test deleting a participation"""
        response = self.client.delete(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Participate.objects.count(), 0)


class ParticipateAPIListViewTests(APITestCase):
    """Tests for the ParticipateAPIListView"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            email='test@example.com', 
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        
        # Create a test event
        self.event = Evenement.objects.create(
            title='Test Event',
            description='Test Description',
            zone='Test Zone',
            lieu='Test Location',
            date=datetime.now()
        )
        
        self.url = reverse('participate')
        self.client.force_authenticate(user=self.user)
    
    def test_get_participates(self):
        """Test retrieving all participations"""
        # Create some test participations
        Participate.objects.create(
            evenement_id=self.event,
            user_id=self.user
        )
        
        Participate.objects.create(
            evenement_id=self.event,
            user_id=self.user
        )
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)
    
    def test_create_participate(self):
        """Test creating a new participation"""
        data = {
            'evenement_id': self.event.id,
            'user_id': self.user.id
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Participate.objects.count(), 1)


class MessageByUserAPIViewTests(APITestCase):
    """Tests for the MessageByUserAPIView"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            email='test@example.com', 
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        
        # Create a test zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            description='Test Description'
        )
        
        # Create messages for the user
        self.message1 = Message.objects.create(
            objet='Message 1',
            message='Test Message 1',
            zone=self.zone,
            user_id=self.user
        )
        
        self.message2 = Message.objects.create(
            objet='Message 2',
            message='Test Message 2',
            zone=self.zone,
            user_id=self.user
        )
        
        self.url = reverse('message_user', args=[self.user.id])
        self.client.force_authenticate(user=self.user)
    
    def test_get_messages_by_user(self):
        """Test retrieving messages by user ID"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        # Verify both messages are returned
        messages = [msg['objet'] for msg in response.data]
        self.assertIn('Message 1', messages)
        self.assertIn('Message 2', messages)
    
    def test_get_messages_by_nonexistent_user(self):
        """Test retrieving messages for a user that doesn't exist"""
        # Use a non-existent user ID
        url = reverse('message_user', args=[999])
        response = self.client.get(url)
        
        # Should return an empty list, not a 404
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)


# Not implementing ResponseByMessageAPIViewTests because there's no URL pattern specifically for ResponseByMessageAPIView
# Instead, we'll create another test class to improve coverage

class MessageAPIViewTests(APITestCase):
    """Tests for the MessageAPIView"""
    
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            email='test@example.com', 
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        
        # Create a test zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            description='Test Description'
        )
        
        # Create a test message
        self.message = Message.objects.create(
            objet='Test Message',
            message='Message Content',
            zone=self.zone,
            user_id=self.user
        )
        
        self.url = reverse('message', args=[self.message.id])
        self.client.force_authenticate(user=self.user)
    
    def test_get_message(self):
        """Test retrieving a message"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['objet'], 'Test Message')
        self.assertEqual(response.data['message'], 'Message Content')
    
    def test_update_message(self):
        """Test updating a message"""
        data = {
            'objet': 'Updated Message',
            'message': 'Updated Content',
            'zone': self.zone.id,
            'user_id': self.user.id
        }
        
        response = self.client.put(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.message.refresh_from_db()
        self.assertEqual(self.message.objet, 'Updated Message')
        self.assertEqual(self.message.message, 'Updated Content')
    
    def test_delete_message(self):
        """Test deleting a message"""
        response = self.client.delete(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Message.objects.count(), 0)
