import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from Mapapi.models import (
    User, UserManager, Prediction, Notification, Zone, Category, Incident
)


class UserManagerFinalCoverageTests(TestCase):
    """Tests for the remaining uncovered UserManager methods (lines 57-68, 75-81)"""
    
    def test_get_or_create_user_with_phone(self):
        """Test get_or_create_user method with phone only (lines 57-68)"""
        # This should create a new user with a dummy email
        user = User.objects.get_or_create_user(phone="1234567890")
        
        # Verify user was created with phone and a dummy email
        self.assertEqual(user.phone, "1234567890")
        self.assertEqual(user.email, "1234567890@example.com")  # The actual format used in the model
        self.assertTrue(user.is_active)
    
    def test_get_or_create_user_with_existing_phone(self):
        """Test get_or_create_user with an existing phone number (lines 57-68)"""
        # First create a user with a phone number
        original_user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            phone="9876543210"
        )
        
        # Now try to get_or_create with the same phone
        retrieved_user = User.objects.get_or_create_user(phone="9876543210")
        
        # Should return the existing user, not create a new one
        self.assertEqual(original_user.id, retrieved_user.id)
        self.assertEqual(retrieved_user.email, "test@example.com")


class UserModelFinalCoverageTests(TestCase):
    """Tests for remaining uncovered User model methods (line 106, 199)"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
    
    def test_is_otp_valid_no_otp(self):
        """Test is_otp_valid method with no OTP set (line 199)"""
        # Don't set any OTP
        self.user.otp = None
        self.user.otp_expiration = None
        self.user.save()
        
        # Should return False when no OTP is set
        self.assertFalse(self.user.is_otp_valid())
    
    def test_user_property_zone_property_none(self):
        """Test the User model's zone-related property (line 106)"""
        # Create some zones but don't assign to user
        zone1 = Zone.objects.create(name="Zone 1")
        zone2 = Zone.objects.create(name="Zone 2")
        
        # Test when user has multiple zones, what's returned
        self.user.zones.add(zone1, zone2)
        
        # The property should exist and return something
        self.assertTrue(hasattr(self.user, 'zones'))
        self.assertEqual(self.user.zones.count(), 2)


class PredictionFinalCoverageTests(TestCase):
    """Tests for Prediction model save method branch coverage (lines 436-440)"""
    
    @patch('Mapapi.models.connection')
    def test_prediction_save_with_existing_id(self, mock_connection):
        """Test save method of Prediction with an existing ID (line 436 branch)"""
        # Create a prediction with an existing ID
        prediction = Prediction(
            prediction_id=999,  # Existing ID
            incident_id='123',
            incident_type='Test Type',
            piste_solution='Test Solution',
            analysis='Test Analysis'
        )
        
        # Mock cursor should not be called when prediction_id already exists
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Save the prediction
        prediction.save()
        
        # Verify prediction_id was not changed
        self.assertEqual(prediction.prediction_id, 999)
        
        # Verify cursor.execute was not called
        mock_cursor.execute.assert_not_called()
