from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from unittest.mock import patch

from Mapapi.models import User, Zone, Collaboration, Colaboration, Incident, PhoneOTP
from Mapapi.serializer import (
    UserRegisterSerializer, EluToZoneSerializer, CollaborationSerializer,
    ColaborationSerializer, PhoneOTPSerializer, UserSerializer
)

class UserRegisterSerializerTests(TestCase):
    def test_create_user_register(self):
        """Test UserRegisterSerializer.create() method"""
        data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '+1234567890',
            'address': '123 Test St',
            'password': 'testpass123'
        }
        
        serializer = UserRegisterSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        user = serializer.save()
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'User')
        self.assertEqual(user.phone, '+1234567890')
        self.assertEqual(user.address, '123 Test St')
        self.assertTrue(user.check_password('testpass123'))
        self.assertTrue(user.is_active)


class EluToZoneSerializerTests(TestCase):
    def test_create_elu_to_zone(self):
        """Test EluToZoneSerializer.create() method"""
        # Create an ELU user (user_type='elu')
        elu_user = User.objects.create_user(
            email='elu@example.com',
            password='testpass123',
            first_name='ELU',
            last_name='User',
            user_type='elu'
        )
        
        # Create a zone
        zone = Zone.objects.create(
            name='Test Zone',
            description='Test Zone Description'
        )
        
        # Test data for the serializer
        data = {
            'elu': elu_user.id,
            'zone': zone.id
        }
        
        serializer = EluToZoneSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        result = serializer.save()
        
        # Check that the user now has the zone assigned
        self.assertIn(zone, elu_user.zones.all())
        self.assertEqual(result['elu'], elu_user)
        self.assertEqual(result['zone'], zone)


class PhoneOTPSerializerTests(TestCase):
    def test_phone_otp_serializer(self):
        """Test PhoneOTPSerializer"""
        data = {'phone_number': '+1234567890'}
        serializer = PhoneOTPSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['phone_number'], '+1234567890')


class CollaborationEdgeCaseTests(TestCase):
    def test_collaboration_serializer_with_end_date(self):
        """Test CollaborationSerializer with valid end date"""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        incident = Incident.objects.create(
            title='Test Incident',
            zone='Test Zone',
            description='Test description',
            user_id=user
        )
        
        # Test data with valid end_date
        future_date = timezone.now().date() + timedelta(days=7)
        data = {
            'incident': incident.id,
            'user': user.id,
            'status': 'pending',
            'end_date': future_date
        }
        
        serializer = CollaborationSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        try:
            collaboration = serializer.save()
            self.assertEqual(collaboration.incident, incident)
            self.assertEqual(collaboration.user, user)
            self.assertEqual(collaboration.end_date, future_date)
        except Exception as e:
            self.fail(f"Validation failed when it should have passed: {e}")
    
    def test_collaboration_serializer_with_past_end_date(self):
        """Test CollaborationSerializer with past end date"""
        user = User.objects.create_user(
            email='test2@example.com',
            password='testpass123',
            first_name='Test2',
            last_name='User'
        )
        
        incident = Incident.objects.create(
            title='Test Incident 2',
            zone='Test Zone',
            description='Test description',
            user_id=user
        )
        
        # Test data with past end_date
        past_date = timezone.now().date() - timedelta(days=1)
        data = {
            'incident': incident.id,
            'user': user.id,
            'status': 'pending',
            'end_date': past_date
        }
        
        serializer = CollaborationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        # The error is added to non_field_errors in the serializer
        self.assertIn('non_field_errors', serializer.errors)
        self.assertIn('La date de fin doit être dans le futur', str(serializer.errors['non_field_errors']))


class ColaborationSerializerTests(TestCase):
    def test_create_colaboration(self):
        """Test ColaborationSerializer"""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        incident = Incident.objects.create(
            title='Test Incident',
            zone='Test Zone',
            description='Test description',
            user_id=user
        )
        
        future_date = timezone.now().date() + timedelta(days=7)
        data = {
            'incident': incident.id,
            'user': user.id,
            'end_date': future_date
        }
        
        serializer = ColaborationSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        try:
            colaboration = serializer.save()
            self.assertEqual(colaboration.incident, incident)
            self.assertEqual(colaboration.user, user)
            self.assertEqual(colaboration.end_date, future_date)
        except Exception as e:
            self.fail(f"Failed to create Colaboration: {e}")
