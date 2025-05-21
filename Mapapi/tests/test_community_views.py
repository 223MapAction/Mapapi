from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from Mapapi.models import Communaute, Zone
from rest_framework import status

User = get_user_model()

class CommunityViewTests(APITestCase):
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

        # Create test community
        self.community = Communaute.objects.create(
            name='Test Community',
            zone=self.zone
        )

    def test_list_communities(self):
        """Test listing all communities"""
        url = reverse('community')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) >= 1)

    def test_create_community(self):
        """Test creating a new community"""
        url = reverse('community')
        data = {
            'name': 'New Community',
            'zone': self.zone.id
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Communaute.objects.count(), 2)
        self.assertEqual(response.data['name'], 'New Community')

    def test_create_community_invalid_data(self):
        """Test creating a community with invalid data"""
        url = reverse('community')
        data = {
            'name': '',  # Empty name should be invalid
            'zone': self.zone.id
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_community(self):
        """Test retrieving a specific community"""
        url = reverse('community', args=[self.community.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Community')

    def test_retrieve_nonexistent_community(self):
        """Test retrieving a non-existent community"""
        url = reverse('community', args=[999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_community(self):
        """Test updating a community"""
        url = reverse('community', args=[self.community.id])
        data = {
            'name': 'Updated Community',
            'zone': self.zone.id
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.community.refresh_from_db()
        self.assertEqual(self.community.name, 'Updated Community')

    def test_update_nonexistent_community(self):
        """Test updating a non-existent community"""
        url = reverse('community', args=[999])
        data = {
            'name': 'Updated Community',
            'zone': self.zone.id
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_community(self):
        """Test deleting a community"""
        url = reverse('community', args=[self.community.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Communaute.objects.count(), 0)

    def test_delete_nonexistent_community(self):
        """Test deleting a non-existent community"""
        url = reverse('community', args=[999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
