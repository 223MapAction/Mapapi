from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from Mapapi.models import Incident, Zone, Category, Collaboration
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class CollaborationViewTests(APITestCase):
    def setUp(self):
        # Create test users
        self.user1 = User.objects.create_user(
            email='user1@example.com',
            password='testpass123',
            first_name='User',
            last_name='One',
            phone='1234567890',
            user_type='citizen'
        )
        self.user2 = User.objects.create_user(
            email='user2@example.com',
            password='testpass123',
            first_name='User',
            last_name='Two',
            phone='0987654321',
            user_type='citizen'
        )
        
        # Create test zone and category
        self.zone = Zone.objects.create(name='Test Zone')
        self.category = Category.objects.create(name='Test Category')
        
        # Create test incident
        self.incident = Incident.objects.create(
            title='Test Incident',
            zone=self.zone.name,
            user_id=self.user1,
            description='Test description',
            etat='declared',
            category_id=self.category
        )
        
        # Set up client authentication
        self.client.force_authenticate(user=self.user1)

    def test_create_collaboration_invalid_date(self):
        """Test collaboration creation with past end date fails"""
        url = reverse('collaboration')
        data = {
            'incident': self.incident.id,
            'user': self.user2.id,
            'end_date': (timezone.now() - timedelta(days=1)).date().isoformat()
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
