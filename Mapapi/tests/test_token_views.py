from django.test import TestCase, RequestFactory
from django.http import JsonResponse
from rest_framework.test import APIClient
from rest_framework import status
from Mapapi.views import get_csrf_token, GetTokenByMailView
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class TokenViewsTests(TestCase):
    """Tests for token-related views"""

    def setUp(self):
        self.factory = RequestFactory()
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpassword'
        )

    def test_get_csrf_token(self):
        """Test the get_csrf_token view"""
        request = self.factory.get('/get_csrf_token/')
        response = get_csrf_token(request)
        self.assertIsInstance(response, JsonResponse)
        # JsonResponse content is a JSON-encoded string
        import json
        content = json.loads(response.content.decode())
        self.assertTrue('csrf_token' in content)
        self.assertIsNotNone(content['csrf_token'])

    def test_get_token_by_mail_view(self):
        """Test the GetTokenByMailView"""
        url = reverse('get_token_by_mail')
        data = {
            'email': 'test@example.com',
            'password': 'testpassword'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Check if response has the expected structure
        self.assertIn('status', response.data)
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('token', response.data)
