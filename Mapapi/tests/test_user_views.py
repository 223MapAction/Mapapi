from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class UserViewsTests(TestCase):
    """Tests for user-related views"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        self.client.force_authenticate(user=self.user)

    def test_user_api_view_get(self):
        """Test retrieving a user by ID"""
        url = reverse('user', args=[self.user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'test@example.com')
        self.assertEqual(response.data['email'], 'test@example.com')

    def test_user_api_view_put(self):
        """Test updating a user"""
        url = reverse('user', args=[self.user.id])
        data = {
            'first_name': 'Updated',
            'last_name': 'Name'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], 'Updated')
        self.assertEqual(response.data['last_name'], 'Name')

    def test_user_api_view_put_with_password(self):
        """Test updating a user's password"""
        url = reverse('user', args=[self.user.id])
        data = {
            'password': 'newpassword123'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify password was changed (can't check directly due to hashing)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpassword123'))

    def test_user_api_view_delete(self):
        """Test deleting a user"""
        url = reverse('user', args=[self.user.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(User.objects.filter(id=self.user.id).count(), 0)

    def test_user_api_view_get_not_found(self):
        """Test retrieving a non-existent user"""
        url = reverse('user', args=[999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_api_view_put_not_found(self):
        """Test updating a non-existent user"""
        url = reverse('user', args=[999])
        data = {'first_name': 'Updated'}
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_api_view_delete_not_found(self):
        """Test deleting a non-existent user"""
        url = reverse('user', args=[999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_api_list_view(self):
        """Test listing all users"""
        url = reverse('user_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)  # At least our test user
        
    def test_user_register_view(self):
        """Test user registration"""
        url = reverse('register')
        data = {
            'email': 'newuser@example.com',
            'password': 'newpassword123',
            'first_name': 'New',
            'last_name': 'User',
            'phone': '1234567890',
            'address': 'Test Address'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['email'], 'newuser@example.com')
        self.assertIn('token', response.data)
        
        # Verify user was created using email instead of username
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())
