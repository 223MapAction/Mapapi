from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from Mapapi.models import User, UserManager
from unittest.mock import patch, MagicMock, PropertyMock

class UserManagerTargetedTests(TestCase):
    """Tests specifically targeting the remaining uncovered lines in models.py"""
    
    @patch('Mapapi.models.User.save')
    def test_create_user_with_phone_and_no_email(self, mock_save):
        """Test _create_user when only phone is provided"""
        manager = UserManager()
        manager.model = User
        
        # Create a real user instance with the manager
        phone = '123456789'
        user = manager._create_user(
            email=None,
            phone=phone,
            password='testpass'
        )
        
        # Verify the email was generated from phone
        expected_email = f"{phone}@example.com"
        self.assertEqual(user.email, expected_email)
        self.assertEqual(user.phone, phone)
        
        # Verify save was called
        self.assertTrue(mock_save.called)
        self.assertTrue(user.check_password('testpass'))
    
    @patch('Mapapi.models.User.save')
    def test_create_user_with_email_and_no_phone(self, mock_save):
        """Test _create_user when only email is provided"""
        manager = UserManager()
        manager.model = User
        
        # Create a real user instance with the manager
        email = 'test@example.com'
        user = manager._create_user(
            email=email,
            phone=None,
            password='testpass'
        )
        
        # Verify the email was set correctly and phone is None
        self.assertEqual(user.email, email)
        self.assertIsNone(user.phone)
        
        # Verify save was called
        self.assertTrue(mock_save.called)
        self.assertTrue(user.check_password('testpass'))
    
    def test_create_superuser_with_invalid_flags(self):
        """Test create_superuser with invalid flags"""
        # Test with is_superuser=False
        with self.assertRaises(ValueError) as context:
            User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass',
                is_superuser=False
            )
        self.assertEqual(str(context.exception), 'Superuser must have is_superuser=True.')
        
        # Test with is_staff=False
        with self.assertRaises(ValueError) as context:
            User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass',
                is_superuser=True,
                is_staff=False
            )
        self.assertEqual(str(context.exception), 'Superuser must have is_staff=True.')
        
    def test_get_or_create_user_with_phone_only(self):
        """Test get_or_create_user with phone only"""
        phone = '123456789'
        
        # First call should create a new user
        user1 = User.objects.get_or_create_user(
            phone=phone,
            password='testpass'
        )
        
        self.assertIsNotNone(user1)
        self.assertEqual(user1.phone, phone)
        self.assertEqual(user1.email, f"{phone}@example.com")
        
        # Second call should get the existing user
        with patch.object(User.objects, 'get') as mock_get:
            mock_get.return_value = user1
            user2 = User.objects.get_or_create_user(
                phone=phone,
                password='newpass'  # Should be ignored
            )
            
            self.assertEqual(user1.id, user2.id)
            self.assertEqual(user2.phone, phone)
    
    def test_create_user_with_no_email_and_no_phone(self):
        """Test _create_user raises error when both email and phone are None"""
        manager = UserManager()
        manager.model = User
        
        with self.assertRaises(ValueError) as context:
            manager._create_user(
                email=None,
                phone=None,
                password='testpass'
            )
        
        self.assertEqual(
            str(context.exception),
            'The given email or phone number must be set'
        )
