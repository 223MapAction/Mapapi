from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from Mapapi.models import Evenement, Zone
from rest_framework import status
from django.utils import timezone

User = get_user_model()

class EventViewTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            first_name='Test',
            last_name='User',
            phone='1234567890',
            user_type='citizen'
        )
        self.client.force_authenticate(user=self.user)

        # Create test zone
        self.zone = Zone.objects.create(
            name='Test Zone',
            lattitude='0.0',
            longitude='0.0'
        )

        # Create test event
        self.event = Evenement.objects.create(
            title='Test Event',
            zone=str(self.zone.name),
            description='Test Description',
            date=timezone.now(),
            lieu='Test Location',
            user_id=self.user,
            latitude='0.0',
            longitude='0.0'
        )

    def test_list_events(self):
        """Test listing all events"""
        url = reverse('event')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)

    def test_create_event(self):
        """Test creating a new event"""
        url = reverse('event')
        data = {
            'title': 'New Event',
            'description': 'New Description',
            'date': timezone.now().isoformat(),
            'lieu': 'New Location',
            'user_id': self.user.id,
            'zone': str(self.zone.name),
            'latitude': '1.0',
            'longitude': '1.0'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Evenement.objects.count(), 2)
        self.assertEqual(response.data['title'], 'New Event')

    def test_create_event_invalid_data(self):
        """Test creating an event with invalid data"""
        url = reverse('event')
        data = {
            'title': '',  # Empty title should be invalid
            'description': 'New Description',
            'date': timezone.now().isoformat(),
            'user_id': self.user.id,
            'zone': str(self.zone.name)
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_event(self):
        """Test retrieving a specific event"""
        url = reverse('event', args=[self.event.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Event')

    def test_retrieve_nonexistent_event(self):
        """Test retrieving a non-existent event"""
        url = reverse('event', args=[999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_event(self):
        """Test updating an event"""
        url = reverse('event', args=[self.event.id])
        data = {
            'title': 'Updated Event',
            'description': 'Updated Description',
            'date': timezone.now().isoformat(),
            'lieu': 'Updated Location',
            'user_id': self.user.id,
            'zone': str(self.zone.name),
            'latitude': '2.0',
            'longitude': '2.0'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Updated Event')
        self.assertEqual(self.event.lieu, 'Updated Location')

    def test_update_nonexistent_event(self):
        """Test updating a non-existent event"""
        url = reverse('event', args=[999])
        data = {
            'title': 'Updated Event',
            'description': 'Updated Description',
            'date': timezone.now().isoformat(),
            'user_id': self.user.id,
            'zone': str(self.zone.name)
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_event(self):
        """Test deleting an event"""
        url = reverse('event', args=[self.event.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Evenement.objects.count(), 0)

    def test_delete_nonexistent_event(self):
        """Test deleting a non-existent event"""
        url = reverse('event', args=[999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
