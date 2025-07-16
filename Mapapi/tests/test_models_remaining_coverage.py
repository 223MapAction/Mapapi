import uuid
import os
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone
from django.db import connection
from datetime import timedelta, datetime
from Mapapi.models import (
    User, Category, Zone, Incident, Rapport, Message, ResponseMessage,
    Collaboration, Colaboration, Prediction, ImageBackground, Notification
)


class UserManagerRemainingCoverageTests(TestCase):
    """Tests targeting uncovered lines 57-68, 75-81 in UserManager"""
    
    def test_create_user_with_staff_status(self):
        """Test creating a user with is_staff=True (lines 59-68)"""
        user = User.objects.create_user(
            email='staff@example.com',
            password='staffpass123',
            is_staff=True
        )
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)
        
    def test_create_superuser_with_empty_email(self):
        """Test creating a superuser with empty email (should raise ValueError)"""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email='',
                password='adminpass123'
            )


class UserModelRemainingCoverageTests(TestCase):
    """Tests targeting remaining uncovered lines in User model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            phone='1234567890'
        )
    
    def test_is_otp_valid_expired(self):
        """Test is_otp_valid method with expired OTP (line 199)"""
        # Generate OTP first
        self.user.generate_otp()
        
        # Set expiration to a past time
        self.user.otp_expiration = timezone.now() - timedelta(minutes=30)
        self.user.save()
        
        # Test with expired OTP
        self.assertFalse(self.user.is_otp_valid())
    
    def test_user_property_zone_property(self):
        """Test the zone property of User model (around line 106)"""
        # Create a zone
        zone = Zone.objects.create(name='Test Zone')
        
        # Create an incident linked to that zone
        category = Category.objects.create(name='Test Category')
        incident = Incident.objects.create(
            zone=zone.name,  # Zone is a CharField, not a ForeignKey
            title='Test Incident',
            description='Test Description',
            user_id=self.user  # user_id instead of created_by
        )
        # Add category using many-to-many relationship
        incident.category_ids.add(category)
        
        # Create a collaboration linking user to incident
        Collaboration.objects.create(
            user=self.user,
            incident=incident,
            end_date=timezone.now().date()
        )
        
        # For the User.zone property test, we'll add the zone to the user's zones
        self.user.zones.add(zone)
        
        # Test the zones many-to-many relationship instead since there is no 'zone' property
        # We added the zone to self.user.zones earlier
        self.assertIn(zone, self.user.zones.all())
        
        # Test removal of zone
        self.user.zones.remove(zone)
        self.assertNotIn(zone, self.user.zones.all())


class PredictionModelTests(TestCase):
    """Tests specifically targeting Prediction model methods (lines 436-440)"""
    
    @patch('Mapapi.models.connection')
    def test_prediction_save_method(self, mock_connection):
        """Test save method of Prediction model with mocked database connection"""
        # Mock the cursor and execution
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)  # Return ID 1
        
        # Create and save prediction
        prediction = Prediction(
            incident_id='123',
            incident_type='Test Type',
            piste_solution='Test Solution',
            analysis='Test Analysis'
        )
        
        prediction.save()
        
        # Verify correct SQL was executed
        mock_cursor.execute.assert_called_with("SELECT nextval('Mapapi_prediction_new_id_seq')")
        
        # Verify prediction_id was set
        self.assertEqual(prediction.prediction_id, 1)
        
        # Test second prediction gets ID 2
        mock_cursor.fetchone.return_value = (2,)  # Return ID 2
        prediction2 = Prediction(
            incident_id='456',
            incident_type='Test Type 2',
            piste_solution='Test Solution 2',
            analysis='Test Analysis 2'
        )
        prediction2.save()
        self.assertEqual(prediction2.prediction_id, 2)


class NotificationModelTests(TestCase):
    """Tests targeting Notification model (potentially line 451)"""
    
    def test_notification_str_method(self):
        """Test __str__ method of Notification model without creating an actual instance"""
        # Create a simple Notification object without saving it
        notification = Notification(message='Test Notification')
        
        # Test the __str__ method directly
        self.assertEqual(str(notification), 'Test Notification')
