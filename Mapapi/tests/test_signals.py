from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from Mapapi.models import Incident, Zone, Collaboration, Notification
from unittest.mock import patch
import logging
from datetime import date, timedelta

User = get_user_model()

class SignalTests(TestCase):
    def setUp(self):
        # Create test users with organizations
        self.org1 = "Organization 1"
        self.org2 = "Organization 2"
        
        self.user1 = User.objects.create_user(
            email='user1@test.com',
            password='testpass123',
            organisation=self.org1,
            first_name='User',
            last_name='One'
        )
        
        self.user2 = User.objects.create_user(
            email='user2@test.com',
            password='testpass123',
            organisation=self.org2,
            first_name='User',
            last_name='Two'
        )
        
        # Create a test zone
        self.zone = Zone.objects.create(
            name="Test Zone",
            description="Test Zone Description"
        )
        
        # Create a test incident
        self.incident = Incident.objects.create(
            title="Test Incident",
            description="Test Description",
            zone=self.zone.name,
            user_id=self.user1,
            taken_by=self.user2
        )

    @patch('Mapapi.Send_mails.send_email.delay')
    def test_collaboration_signal_success(self, mock_send_email):
        """Test successful collaboration signal handling"""
        # Create a collaboration with end_date
        collaboration = Collaboration.objects.create(
            incident=self.incident,
            user=self.user1,
            end_date=date.today() + timedelta(days=30)
        )
        
        # Check if email was called
        mock_send_email.assert_called_once()
        
        # Verify email arguments
        call_args = mock_send_email.call_args[1]
        self.assertEqual(call_args['subject'], 'Nouvelle demande de collaboration')
        self.assertEqual(call_args['template_name'], 'emails/collaboration_request.html')
        self.assertEqual(call_args['to_email'], self.user2.email)
        
        # Check if notification was created
        notification = Notification.objects.filter(user=self.user2).first()
        self.assertIsNotNone(notification)
        self.assertIn(self.org1, notification.message)
        self.assertIn(self.incident.title, notification.message)
        self.assertEqual(notification.colaboration, collaboration)

    @patch('Mapapi.Send_mails.send_email.delay')
    def test_collaboration_signal_no_email(self, mock_send_email):
        """Test collaboration signal when user has no email"""
        # Create a new user with no email
        user3 = User.objects.create_user(
            email='temp@test.com',  # Temporary email to satisfy model constraint
            password='testpass123',
            organisation=self.org2,
            first_name='User',
            last_name='Three'
        )
        # Set email to empty string after creation
        user3.email = ''
        user3.save()
        
        self.incident.taken_by = user3
        self.incident.save()
        
        # Create a collaboration - should be deleted due to missing email
        collaboration = Collaboration.objects.create(
            incident=self.incident,
            user=self.user1,
            end_date=date.today() + timedelta(days=30)
        )
        
        # Check that email was not sent
        mock_send_email.assert_not_called()
        
        # Verify collaboration was deleted
        self.assertEqual(Collaboration.objects.count(), 0)
        
        # Verify no notification was created
        self.assertEqual(Notification.objects.count(), 0)

    @patch('Mapapi.Send_mails.send_email.delay')
    def test_collaboration_signal_email_error(self, mock_send_email):
        """Test collaboration signal handling when email sending fails"""
        # Make send_email raise an exception
        mock_send_email.side_effect = Exception("Email error")
        
        # Create a collaboration
        collaboration = Collaboration.objects.create(
            incident=self.incident,
            user=self.user1,
            end_date=date.today() + timedelta(days=30)
        )
        
        # Check that the collaboration still exists despite email error
        self.assertEqual(Collaboration.objects.count(), 1)
        
        # Verify no notification was created since email failed
        self.assertEqual(Notification.objects.count(), 0)
