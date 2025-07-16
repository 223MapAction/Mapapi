from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from Mapapi.models import ImageBackground
from rest_framework import status
import tempfile
from PIL import Image
import os

User = get_user_model()

class ImageBackgroundViewTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            phone='1234567890',
            user_type='citizen'
        )
        
        # Create a temporary image file
        self.image_file = self.create_temporary_image()
        
        # Create test image background
        self.image_background = ImageBackground.objects.create(
            photo=self.image_file.name
        )
        
        # Set up client authentication
        self.client.force_authenticate(user=self.user)

    def create_temporary_image(self):
        # Create a temporary image file
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        image = Image.new('RGB', (100, 100))
        image.save(temp_file.name)
        return temp_file

    def tearDown(self):
        # Clean up temporary files
        if hasattr(self, 'image_file'):
            os.unlink(self.image_file.name)

    def test_list_images(self):
        """Test listing all image backgrounds"""
        url = reverse('image')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)  # API returns 201 for GET request
        self.assertTrue(len(response.data) >= 1)  # At least one image should exist

    def test_create_image(self):
        """Test creating a new image background"""
        url = reverse('image')
        with open(self.image_file.name, 'rb') as img:
            data = {
                'photo': img
            }
            response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ImageBackground.objects.count(), 2)

    def test_retrieve_image(self):
        """Test retrieving a specific image background"""
        url = reverse('image', args=[self.image_background.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('photo', response.data)

    def test_update_image(self):
        """Test updating an image background"""
        url = reverse('image', args=[self.image_background.id])
        with open(self.image_file.name, 'rb') as img:
            data = {
                'photo': img
            }
            response = self.client.put(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_image(self):
        """Test deleting an image background"""
        url = reverse('image', args=[self.image_background.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ImageBackground.objects.count(), 0)

    def test_retrieve_nonexistent_image(self):
        """Test retrieving a non-existent image background"""
        url = reverse('image', args=[999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_nonexistent_image(self):
        """Test updating a non-existent image background"""
        url = reverse('image', args=[999])
        with open(self.image_file.name, 'rb') as img:
            data = {
                'photo': img
            }
            response = self.client.put(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
