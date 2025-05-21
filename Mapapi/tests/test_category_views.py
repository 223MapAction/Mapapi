from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from Mapapi.models import Category
from rest_framework import status

User = get_user_model()

class CategoryViewTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            email='admin@example.com',
            password='testpass123',
            first_name='Admin',
            last_name='User',
            phone='1234567890',
            user_type='admin'
        )
        
        # Create test category
        self.category = Category.objects.create(
            name='Test Category',
            description='Test Description'
        )
        
        # Set up client authentication
        self.client.force_authenticate(user=self.user)

    def test_category_list(self):
        """Test retrieving list of categories"""
        url = reverse('category-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(response.data, list))
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Test Category')

    def test_create_category_success(self):
        """Test successful category creation"""
        url = reverse('category-list')
        data = {
            'name': 'New Category',
            'description': 'New Description'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Category.objects.count(), 2)
        self.assertTrue(Category.objects.filter(name='New Category').exists())

    def test_create_category_duplicate_name(self):
        """Test creating category with duplicate name fails"""
        url = reverse('category-list')
        data = {
            'name': 'Test Category',  # Same name as existing category
            'description': 'Another Description'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Category.objects.count(), 1)

    def test_get_category_detail(self):
        """Test retrieving a specific category"""
        url = reverse('category-detail', args=[self.category.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Category')
        self.assertEqual(response.data['description'], 'Test Description')

    def test_update_category_success(self):
        """Test successful category update"""
        url = reverse('category-detail', args=[self.category.id])
        data = {
            'name': 'Updated Category',
            'description': 'Updated Description'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Category')
        self.assertEqual(response.data['description'], 'Updated Description')

    def test_update_category_duplicate_name(self):
        """Test updating category with duplicate name fails"""
        # Create another category
        Category.objects.create(name='Another Category', description='Another Description')
        
        url = reverse('category-detail', args=[self.category.id])
        data = {
            'name': 'Another Category',
            'description': 'Updated Description'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_category_success(self):
        """Test successful category deletion"""
        url = reverse('category-detail', args=[self.category.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(id=self.category.id).exists())

    def test_delete_category_with_incidents(self):
        """Test deleting category with associated incidents fails"""
        # First create an incident with this category
        from Mapapi.models import Incident, Zone
        zone = Zone.objects.create(name='Test Zone')
        Incident.objects.create(
            title='Test Incident',
            zone=zone.name,
            user_id=self.user,
            description='Test description',
            category_id=self.category
        )
        
        url = reverse('category-detail', args=[self.category.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Category.objects.filter(id=self.category.id).exists())

    def test_category_pagination(self):
        """Test category list pagination"""
        # Create 15 more categories (16 total)
        for i in range(15):
            Category.objects.create(
                name=f'Category {i}',
                description=f'Description {i}'
            )
        
        url = reverse('category-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(response.data, list))
        self.assertEqual(len(response.data), 16)
