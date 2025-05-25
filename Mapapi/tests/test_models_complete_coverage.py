from django.test import TestCase
from Mapapi.models import User


class UserManagerCompleteTests(TestCase):
    """Tests to ensure complete coverage of User model manager"""

    def test_create_user_with_phone_and_email(self):
        """Test creating a user with phone number and email"""
        phone = '123456789'
        email = 'test@example.com'
        user = User.objects.create_user(
            email=email,
            phone=phone,
            password='testpassword'
        )
        # Verify the user was created with the correct email and phone
        self.assertEqual(user.email, email)
        self.assertEqual(user.phone, phone)

    def test_get_or_create_user_with_phone_only(self):
        """Test get_or_create_user with only a phone number"""
        phone = '987654321'
        # First create should create a new user
        user1 = User.objects.get_or_create_user(
            phone=phone,
            password='testpassword'
        )
        self.assertEqual(user1.phone, phone)
        
        # Second call should return the existing user
        user2 = User.objects.get_or_create_user(
            phone=phone,
            password='newpassword'  # This password should be ignored
        )
        self.assertEqual(user1.id, user2.id)

    def test_create_superuser_with_invalid_is_staff(self):
        """Test creating a superuser with is_staff=False raises error"""
        with self.assertRaises(ValueError) as context:
            User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass',
                is_staff=False
            )
        self.assertEqual(str(context.exception), 'Superuser must have is_staff=True.')

    def test_create_user_no_email(self):
        """Test creating a user without email raises error"""
        with self.assertRaises(ValueError) as context:
            User.objects.create_user(
                email=None,
                phone='123456789',
                password='testpassword'
            )
        self.assertEqual(str(context.exception), 'The Email field must be set')

    def test_get_or_create_user_no_email_no_phone(self):
        """Test get_or_create_user with neither email nor phone raises error"""
        with self.assertRaises(ValueError) as context:
            User.objects.get_or_create_user(
                email=None,
                phone=None,
                password='testpassword'
            )
        self.assertEqual(str(context.exception), 'un email ou un numéro de téléphone est requiert')
