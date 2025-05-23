from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from django.utils import timezone
from datetime import timedelta
import json
from django.conf import settings

from Mapapi.models import (
    User, Zone, Category, Incident, Indicateur, 
    Evenement, Communaute, Collaboration, PasswordReset, Message, ResponseMessage, Rapport,
    PhoneOTP
)
from django.core.mail import EmailMultiAlternatives
from unittest.mock import patch, MagicMock


class GetTokenByMailViewTests(APITestCase):
    """Tests for GetTokenByMailView"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='token_test@example.com',
            password='testpassword',
            first_name='Token',
            last_name='Test'
        )
        
    def test_get_token_successful(self):
        """Test successfully getting a token by email"""
        url = reverse('token_by_mail')
        data = {'email': self.user.email}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['status'], 'success')
        
    def test_get_token_nonexistent_email(self):
        """Test getting a token with a non-existent email"""
        url = reverse('token_by_mail')
        data = {'email': 'nonexistent@example.com'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class IncidentFilterAdditionalTests(APITestCase):
    """Additional tests for IncidentFilterView"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='filter_test@example.com',
            password='testpassword',
            first_name='Filter',
            last_name='Test'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create a zone
        self.zone = Zone.objects.create(name='Test Zone', lattitude='10.0', longitude='10.0')
        
        # Create a category
        self.category = Category.objects.create(name='Test Category')
        
        # Create some test incidents
        self.incident1 = Incident.objects.create(
            title='Incident 1',
            description='Description 1',
            zone=self.zone,
            category=self.category,
            etat='pending',
            created_at=timezone.now() - timedelta(days=5)
        )
        
        self.incident2 = Incident.objects.create(
            title='Incident 2',
            description='Description 2',
            zone=self.zone,
            category=self.category,
            etat='resolved',
            created_at=timezone.now() - timedelta(days=2)
        )
    
    def test_filter_by_status(self):
        """Test filtering incidents by status"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=status&status=pending')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that only the pending incident is returned
        incident_titles = [incident['title'] for incident in response.data]
        self.assertIn('Incident 1', incident_titles)
        self.assertNotIn('Incident 2', incident_titles)
        
    def test_filter_by_date_range(self):
        """Test filtering incidents by date range"""
        start_date = (timezone.now() - timedelta(days=6)).strftime('%Y-%m-%d')
        end_date = (timezone.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=date&start_date={start_date}&end_date={end_date}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify filtering works by date range
        incident_titles = [incident['title'] for incident in response.data]
        self.assertIn('Incident 1', incident_titles)
        self.assertNotIn('Incident 2', incident_titles)
    
    def test_filter_by_category(self):
        """Test filtering incidents by category"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=category&category={self.category.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Both incidents have the same category
        self.assertEqual(len(response.data), 2)
        
    def test_filter_by_zone(self):
        """Test filtering incidents by zone"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=zone&zone={self.zone.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Both incidents have the same zone
        self.assertEqual(len(response.data), 2)
        
    def test_filter_invalid_type(self):
        """Test filtering with an invalid filter type"""
        url = reverse('incident_filter')
        response = self.client.get(f'{url}?filter_type=invalid')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CollaborationViewTests(APITestCase):
    """Tests for CollaborationView and related views"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create users
        self.sender = User.objects.create_user(
            email='sender@example.com',
            password='senderpassword',
            first_name='Sender',
            last_name='User'
        )
        
        self.receiver = User.objects.create_user(
            email='receiver@example.com',
            password='receiverpassword',
            first_name='Receiver',
            last_name='User'
        )
        
        # Create an incident
        self.zone = Zone.objects.create(name='Collaboration Zone', lattitude='10.0', longitude='10.0')
        self.category = Category.objects.create(name='Collaboration Category')
        self.incident = Incident.objects.create(
            title='Collaboration Incident',
            description='Incident for collaboration testing',
            zone=self.zone,
            category=self.category,
            etat='pending',
            user=self.sender
        )
        
        self.client.force_authenticate(user=self.sender)
    
    def test_create_collaboration(self):
        """Test creating a collaboration request"""
        url = reverse('collaboration')
        data = {
            'incident': self.incident.id,
            'sender': self.sender.id,
            'receiver': self.receiver.id,
            'message': 'Please collaborate on this incident.'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Collaboration.objects.filter(sender=self.sender, receiver=self.receiver).exists())
    
    @patch('Mapapi.Send_mails.send_email')
    def test_accept_collaboration(self, mock_send_email):
        """Test accepting a collaboration request"""
        # First create a collaboration
        collaboration = Collaboration.objects.create(
            incident=self.incident,
            sender=self.sender,
            receiver=self.receiver,
            message='Please collaborate on this incident.',
            status='pending'
        )
        
        # Log in as the receiver
        self.client.force_authenticate(user=self.receiver)
        
        # Accept the collaboration
        url = reverse('accept_collaboration')
        data = {
            'collaboration_id': collaboration.id,
            'message': 'I accept this collaboration.'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that the collaboration status was updated
        collaboration.refresh_from_db()
        self.assertEqual(collaboration.status, 'accepted')
    
    def test_accept_nonexistent_collaboration(self):
        """Test accepting a non-existent collaboration"""
        url = reverse('accept_collaboration')
        data = {
            'collaboration_id': 999,  # Non-existent ID
            'message': 'I accept this collaboration.'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    @patch('Mapapi.Send_mails.send_email')
    def test_decline_collaboration(self, mock_send_email):
        """Test declining a collaboration request"""
        # First create a collaboration
        collaboration = Collaboration.objects.create(
            incident=self.incident,
            sender=self.sender,
            receiver=self.receiver,
            message='Please collaborate on this incident.',
            status='pending'
        )
        
        # Log in as the receiver
        self.client.force_authenticate(user=self.receiver)
        
        # Decline the collaboration
        url = reverse('decline_collaboration')
        data = {
            'collaboration_id': collaboration.id,
            'message': 'I decline this collaboration.'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that the collaboration status was updated
        collaboration.refresh_from_db()
        self.assertEqual(collaboration.status, 'declined')


class PhoneOTPViewTests(APITestCase):
    """Tests for PhoneOTPView"""
    
    def setUp(self):
        self.client = APIClient()
        self.phone_number = '+1234567890'
    
    @patch('Mapapi.views.send_sms')
    def test_generate_and_send_otp(self, mock_send_sms):
        """Test generating and sending an OTP"""
        url = reverse('phone_otp')
        data = {'phone_number': self.phone_number}
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('message', response.data)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify OTP was created in database
        self.assertTrue(PhoneOTP.objects.filter(phone_number=self.phone_number).exists())
        
        # Verify send_sms was called
        mock_send_sms.assert_called_once()
    
    @patch('Mapapi.views.send_sms')
    def test_verify_otp_successful(self, mock_send_sms):
        """Test successfully verifying an OTP"""
        # First create an OTP
        otp_code = '123456'  # Test OTP code
        PhoneOTP.objects.create(
            phone_number=self.phone_number,
            otp_code=otp_code,
            verified=False
        )
        
        # Now verify it
        url = reverse('phone_otp')
        data = {
            'phone_number': self.phone_number,
            'otp_code': otp_code,
            'action': 'verify'
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify OTP was marked as verified
        otp_obj = PhoneOTP.objects.get(phone_number=self.phone_number)
        self.assertTrue(otp_obj.verified)
    
    def test_verify_otp_invalid(self):
        """Test verifying with an invalid OTP"""
        # First create an OTP
        PhoneOTP.objects.create(
            phone_number=self.phone_number,
            otp_code='123456',
            verified=False
        )
        
        # Now try to verify with wrong code
        url = reverse('phone_otp')
        data = {
            'phone_number': self.phone_number,
            'otp_code': '654321',  # Wrong code
            'action': 'verify'
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'failure')
        
        # Verify OTP was not marked as verified
        otp_obj = PhoneOTP.objects.get(phone_number=self.phone_number)
        self.assertFalse(otp_obj.verified)


class MessageAdditionalTests(APITestCase):
    """Additional tests for Message-related views"""
    
    def setUp(self):
        self.client = APIClient()
        # Create a test user for authentication
        self.user = User.objects.create_user(
            email='message_test@example.com',
            password='testpassword',
            first_name='Message',
            last_name='Test'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create test zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            lattitude='10.0',
            longitude='10.0'
        )
        
        # Create a test community
        self.community = Communaute.objects.create(name='Test Community')
        
        # Create test messages
        self.message1 = Message.objects.create(
            user=self.user,
            community=self.community,
            message='Test message 1',
            zone=self.zone
        )
        
        self.message2 = Message.objects.create(
            user=self.user,
            community=self.community,
            message='Test message 2',
            zone=self.zone
        )
    
    def test_messages_by_zone(self):
        """Test retrieving messages by zone"""
        url = reverse('message_by_zone')
        response = self.client.get(f'{url}?zone={self.zone.id}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)  # Both messages have the same zone
        messages = [msg['message'] for msg in response.data]
        self.assertIn('Test message 1', messages)
        self.assertIn('Test message 2', messages)
    
    def test_messages_by_user(self):
        """Test retrieving messages by user"""
        url = reverse('message_by_user', args=[self.user.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)  # Both messages have the same user
        messages = [msg['message'] for msg in response.data]
        self.assertIn('Test message 1', messages)
        self.assertIn('Test message 2', messages)


class ResponseMessageTests(APITestCase):
    """Tests for ResponseMessage-related views"""
    
    def setUp(self):
        self.client = APIClient()
        # Create a test user for authentication
        self.user = User.objects.create_user(
            email='response_test@example.com',
            password='testpassword',
            first_name='Response',
            last_name='Test'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create a test community
        self.community = Communaute.objects.create(name='Response Community')
        
        # Create a test message
        self.message = Message.objects.create(
            user=self.user,
            community=self.community,
            message='Original message'
        )
        
        # Create a test response
        self.response = ResponseMessage.objects.create(
            user=self.user,
            message=self.message,
            response='Test response'
        )
    
    def test_get_response(self):
        """Test retrieving a response"""
        url = reverse('response_message', args=[self.response.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['response'], 'Test response')
    
    def test_create_response(self):
        """Test creating a response"""
        url = reverse('response_messages')
        data = {
            'user': self.user.id,
            'message': self.message.id,
            'response': 'New response'
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ResponseMessage.objects.count(), 2)  # Original + new
    
    def test_responses_by_message(self):
        """Test retrieving responses by message"""
        url = reverse('response_by_message', args=[self.message.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['response'], 'Test response')
