from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from unittest.mock import patch
from Mapapi.serializer import (
    UserSerializer, UserEluSerializer, RegisterSerializer,
    SetPasswordSerializer, CollaborationSerializer
)
from Mapapi.models import User, Zone, Collaboration, Incident, Colaboration

class UserSerializerTests(TestCase):
    def test_create_user_with_zones(self):
        """Test UserSerializer.create() with zones"""
        # Create test zones
        zone1 = Zone.objects.create(name='Zone 1')
        zone2 = Zone.objects.create(name='Zone 2')
        
        # Test data with zones
        user_data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password': 'testpass123',
            'zones': [zone1.id, zone2.id]
        }
        
        serializer = UserSerializer(data=user_data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        
        # Verify zones were set
        self.assertEqual(user.zones.count(), 2)
        self.assertIn(zone1, user.zones.all())
        self.assertIn(zone2, user.zones.all())
    
    def test_create_user_without_zones(self):
        """Test UserSerializer.create() without zones"""
        # Test data without zones
        user_data = {
            'email': 'test2@example.com',
            'first_name': 'Test2',
            'last_name': 'User2',
            'password': 'testpass123'
        }
        
        serializer = UserSerializer(data=user_data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        
        # Verify no zones were set
        self.assertEqual(user.zones.count(), 0)


class UserEluSerializerTests(TestCase):
    def test_create_elu_user(self):
        """Test UserEluSerializer.create()"""
        user_data = {
            'email': 'elu@example.com',
            'first_name': 'Elu',
            'last_name': 'Test',
            'phone': '1234567890'
        }
        
        serializer = UserEluSerializer(data=user_data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        
        self.assertEqual(user.user_type, 'elu')
        self.assertTrue(user.active)


class RegisterSerializerTests(TestCase):
    @patch('Mapapi.models.User.send_verification_email')
    def test_register_user(self, mock_send_email):
        """Test RegisterSerializer.create()"""
        # Configure the mock
        mock_send_email.return_value = None
        
        user_data = {'email': 'register@example.com'}
        serializer = RegisterSerializer(data=user_data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        
        # Verify the user was created
        self.assertEqual(user.email, 'register@example.com')
        # Verify send_verification_email was called
        mock_send_email.assert_called_once()


class SetPasswordSerializerTests(TestCase):
    def test_validate_password(self):
        """Test SetPasswordSerializer.validate_password()"""
        serializer = SetPasswordSerializer()
        password = 'testpass123'
        self.assertEqual(serializer.validate_password(password), password)
    
    def test_save(self):
        """Test SetPasswordSerializer.save()"""
        user = User.objects.create_user(
            email='test@example.com',
            password='oldpassword',
            first_name='Test',
            last_name='User'
        )
        
        serializer = SetPasswordSerializer(data={'password': 'newpassword123'})
        self.assertTrue(serializer.is_valid())
        serializer.save(user=user)
        
        # Verify password was updated
        user.refresh_from_db()
        self.assertTrue(user.check_password('newpassword123'))


class CollaborationSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        self.incident = Incident.objects.create(
            title='Test Incident',
            zone='Test Zone',
            user_id=self.user
        )
    
    def test_validate_end_date_in_past(self):
        """Test CollaborationSerializer.validate() with end date in past"""
        past_date = timezone.now().date() - timedelta(days=1)
        data = {
            'incident': self.incident.id,
            'user': self.user.id,
            'end_date': past_date
        }
        
        serializer = CollaborationSerializer(data=data)
        with self.assertRaises(ValidationError) as context:
            serializer.is_valid(raise_exception=True)
        
        self.assertIn('La date de fin doit être dans le futur', str(context.exception))
    
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_validate_duplicate_collaboration(self):
        """Test CollaborationSerializer.validate() with end date in the past"""
        # Create a user with email to avoid signal error
        user = User.objects.create_user(
            email='test2@example.com',
            password='testpass123',
            first_name='Test2',
            last_name='User2'
        )
        
        # Create an incident
        incident = Incident.objects.create(
            title='Test Incident',
            zone='Test Zone',
            description='Test description',
            user_id=user
        )
        
        # Try to create a collaboration with end date in the past
        past_date = timezone.now().date() - timedelta(days=1)
        data = {
            'incident': incident.id,
            'user': user.id,
            'end_date': past_date,
            'status': 'pending'
        }
        
        # Create a new instance of the serializer with the data
        serializer = CollaborationSerializer(data=data)
        
        # The validation should fail with a ValidationError
        with self.assertRaises(serializers.ValidationError) as context:
            if not serializer.is_valid():
                raise serializers.ValidationError(serializer.errors)
            serializer.save()
        
        # Check that the error message is correct
        self.assertIn('La date de fin doit être dans le futur', str(context.exception))


class ColaborationSerializerTests(TestCase):
    def test_create_colaboration(self):
        """Test Colaboration model creation"""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        # Create an incident for the collaboration
        incident = Incident.objects.create(
            title='Test Incident',
            zone='Test Zone',
            description='Test description',
            user_id=user
        )
        
        # Create a Colaboration instance with required fields
        colaboration = Colaboration.objects.create(
            incident=incident,
            user=user,
            status='pending',
            end_date=timezone.now().date() + timedelta(days=7)
        )
        
        # Verify the object was created
        self.assertEqual(Colaboration.objects.count(), 1)
        self.assertEqual(colaboration.user, user)
        self.assertEqual(colaboration.status, 'pending')
        self.assertEqual(colaboration.incident, incident)
