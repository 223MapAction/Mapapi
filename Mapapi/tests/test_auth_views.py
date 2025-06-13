from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from Mapapi.models import User
from django.utils import timezone

class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '1234567890',
            'user_type': 'citizen'
        }
        self.user = User.objects.create_user(
            email=self.user_data['email'],
            password=self.user_data['password'],
            first_name=self.user_data['first_name'],
            last_name=self.user_data['last_name'],
            phone=self.user_data['phone'],
            user_type=self.user_data['user_type']
        )

    def test_user_registration_success(self):
        """Test successful user registration"""
        url = reverse('register')
        new_user_data = {
            'email': 'newuser@example.com',
            'password': 'newpass123',
            'first_name': 'New',
            'last_name': 'User',
            'phone': '0987654321',
            'user_type': 'citizen',
            'address': '123 Test St'  # Optional field
        }
        response = self.client.post(url, new_user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())

    def test_user_registration_duplicate_email(self):
        """Test registration with existing email fails"""
        url = reverse('register')
        response = self.client.post(url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_login_success(self):
        """Test successful user login"""
        url = reverse('token_obtain_pair')
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        response = self.client.post(url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_user_login_invalid_credentials(self):
        """Test login with invalid credentials fails"""
        url = reverse('token_obtain_pair')
        invalid_login_data = {
            'email': self.user_data['email'],
            'password': 'wrongpassword'
        }
        response = self.client.post(url, invalid_login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_success(self):
        """Test successful password change"""
        url = reverse('change_password')
        self.client.force_authenticate(user=self.user)
        change_password_data = {
            'old_password': self.user_data['password'],
            'new_password': 'newpass123'
        }
        response = self.client.put(url, change_password_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify new password works
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass123'))

    def test_change_password_wrong_old_password(self):
        """Test password change with wrong old password fails"""
        url = reverse('change_password')
        self.client.force_authenticate(user=self.user)
        change_password_data = {
            'old_password': 'wrongpassword',
            'new_password': 'newpass123'
        }
        response = self.client.put(url, change_password_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_token_by_email_success(self):
        """Test successful token retrieval by email"""
        url = reverse('get_token_by_mail')
        data = {'email': self.user_data['email']}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', response.data)

    def test_get_token_by_email_invalid_email(self):
        """Test token retrieval with invalid email fails"""
        url = reverse('get_token_by_mail')
        data = {'email': 'nonexistent@example.com'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
